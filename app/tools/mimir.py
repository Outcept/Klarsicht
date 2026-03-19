"""Prometheus/Mimir query tools for the RCA agent.

Supports both vanilla Prometheus and Mimir. Set the metrics endpoint to:
  - Prometheus: http://prometheus.monitoring.svc:9090
  - Mimir:      http://mimir.monitoring.svc:9009/prometheus
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    """Return the metrics API base URL, stripping trailing slashes."""
    return settings.mimir_endpoint.rstrip("/")


def mimir_query(promql: str, start: str, end: str, step: str = "60s") -> dict[str, Any]:
    """Execute a range query against Prometheus/Mimir.

    Args:
        promql: PromQL expression.
        start: RFC3339 or Unix timestamp for range start.
        end: RFC3339 or Unix timestamp for range end.
        step: Query resolution step (e.g. "60s", "5m").

    Returns:
        Parsed JSON response from the query_range endpoint.
    """
    url = f"{_base_url()}/api/v1/query_range"

    try:
        resp = requests.get(
            url,
            params={"query": promql, "start": start, "end": end, "step": step},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("Metrics query failed: %s", e)
        return {"error": str(e), "status": "error"}


def mimir_instant_query(promql: str) -> dict[str, Any]:
    """Execute an instant query against Prometheus/Mimir.

    Args:
        promql: PromQL expression.

    Returns:
        Parsed JSON response from the query endpoint.
    """
    url = f"{_base_url()}/api/v1/query"

    try:
        resp = requests.get(url, params={"query": promql}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("Metrics instant query failed: %s", e)
        return {"error": str(e), "status": "error"}
