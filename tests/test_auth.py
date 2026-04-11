"""Tests for OIDC auth: claim resolution, team mapping, incident filtering."""

import pytest

from app.auth import AuthUser, can_view_incident, filter_incidents, resolve_user
from app.config import settings


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "auth_claim_mapping", "")
    monkeypatch.setattr(settings, "auth_team_mappings", "")
    monkeypatch.setattr(settings, "auth_admin_teams", "")


# --- resolve_user ---


def test_resolve_user_basic(monkeypatch):
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')
    monkeypatch.setattr(settings, "auth_admin_teams", "sre")

    user = resolve_user({"sub": "user1", "department": "checkout"})
    assert user.sub == "user1"
    assert user.is_admin is False
    assert user.allowed_label_values == {"team": ["checkout"]}


def test_resolve_user_with_team_mapping(monkeypatch):
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')
    monkeypatch.setattr(settings, "auth_team_mappings", '{"XY-Z": ["XY-Z1", "XY-Z2"]}')
    monkeypatch.setattr(settings, "auth_admin_teams", "sre")

    user = resolve_user({"sub": "user2", "department": "XY-Z"})
    assert user.allowed_label_values == {"team": ["XY-Z1", "XY-Z2"]}


def test_resolve_user_admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')
    monkeypatch.setattr(settings, "auth_admin_teams", "sre,platform-leads")

    user = resolve_user({"sub": "admin1", "department": "sre"})
    assert user.is_admin is True
    assert user.allowed_label_values == {}  # Admin — no filtering needed


def test_resolve_user_no_matching_claim(monkeypatch):
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')
    monkeypatch.setattr(settings, "auth_admin_teams", "sre")

    user = resolve_user({"sub": "user3", "email": "user@example.com"})
    # No department claim → no allowed labels
    assert user.allowed_label_values == {}
    assert user.is_admin is False


def test_resolve_user_multiple_claim_mappings(monkeypatch):
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team", "location": "region"}')
    monkeypatch.setattr(settings, "auth_admin_teams", "sre")

    user = resolve_user({"sub": "user4", "department": "checkout", "location": "eu"})
    assert user.allowed_label_values == {"team": ["checkout"], "region": ["eu"]}


def test_resolve_user_no_mapping_is_admin(monkeypatch):
    """Empty claim_mapping → fail open, everyone admin."""
    monkeypatch.setattr(settings, "auth_claim_mapping", "")
    monkeypatch.setattr(settings, "auth_admin_teams", "sre")
    user = resolve_user({"sub": "user5", "department": "anything"})
    assert user.is_admin is True


def test_resolve_user_no_admin_teams_is_admin(monkeypatch):
    """Empty admin_teams → fail open, everyone admin."""
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')
    monkeypatch.setattr(settings, "auth_admin_teams", "")
    user = resolve_user({"sub": "user6", "department": "anything"})
    assert user.is_admin is True


# --- filter_incidents ---

MOCK_INCIDENTS = {
    "inc-1": {"status": "completed", "labels": {"team": "XY-Z1", "namespace": "prod"}},
    "inc-2": {"status": "completed", "labels": {"team": "XY-Z2", "namespace": "prod"}},
    "inc-3": {"status": "completed", "labels": {"team": "platform", "namespace": "infra"}},
    "inc-4": {"status": "investigating", "labels": {"team": "checkout", "namespace": "prod"}},
    "inc-5": {"status": "completed", "labels": {}},
}


def test_filter_no_auth():
    """Auth disabled (user=None) → see everything."""
    result = filter_incidents(MOCK_INCIDENTS, None)
    assert len(result) == 5


def test_filter_admin():
    """Admin user → see everything."""
    admin = AuthUser(sub="admin", claims={}, is_admin=True)
    result = filter_incidents(MOCK_INCIDENTS, admin)
    assert len(result) == 5


def test_filter_by_team_exact():
    """User with exact team match."""
    user = AuthUser(sub="u1", claims={}, allowed_label_values={"team": ["checkout"]})
    result = filter_incidents(MOCK_INCIDENTS, user)
    assert list(result.keys()) == ["inc-4"]


