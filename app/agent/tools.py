"""LangChain tool wrappers around K8s and Mimir functions."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.tools.k8s import (
    k8s_get_events,
    k8s_get_logs,
    k8s_get_node,
    k8s_get_pod,
    k8s_list_deployments,
)
from app.tools.mimir import mimir_instant_query, mimir_query


def _serialize(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


@tool
def get_pod(namespace: str, pod_name: str) -> str:
    """Get pod status including phase, restart count, conditions, resource limits/requests, node name, and container statuses.

    Args:
        namespace: Kubernetes namespace.
        pod_name: Name of the pod.
    """
    return _serialize(k8s_get_pod(namespace, pod_name))


@tool
def get_events(namespace: str, involved_object_name: str) -> str:
    """Get Kubernetes warning events for a specific object (pod, node, etc.) from the last 60 minutes.

    Args:
        namespace: Kubernetes namespace.
        involved_object_name: Name of the involved object (e.g. pod name).
    """
    return _serialize(k8s_get_events(namespace, involved_object_name))


@tool
def get_logs(
    namespace: str,
    pod_name: str,
    container: str = "",
    previous: bool = False,
    tail: int = 100,
) -> str:
    """Get container logs from a pod. Use previous=True to get logs from the last terminated container (useful for crash loops).

    Args:
        namespace: Kubernetes namespace.
        pod_name: Name of the pod.
        container: Container name. Leave empty for single-container pods.
        previous: If True, get logs from the previous (crashed) container instance.
        tail: Number of log lines to return (default 100).
    """
    return k8s_get_logs(namespace, pod_name, container or None, previous, tail)


@tool
def list_deployments(namespace: str) -> str:
    """List all deployments in a namespace with replica counts, images, and last update timestamps. Useful for checking recent rollouts.

    Args:
        namespace: Kubernetes namespace.
    """
    return _serialize(k8s_list_deployments(namespace))


@tool
def get_node(node_name: str) -> str:
    """Get node status including allocatable resources, conditions (MemoryPressure, DiskPressure), and taints.

    Args:
        node_name: Name of the Kubernetes node.
    """
    return _serialize(k8s_get_node(node_name))


@tool
def query_metrics(promql: str, start: str, end: str, step: str = "60s") -> str:
    """Execute a PromQL range query against Mimir/Prometheus. Returns time series data.

    Args:
        promql: PromQL expression (e.g. 'container_memory_usage_bytes{pod="worker-abc"}').
        start: Range start as RFC3339 timestamp (e.g. '2025-03-19T09:30:00Z').
        end: Range end as RFC3339 timestamp.
        step: Query resolution step (e.g. '60s', '5m').
    """
    return _serialize(mimir_query(promql, start, end, step))


@tool
def query_metrics_instant(promql: str) -> str:
    """Execute an instant PromQL query against Mimir/Prometheus. Returns current values.

    Args:
        promql: PromQL expression.
    """
    return _serialize(mimir_instant_query(promql))


K8S_TOOLS = [
    get_pod,
    get_events,
    get_logs,
    list_deployments,
    get_node,
]

MIMIR_TOOLS = [
    query_metrics,
    query_metrics_instant,
]


def get_tools() -> list:
    """Return the active tool set based on configuration."""
    from app.config import settings

    tools = list(K8S_TOOLS)
    if settings.mimir_endpoint:
        tools.extend(MIMIR_TOOLS)
    return tools
