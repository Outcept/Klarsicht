"""Agent startup registration with the central backend.

When mode=agent, this runs on startup to register this cluster agent
with the backend via POST /cluster/v1/join.
"""

from __future__ import annotations

import logging
import time

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_DELAY = 3  # seconds


def register_with_backend() -> None:
    """POST to the backend's /cluster/v1/join endpoint.

    Retries a few times on failure since the backend may not be up yet.
    """
    if not settings.backend_url:
        logger.error("KLARSICHT_BACKEND_URL is required in agent mode")
        return
    if not settings.cluster_name:
        logger.error("KLARSICHT_CLUSTER_NAME is required in agent mode")
        return

    url = settings.backend_url.rstrip("/") + "/cluster/v1/join"
    headers = {"Content-Type": "application/json"}
    if settings.join_token:
        headers["Authorization"] = f"Bearer {settings.join_token}"

    # Build the agent's own URL that the backend will use to call us.
    # In K8s this is typically the service DNS name.
    # The agent advertises its own pod/service URL.
    agent_url = _build_agent_url()

    payload = {
        "cluster_name": settings.cluster_name,
        "agent_url": agent_url,
        "has_metrics": bool(settings.mimir_endpoint),
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            logger.info(
                "Registered with backend as %r (attempt %d) — %s",
                settings.cluster_name, attempt, resp.json(),
            )
            return
        except Exception:
            logger.warning(
                "Failed to register with backend (attempt %d/%d)",
                attempt, _MAX_RETRIES, exc_info=True,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    logger.error("Could not register with backend after %d attempts", _MAX_RETRIES)


def _build_agent_url() -> str:
    """Determine the URL the backend should use to reach this agent.

    Uses KLARSICHT_DASHBOARD_URL if set (external URL), otherwise
    constructs a K8s-style service URL from the cluster name.
    """
    if settings.dashboard_url:
        return settings.dashboard_url
    # Fallback: assume K8s service naming convention
    # The Helm chart names the service klarsicht-agent in the release namespace
    return "http://klarsicht-agent.klarsicht.svc:8000"
