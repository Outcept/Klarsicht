---
title: Kubernetes
weight: 1
---

Klarsicht connects to the Kubernetes API via the pod's ServiceAccount. No additional configuration needed — it auto-discovers the API server when running in-cluster.

## Tools available to the agent

| Tool | What it does | K8s API call |
|------|-------------|--------------|
| `get_pod` | Pod status, restart count, exit codes, resource limits | `GET /api/v1/namespaces/{ns}/pods/{name}` |
| `get_logs` | Container stdout/stderr (current + previous) | `GET /api/v1/namespaces/{ns}/pods/{name}/log` |
| `get_events` | Warning events for a pod (last 60 min) | `GET /api/v1/namespaces/{ns}/events` |
| `list_deployments` | All deployments with replica counts, images | `GET /apis/apps/v1/namespaces/{ns}/deployments` |
| `get_node` | Node conditions, allocatable resources, taints | `GET /api/v1/nodes/{name}` |

## Namespace scoping

By default, the agent can inspect all namespaces. To restrict:

```yaml
# values.yaml
agent:
  watchNamespaces:
    - production
    - staging
```

The agent will only investigate pods in the listed namespaces.

## What data is accessed

- Pod metadata (name, namespace, labels, annotations)
- Container status (state, exit code, restart count)
- Container logs (last 100 lines by default)
- Kubernetes events (Warning type, last 60 minutes)
- Deployment spec (image tags, replica counts, rollout history)
- Node conditions (MemoryPressure, DiskPressure, Ready)

**Not accessed:** Secrets, ConfigMap values, volumes, exec into containers.
