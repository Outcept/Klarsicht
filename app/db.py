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
    labels          JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS steps JSONB;

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
    labels: dict[str, str] | None = None,
) -> None:
    """Insert a new incident row with status 'investigating'."""
    pool = _get_pool()
    await pool.execute(
        """
        INSERT INTO incidents (id, alert_name, namespace, pod, status, labels, started_at)
        VALUES ($1, $2, $3, $4, 'investigating', $5, $6)
        """,
        incident_id,
        alert_name,
        namespace,
        pod,
        json.dumps(labels or {}),
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


async def mark_incident_failed(incident_id: UUID, error_message: str | None = None) -> None:
    """Mark an incident as failed if the investigation errors out."""
    pool = _get_pool()
    await pool.execute(
        "UPDATE incidents SET status = 'failed', error_message = $2 WHERE id = $1",
        incident_id,
        error_message,
    )


async def save_incident_steps(incident_id: UUID, steps: list[dict[str, Any]]) -> None:
    """Persist the agent's execution trace so it survives the in-memory cleanup."""
    pool = _get_pool()
    await pool.execute(
        "UPDATE incidents SET steps = $2 WHERE id = $1",
        incident_id,
        json.dumps(steps),
    )


async def get_incident_steps(incident_id: UUID) -> list[dict[str, Any]] | None:
    """Read the persisted execution trace for an incident."""
    pool = _get_pool()
    row = await pool.fetchrow("SELECT steps FROM incidents WHERE id = $1", incident_id)
    if row is None or row["steps"] is None:
        return None
    return json.loads(row["steps"])


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

    labels = json.loads(row["labels"]) if row.get("labels") else {}
    error = row["error_message"] if "error_message" in row.keys() else None
    return {"status": status, "result": result, "labels": labels, "error": error}


async def get_incident(incident_id: UUID) -> dict[str, Any] | None:
    """Get a single incident with its RCA result."""
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.status, i.labels, i.started_at, i.error_message,
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
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.status, i.labels, i.started_at, i.error_message,
               r.investigated_at, r.root_cause, r.fix_steps, r.postmortem
        FROM incidents i
        LEFT JOIN rca_results r ON r.incident_id = i.id
        ORDER BY i.created_at DESC
        """
    )
    return {str(row["id"]): _row_to_incident(row) for row in rows}


async def get_alert_history(
    alert_name: str = "",
    namespace: str = "",
    pod: str = "",
    days: int = 30,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find past incidents matching the given criteria.

    Searches by alert_name, namespace, or pod (partial match).
    Returns recent incidents with their root cause summaries.
    """
    pool = _get_pool()

    conditions = ["i.status = 'completed'"]
    params: list[Any] = []
    idx = 1

    if alert_name:
        conditions.append(f"i.alert_name = ${idx}")
        params.append(alert_name)
        idx += 1

    if namespace:
        conditions.append(f"i.namespace = ${idx}")
        params.append(namespace)
        idx += 1

    if pod:
        # Match pod prefix (deployment name without replica hash)
        pod_prefix = "-".join(pod.split("-")[:-2]) if pod.count("-") >= 2 else pod
        conditions.append(f"i.pod LIKE ${idx}")
        params.append(f"{pod_prefix}%")
        idx += 1

    conditions.append(f"i.started_at > now() - interval '{days} days'")
    where = " AND ".join(conditions)

    rows = await pool.fetch(
        f"""
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.started_at,
               r.root_cause, r.investigated_at
        FROM incidents i
        LEFT JOIN rca_results r ON r.incident_id = i.id
        WHERE {where}
        ORDER BY i.started_at DESC
        LIMIT {limit}
        """,
        *params,
    )

    results = []
    for row in rows:
        rc_data = json.loads(row["root_cause"]) if row["root_cause"] else None
        results.append({
            "incident_id": str(row["id"]),
            "alert_name": row["alert_name"],
            "namespace": row["namespace"],
            "pod": row["pod"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "root_cause_summary": rc_data.get("summary", "") if rc_data else "",
            "root_cause_category": rc_data.get("category", "") if rc_data else "",
            "confidence": rc_data.get("confidence", 0) if rc_data else 0,
        })

    return results


async def get_stats() -> dict[str, Any]:
    """Aggregate incident statistics for the overview dashboard."""
    pool = _get_pool()

    # Status counts
    status_rows = await pool.fetch(
        "SELECT status, COUNT(*) AS cnt FROM incidents GROUP BY status"
    )
    status_counts: dict[str, int] = {row["status"]: row["cnt"] for row in status_rows}
    total = sum(status_counts.values())
    completed = status_counts.get("completed", 0)
    investigating = status_counts.get("investigating", 0)
    failed = status_counts.get("failed", 0)

    # Average investigation time (seconds) for completed incidents
    avg_row = await pool.fetchrow(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (r.investigated_at - i.started_at))) AS avg_secs
        FROM incidents i
        JOIN rca_results r ON r.incident_id = i.id
        WHERE i.status = 'completed'
        """
    )
    avg_secs = float(avg_row["avg_secs"]) if avg_row and avg_row["avg_secs"] is not None else 0.0

    # Top alerts
    top_alert_rows = await pool.fetch(
        """
        SELECT alert_name, COUNT(*) AS cnt
        FROM incidents
        GROUP BY alert_name
        ORDER BY cnt DESC
        LIMIT 10
        """
    )
    top_alerts = [{"alert_name": r["alert_name"], "count": r["cnt"]} for r in top_alert_rows]

    # Top namespaces
    top_ns_rows = await pool.fetch(
        """
        SELECT namespace, COUNT(*) AS cnt
        FROM incidents
        GROUP BY namespace
        ORDER BY cnt DESC
        LIMIT 10
        """
    )
    top_namespaces = [{"namespace": r["namespace"], "count": r["cnt"]} for r in top_ns_rows]

    # Recent incidents (last 5)
    recent_rows = await pool.fetch(
        """
        SELECT i.id, i.alert_name, i.namespace, i.pod, i.status, i.started_at,
               r.root_cause
        FROM incidents i
        LEFT JOIN rca_results r ON r.incident_id = i.id
        ORDER BY i.created_at DESC
        LIMIT 5
        """
    )
    recent: list[dict[str, Any]] = []
    for row in recent_rows:
        confidence: float | None = None
        if row["root_cause"]:
            rc_data = json.loads(row["root_cause"])
            confidence = rc_data.get("confidence")
        recent.append({
            "incident_id": str(row["id"]),
            "alert_name": row["alert_name"],
            "namespace": row["namespace"],
            "pod": row["pod"],
            "status": row["status"],
            "confidence": confidence,
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        })

    # Category breakdown from root_cause JSONB
    cat_rows = await pool.fetch(
        """
        SELECT r.root_cause->>'category' AS category, COUNT(*) AS cnt
        FROM rca_results r
        WHERE r.root_cause IS NOT NULL AND r.root_cause->>'category' IS NOT NULL
        GROUP BY category
        ORDER BY cnt DESC
        """
    )
    category_breakdown = [{"category": r["category"], "count": r["cnt"]} for r in cat_rows]

    return {
        "total_incidents": total,
        "completed": completed,
        "investigating": investigating,
        "failed": failed,
        "avg_investigation_seconds": round(avg_secs, 1),
        "top_alerts": top_alerts,
        "top_namespaces": top_namespaces,
        "recent_incidents": recent,
        "category_breakdown": category_breakdown,
    }