def test_filter_by_team_expanded():
    """User with expanded team mapping (XY-Z → XY-Z1, XY-Z2)."""
    user = AuthUser(sub="u2", claims={}, allowed_label_values={"team": ["XY-Z1", "XY-Z2"]})
    result = filter_incidents(MOCK_INCIDENTS, user)
    assert set(result.keys()) == {"inc-1", "inc-2"}


def test_filter_no_claims():
    """User with no mapped claims → sees nothing."""
    user = AuthUser(sub="u3", claims={}, allowed_label_values={})
    result = filter_incidents(MOCK_INCIDENTS, user)
    assert len(result) == 0


def test_filter_no_matching_labels():
    """User has claims but no incidents match."""
    user = AuthUser(sub="u4", claims={}, allowed_label_values={"team": ["nonexistent"]})
    result = filter_incidents(MOCK_INCIDENTS, user)
    assert len(result) == 0


# --- can_view_incident ---


def test_can_view_no_auth():
    assert can_view_incident({"labels": {"team": "x"}}, None) is True


def test_can_view_admin():
    admin = AuthUser(sub="admin", claims={}, is_admin=True)
    assert can_view_incident({"labels": {"team": "x"}}, admin) is True


def test_can_view_matching():
    user = AuthUser(sub="u", claims={}, allowed_label_values={"team": ["checkout"]})
    assert can_view_incident({"labels": {"team": "checkout"}}, user) is True


def test_can_view_not_matching():
    user = AuthUser(sub="u", claims={}, allowed_label_values={"team": ["checkout"]})
    assert can_view_incident({"labels": {"team": "platform"}}, user) is False


def test_can_view_no_labels():
    user = AuthUser(sub="u", claims={}, allowed_label_values={"team": ["checkout"]})
    assert can_view_incident({"labels": {}}, user) is False
    assert can_view_incident({}, user) is False


# --- Endpoint integration (in-memory mode) ---


@pytest.mark.asyncio
async def test_incidents_filtered_by_auth(monkeypatch):
    """Auth-enabled endpoint filters incidents by user's team."""
    from httpx import ASGITransport, AsyncClient
    from app.webhook import app, _memory_store, _memory_labels
    import app.webhook as wh

    monkeypatch.setattr(wh, "_use_db", False)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_claim_mapping", '{"department": "team"}')

    # Seed test data
    _memory_store["test-1"] = None
    _memory_labels["test-1"] = {"team": "checkout", "alertname": "CrashLoop"}
    _memory_store["test-2"] = None
    _memory_labels["test-2"] = {"team": "platform", "alertname": "OOM"}

    # Override the FastAPI dependency to skip real OIDC validation
    from app.auth import get_current_user as real_dep
    async def mock_get_user():
        return AuthUser(sub="user1", claims={}, allowed_label_values={"team": ["checkout"]})

    app.dependency_overrides[real_dep] = mock_get_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/incidents")
        assert resp.status_code == 200
        data = resp.json()
        # Should only see checkout incidents
        assert "test-1" in data
        assert "test-2" not in data
    finally:
        app.dependency_overrides.clear()
        _memory_store.pop("test-1", None)
        _memory_store.pop("test-2", None)
        _memory_labels.pop("test-1", None)
        _memory_labels.pop("test-2", None)


@pytest.mark.asyncio
async def test_incident_detail_forbidden(monkeypatch):
    """Auth-enabled: accessing another team's incident returns 403."""
    from httpx import ASGITransport, AsyncClient
    from app.webhook import app, _memory_store, _memory_labels
    import app.webhook as wh

    monkeypatch.setattr(wh, "_use_db", False)
    monkeypatch.setattr(settings, "auth_enabled", True)

    _memory_store["forbidden-1"] = None
    _memory_labels["forbidden-1"] = {"team": "platform"}

    from app.auth import get_current_user as real_dep
    async def mock_get_user():
        return AuthUser(sub="user1", claims={}, allowed_label_values={"team": ["checkout"]})
    app.dependency_overrides[real_dep] = mock_get_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/incidents/forbidden-1")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
        _memory_store.pop("forbidden-1", None)
        _memory_labels.pop("forbidden-1", None)
