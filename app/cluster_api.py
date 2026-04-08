"""HTTP API that exposes K8s and Mimir tools for remote access.

Deployed as a lightweight agent on each cluster. The central backend
calls these endpoints instead of talking to the K8s API directly.

Also includes the /cluster/join endpoint used by the backend to accept
agent registrations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cluster/v1", tags=["cluster"])


# --- Auth ---

def verify_join_token(authorization: str | None = Header(default=None)):
    """Verify the shared join token between backend and agent."""
    if not settings.join_token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    token = authorization.removeprefix("Bearer ")
    if token != settings.join_token:
        raise HTTPException(status_code=403, detail="Invalid token")


# --- Join endpoint (runs on backend) ---

class JoinRequest(BaseModel):
    cluster_name: str
    agent_url: str  # how the backend can reach this agent
    has_metrics: bool = False


@router.post("/join")
def cluster_join(req: JoinRequest, _=Depends(verify_join_token)):
    """Agent calls this on the backend to register itself."""
    from app.cluster_registry import register
    agent = register(req.cluster_name, req.agent_url, req.has_metrics)
    logger.info("Cluster %s joined from %s", req.cluster_name, req.agent_url)
    return {"status": "joined", "cluster_name": agent.name}


@router.delete("/join/{cluster_name}")
def cluster_leave(cluster_name: str, _=Depends(verify_join_token)):
    """Remove a cluster agent from the registry."""
    from app.cluster_registry import unregister
    if not unregister(cluster_name):
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"status": "removed", "cluster_name": cluster_name}


@router.get("/agents")
def list_agents(_=Depends(verify_join_token)):
    """List all registered cluster agents."""
    from app.cluster_registry import list_agents as _list
    return [
        {"name": a.name, "url": a.url, "has_metrics": a.has_metrics, "joined_at": a.joined_at.isoformat()}
        for a in _list()
    ]


# --- Request models for K8s/Mimir tools (run on agent) ---

class PodRequest(BaseModel):
    namespace: str
    pod_name: str


class EventsRequest(BaseModel):
    namespace: str
    involved_object_name: str


class LogsRequest(BaseModel):
    namespace: str
    pod_name: str
    container: str = ""
    previous: bool = False
    tail: int = 100


class DeploymentsRequest(BaseModel):
    namespace: str


class NodeRequest(BaseModel):
    node_name: str


class MetricsRangeRequest(BaseModel):
    promql: str
    start: str
    end: str
    step: str = "60s"


class MetricsInstantRequest(BaseModel):
    promql: str


class CheckEndpointRequest(BaseModel):
    url: str
    timeout: int = 5


# --- K8s tool endpoints (run on agent) ---

@router.get("/info")
def cluster_info(_=Depends(verify_join_token)):
    """Return cluster identity and capabilities."""
    return {
        "cluster_name": settings.cluster_name,
        "has_metrics": bool(settings.mimir_endpoint),
    }


@router.post("/pod")
def cluster_get_pod(req: PodRequest, _=Depends(verify_join_token)):
    from app.tools.k8s import k8s_get_pod
    return k8s_get_pod(req.namespace, req.pod_name)


@router.post("/events")
def cluster_get_events(req: EventsRequest, _=Depends(verify_join_token)):
    from app.tools.k8s import k8s_get_events
    return k8s_get_events(req.namespace, req.involved_object_name)


@router.post("/logs")
def cluster_get_logs(req: LogsRequest, _=Depends(verify_join_token)):
    from app.tools.k8s import k8s_get_logs
    return {"logs": k8s_get_logs(req.namespace, req.pod_name, req.container or None, req.previous, req.tail)}


@router.post("/deployments")
def cluster_list_deployments(req: DeploymentsRequest, _=Depends(verify_join_token)):
    from app.tools.k8s import k8s_list_deployments
    return k8s_list_deployments(req.namespace)


@router.post("/node")
def cluster_get_node(req: NodeRequest, _=Depends(verify_join_token)):
    from app.tools.k8s import k8s_get_node
    return k8s_get_node(req.node_name)


@router.post("/metrics/query_range")
def cluster_metrics_range(req: MetricsRangeRequest, _=Depends(verify_join_token)):
    if not settings.mimir_endpoint:
        raise HTTPException(status_code=404, detail="No metrics endpoint configured on this agent")
    from app.tools.mimir import mimir_query
    return mimir_query(req.promql, req.start, req.end, req.step)


@router.post("/metrics/query")
def cluster_metrics_instant(req: MetricsInstantRequest, _=Depends(verify_join_token)):
    if not settings.mimir_endpoint:
        raise HTTPException(status_code=404, detail="No metrics endpoint configured on this agent")
    from app.tools.mimir import mimir_instant_query
    return mimir_instant_query(req.promql)


@router.post("/check_endpoint")
def cluster_check_endpoint(req: CheckEndpointRequest, _=Depends(verify_join_token)):
    from app.tools.connectivity import check_endpoint
    return check_endpoint(req.url, req.timeout)
