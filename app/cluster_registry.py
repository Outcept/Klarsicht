"""In-memory registry of cluster agents that have joined via token.

The backend keeps this registry and uses it to route LangGraph tool
calls to the correct cluster agent over HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ClusterAgent:
    name: str
    url: str  # e.g. http://agent-prod-eu:8000
    has_metrics: bool = False
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Cluster name -> agent info
_registry: dict[str, ClusterAgent] = {}


def register(name: str, url: str, has_metrics: bool = False) -> ClusterAgent:
    """Register or update a cluster agent."""
    agent = ClusterAgent(name=name, url=url.rstrip("/"), has_metrics=has_metrics)
    _registry[name] = agent
    logger.info("Cluster agent registered: %s at %s (metrics=%s)", name, url, has_metrics)
    return agent


def unregister(name: str) -> bool:
    """Remove a cluster agent from the registry."""
    if name in _registry:
        del _registry[name]
        logger.info("Cluster agent unregistered: %s", name)
        return True
    return False


def get(name: str) -> ClusterAgent | None:
    """Get a registered cluster agent by name."""
    return _registry.get(name)


def get_url(name: str) -> str:
    """Get agent URL by cluster name. Raises ValueError if not found."""
    agent = _registry.get(name)
    if agent is None:
        available = list(_registry.keys())
        raise ValueError(f"Unknown cluster: {name!r}. Available: {available}")
    return agent.url


def list_agents() -> list[ClusterAgent]:
    """Return all registered agents."""
    return list(_registry.values())


def list_cluster_names() -> list[str]:
    """Return names of all registered clusters."""
    return list(_registry.keys())


def clear() -> None:
    """Clear the registry (for testing)."""
    _registry.clear()
