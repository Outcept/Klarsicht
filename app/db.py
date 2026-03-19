"""Postgres database layer for incident and RCA storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from app.config import settings
from app.models.rca import FixStep, Postmortem, RCAResult, RootCause, TimelineEntry

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY,
    alert_name      TEXT NOT NULL,
    namespace       TEXT NOT NULL,
    pod             TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'investigating',
    started_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rca_results (
    incident_id     UUID PRIMARY KEY REFERENCES incidents(id),
    investigated_at TIMESTAMPTZ NOT NULL,
    root_cause      JSONB,
    fix_steps       JSONB,
    postmortem      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_db() -> None:
    """Create the connection pool and run migrations."""
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _pool


async def create_incident(
    incident_id: UUID,
    alert_name: str,
    namespace: str,
    pod: str,
    started_at: datetime,
) -> None:
    """Insert a new incident row with status 'investigating'."""
    pool = _get_pool()
    await pool.execute(
        """
        INSERT INTO incidents (id, alert_name, namespace, pod, status, started_at)
        VALUES ($1, $2, $3, $4, 'investigating', $5)
        """,
        incident_id,
        alert_name,
        namespace,
        pod,
        started_at,
    )


async def save_rca_result(incident_id: UUID, result: RCAResult) -> None:
    """Save the completed RCA result and mark incident as completed."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO rca_results (incident_id, investigated_at, root_cause, fix_steps, postmortem)
                VALUES ($1, $2, $3, $4, $5)
                """,
                incident_id,
                result.investigated_at,
                json.dumps(result.root_cause.model_dump(mode="json")) if result.root_cause else None,
                json.dumps([s.model_dump(mode="json") for s in result.fix_steps]),
                json.dumps(result.postmortem.model_dump(mode="json")) if result.postmortem else None,
            )
            await conn.execute(
                "UPDATE incidents SET status = 'completed' WHERE id = $1",
                incident_id,
            )


async def mark_incident_failed(incident_id: UUID) -> None:
    """Mark an incident as failed if the investigation errors out."""
    pool = _get_pool()
    await pool.execute(
        "UPDATE incidents SET status = 'failed' WHERE id = $1",
        incident_id,
    )


def _row_to_incident(row: asyncpg.Record) -> dict[str, Any]:
    """Convert a joined incident+rca row into the API response shape."""
    status = row["status"]
    result = None

    if status == "completed" and row.get("investigated_at"):
        root_cause_data = json.loads(row["root_cause"]) if row["root_cause"] else None
        fix_steps_data = json.loads(row["fix_steps"]) if row["fix_steps"] else []
        postmortem_data = json.loads(row["postmortem"]) if row["postmortem"] else None

        result = RCAResult(
            incident_id=row["id"],
            alert_name=row["alert_name"],
            namespace=row["namespace"],
            pod=row["pod"],
            started_at=row["started_at"],
            investigated_at=row["investigated_at"],
            root_cause=RootCause(**root_cause_data) if root_cause_data else None,
            fix_steps=[FixStep(**s) for s in fix_steps_data],
            postmortem=Postmortem(**postmortem_data) if postmortem_data else None,
        ).model_dump(mode="json")

    return {"status": status, "result": result}


async def get_incident(incident_id: UUID) -> dict[str, Any] | None:
    """Get a single incident with its RCA result."""
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.status, i.started_at,
               r.investigated_at, r.root_cause, r.fix_steps, r.postmortem
        FROM incidents i
        LEFT JOIN rca_results r ON r.incident_id = i.id
        WHERE i.id = $1
        """,
        incident_id,
    )
    if row is None:
        return None
    return _row_to_incident(row)


async def list_incidents() -> dict[str, Any]:
    """List all incidents with their RCA results."""
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.status, i.started_at,
               r.investigated_at, r.root_cause, r.fix_steps, r.postmortem
        FROM incidents i
        LEFT JOIN rca_results r ON r.incident_id = i.id
        ORDER BY i.created_at DESC
        """
    )
    return {str(row["id"]): _row_to_incident(row) for row in rows}
