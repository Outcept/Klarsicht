"""Tests for the database layer — unit tests with mocked asyncpg pool."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.rca import FixStep, Postmortem, RCAResult, RootCause, TimelineEntry


@pytest.fixture(autouse=True)
def mock_pool(monkeypatch):
    """Provide a mocked asyncpg pool for all db tests."""
    pool = AsyncMock()
    import app.db as db_mod
    monkeypatch.setattr(db_mod, "_pool", pool)
    return pool


@pytest.mark.asyncio
async def test_create_incident(mock_pool):
    from app.db import create_incident

    incident_id = uuid4()
    await create_incident(
        incident_id, "CrashLoopBackOff", "production", "worker-abc", datetime(2025, 3, 19, 10, 0, tzinfo=timezone.utc)
    )

    mock_pool.execute.assert_called_once()
    call_args = mock_pool.execute.call_args
    assert incident_id == call_args[0][1]
    assert "CrashLoopBackOff" == call_args[0][2]


@pytest.mark.asyncio
async def test_save_rca_result(mock_pool):
    from app.db import save_rca_result

    incident_id = uuid4()
    result = RCAResult(
        incident_id=incident_id,
        alert_name="CrashLoopBackOff",
        namespace="production",
        pod="worker-abc",
        started_at=datetime(2025, 3, 19, 10, 0, tzinfo=timezone.utc),
        investigated_at=datetime(2025, 3, 19, 10, 1, tzinfo=timezone.utc),
        root_cause=RootCause(
            summary="Missing env var",
            confidence=0.9,
            category="misconfiguration",
            evidence=["KeyError: SECRET_KEY"],
        ),
        fix_steps=[FixStep(order=1, description="Add the secret", command="kubectl patch ...")],
        postmortem=Postmortem(impact="15 minutes downtime", action_items=["Add pre-deploy check"]),
    )

    # asyncpg pool.acquire() returns an async context manager (not a coroutine).
    # Override acquire to be a plain MagicMock so it returns the CM directly.
    mock_conn = AsyncMock()

    class FakeAcquire:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, *args):
            pass

    class FakeTx:
        async def __aenter__(self):
            return None
        async def __aexit__(self, *args):
            pass

    mock_pool.acquire = MagicMock(return_value=FakeAcquire())
    mock_conn.transaction = MagicMock(return_value=FakeTx())

    await save_rca_result(incident_id, result)

    # Should have called execute twice: INSERT rca_results + UPDATE incidents
    assert mock_conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_mark_incident_failed(mock_pool):
    from app.db import mark_incident_failed

    incident_id = uuid4()
    await mark_incident_failed(incident_id)

    mock_pool.execute.assert_called_once()
    assert "failed" in mock_pool.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_get_incident_not_found(mock_pool):
    from app.db import get_incident

    mock_pool.fetchrow.return_value = None
    result = await get_incident(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_incident_investigating(mock_pool):
    from app.db import get_incident

    iid = uuid4()
    mock_pool.fetchrow.return_value = {
        "id": iid,
        "alert_name": "CrashLoopBackOff",
        "namespace": "production",
        "pod": "worker-abc",
        "status": "investigating",
        "started_at": datetime(2025, 3, 19, 10, 0, tzinfo=timezone.utc),
        "investigated_at": None,
        "root_cause": None,
        "fix_steps": None,
        "postmortem": None,
    }

    result = await get_incident(iid)
    assert result is not None
    assert result["status"] == "investigating"
    assert result["result"] is None


@pytest.mark.asyncio
async def test_get_incident_completed(mock_pool):
    from app.db import get_incident

    iid = uuid4()
    mock_pool.fetchrow.return_value = {
        "id": iid,
        "alert_name": "CrashLoopBackOff",
        "namespace": "production",
        "pod": "worker-abc",
        "status": "completed",
        "started_at": datetime(2025, 3, 19, 10, 0, tzinfo=timezone.utc),
        "investigated_at": datetime(2025, 3, 19, 10, 1, tzinfo=timezone.utc),
        "root_cause": json.dumps({"summary": "Missing env", "confidence": 0.9, "category": "misconfiguration", "evidence": []}),
        "fix_steps": json.dumps([{"order": 1, "description": "Fix it", "command": ""}]),
        "postmortem": json.dumps({"timeline": [], "impact": "downtime", "action_items": []}),
    }

    result = await get_incident(iid)
    assert result is not None
    assert result["status"] == "completed"
    assert result["result"]["root_cause"]["summary"] == "Missing env"
    assert result["result"]["incident_id"] == str(iid)


@pytest.mark.asyncio
async def test_list_incidents(mock_pool):
    from app.db import list_incidents

    iid1, iid2 = uuid4(), uuid4()
    mock_pool.fetch.return_value = [
        {
            "id": iid1,
            "alert_name": "CrashLoop",
            "namespace": "prod",
            "pod": "w1",
            "status": "investigating",
            "started_at": datetime(2025, 3, 19, 10, 0, tzinfo=timezone.utc),
            "investigated_at": None,
            "root_cause": None,
            "fix_steps": None,
            "postmortem": None,
        },
        {
            "id": iid2,
            "alert_name": "OOMKilled",
            "namespace": "prod",
            "pod": "w2",
            "status": "completed",
            "started_at": datetime(2025, 3, 19, 9, 0, tzinfo=timezone.utc),
            "investigated_at": datetime(2025, 3, 19, 9, 2, tzinfo=timezone.utc),
            "root_cause": json.dumps({"summary": "OOM", "confidence": 0.8, "category": "resource_exhaustion", "evidence": []}),
            "fix_steps": json.dumps([]),
            "postmortem": json.dumps({"timeline": [], "impact": "", "action_items": []}),
        },
    ]

    result = await list_incidents()
    assert len(result) == 2
    assert result[str(iid1)]["status"] == "investigating"
    assert result[str(iid2)]["status"] == "completed"
    assert result[str(iid2)]["result"]["root_cause"]["summary"] == "OOM"
