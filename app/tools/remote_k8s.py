"""HTTP client for calling K8s/Mimir tools on remote cluster agents.

Used by the backend in multi-cluster mode. Each function takes a
cluster name, looks up the agent URL in the registry, and POSTs
to the corresponding /cluster/v1/* endpoint.
"""

from __future__ import annotations

from typing import Any

import requests

from app.cluster_registry import get_url
from app.config import settings

_TIMEOUT = 30


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if settings.join_token:
        h["Authorization"] = f"Bearer {settings.join_token}"
    return h


def _post(cluster: str, path: str, payload: dict) -> Any:
    """POST to a cluster agent endpoint and return parsed JSON."""
    url = get_url(cluster) + "/cluster/v1" + path
    resp = requests.post(url, json=payload, headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def remote_get_pod(cluster: str, namespace: str, pod_name: str) -> dict:
    return _post(cluster, "/pod", {"namespace": namespace, "pod_name": pod_name})


def remote_get_events(cluster: str, namespace: str, involved_object_name: str) -> list:
    return _post(cluster, "/events", {"namespace": namespace, "involved_object_name": involved_object_name})


def remote_get_logs(cluster: str, namespace: str, pod_name: str, container: str = "", previous: bool = False, tail: int = 100) -> str:
    data = _post(cluster, "/logs", {
        "namespace": namespace, "pod_name": pod_name,
        "container": container, "previous": previous, "tail": tail,
    })
    return data.get("logs", "")


def remote_list_deployments(cluster: str, namespace: str) -> list:
    return _post(cluster, "/deployments", {"namespace": namespace})


def remote_get_node(cluster: str, node_name: str) -> dict:
    return _post(cluster, "/node", {"node_name": node_name})


def remote_query_metrics(cluster: str, promql: str, start: str, end: str, step: str = "60s") -> dict:
    return _post(cluster, "/metrics/query_range", {
        "promql": promql, "start": start, "end": end, "step": step,
    })


def remote_query_metrics_instant(cluster: str, promql: str) -> dict:
    return _post(cluster, "/metrics/query", {"promql": promql})


def remote_check_endpoint(cluster: str, url: str, timeout: int = 5) -> dict:
    return _post(cluster, "/check_endpoint", {"url": url, "timeout": timeout})
