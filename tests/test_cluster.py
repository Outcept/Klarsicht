"""Tests for multi-cluster join flow, registry, and cluster API."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.webhook import app
from app import cluster_registry


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Reset registry and force in-memory mode for each test."""
    cluster_registry.clear()
    monkeypatch.setattr(settings, "join_token", "")
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "cluster_name", "")
    monkeypatch.setattr(settings, "backend_url", "")
    import app.webhook as wh
    monkeypatch.setattr(wh, "_use_db", False)


@pytest.fixture
def transport():
    return ASGITransport(app=app)


# --- Registry unit tests ---


def test_register_and_list():
    cluster_registry.register("prod-eu", "http://agent-eu:8000", has_metrics=True)
    cluster_registry.register("staging", "http://agent-staging:8000")

    agents = cluster_registry.list_agents()
    assert len(agents) == 2
    names = cluster_registry.list_cluster_names()
    assert "prod-eu" in names
    assert "staging" in names


def test_get_url():
    cluster_registry.register("prod-eu", "http://agent-eu:8000/")
    # Trailing slash should be stripped
    assert cluster_registry.get_url("prod-eu") == "http://agent-eu:8000"


def test_get_url_unknown_cluster():
    with pytest.raises(ValueError, match="Unknown cluster"):
        cluster_registry.get_url("nonexistent")


def test_unregister():
    cluster_registry.register("prod-eu", "http://agent-eu:8000")
    assert cluster_registry.unregister("prod-eu") is True
    assert cluster_registry.get("prod-eu") is None
    assert cluster_registry.unregister("prod-eu") is False


def test_register_overwrites():
    cluster_registry.register("prod-eu", "http://old:8000")
    cluster_registry.register("prod-eu", "http://new:8000")
    assert cluster_registry.get_url("prod-eu") == "http://new:8000"
    assert len(cluster_registry.list_agents()) == 1


# --- Join endpoint tests ---


@pytest.mark.asyncio
async def test_join_no_token(transport):
    """Join succeeds when no join_token is configured (open mode)."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/cluster/v1/join", json={
            "cluster_name": "test-cluster",
            "agent_url": "http://agent:8000",
            "has_metrics": False,
        })
    assert resp.status_code == 200
    assert resp.json()["status"] == "joined"
    assert cluster_registry.get("test-cluster") is not None


@pytest.mark.asyncio
async def test_join_with_valid_token(transport, monkeypatch):
    monkeypatch.setattr(settings, "join_token", "secret-123")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/cluster/v1/join",
            json={"cluster_name": "prod", "agent_url": "http://agent:8000"},
            headers={"Authorization": "Bearer secret-123"},
        )
    assert resp.status_code == 200
    assert cluster_registry.get("prod") is not None


@pytest.mark.asyncio
async def test_join_with_bad_token(transport, monkeypatch):
    monkeypatch.setattr(settings, "join_token", "secret-123")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/cluster/v1/join",
            json={"cluster_name": "prod", "agent_url": "http://agent:8000"},
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_join_missing_token(transport, monkeypatch):
    monkeypatch.setattr(settings, "join_token", "secret-123")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/cluster/v1/join",
            json={"cluster_name": "prod", "agent_url": "http://agent:8000"},
        )
    assert resp.status_code == 401


# --- List agents endpoint ---


@pytest.mark.asyncio
async def test_list_agents_endpoint(transport):
    cluster_registry.register("a", "http://a:8000")
    cluster_registry.register("b", "http://b:8000", has_metrics=True)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/cluster/v1/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {a["name"] for a in data}
    assert names == {"a", "b"}


# --- Leave endpoint ---


@pytest.mark.asyncio
async def test_leave(transport):
    cluster_registry.register("prod", "http://agent:8000")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/cluster/v1/join/prod")
    assert resp.status_code == 200
    assert cluster_registry.get("prod") is None


@pytest.mark.asyncio
async def test_leave_unknown(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/cluster/v1/join/nonexistent")
    assert resp.status_code == 404


# --- Tool selection ---


def test_get_tools_standalone(monkeypatch):
    """Standalone mode returns local K8s tools + connectivity tools."""
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools, K8S_TOOLS, CONNECTIVITY_TOOLS
    tools = get_tools()
    assert len(tools) == len(K8S_TOOLS) + len(CONNECTIVITY_TOOLS)


def test_get_tools_backend(monkeypatch):
    """Backend mode returns remote K8s tools + remote connectivity tools."""
    monkeypatch.setattr(settings, "mode", "backend")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools, REMOTE_K8S_TOOLS, REMOTE_MIMIR_TOOLS, REMOTE_CONNECTIVITY_TOOLS
    tools = get_tools()
    assert len(tools) == len(REMOTE_K8S_TOOLS) + len(REMOTE_MIMIR_TOOLS) + len(REMOTE_CONNECTIVITY_TOOLS)


def test_get_compact_tools_backend(monkeypatch):
    """Backend compact mode returns remote tools."""
    monkeypatch.setattr(settings, "mode", "backend")
    monkeypatch.setattr(settings, "database_url", "")

    from app.agent.tools import get_compact_tools
    tools = get_compact_tools()
    tool_names = [t.name for t in tools]
    assert all("remote" in name for name in tool_names)
