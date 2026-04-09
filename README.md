# Klarsicht

AI-powered root cause analysis for Kubernetes. Self-hosted. Helm install. FINMA-ready.

Klarsicht is an AI agent that receives Grafana alerts, inspects your Kubernetes cluster (pods, logs, events, Prometheus metrics), and delivers structured root cause analyses with fix steps and postmortem drafts — in under 60 seconds.

**[Website](https://klarsicht.dev)** · **[Docs](https://klarsicht.dev/docs/)** · **[Blog](https://klarsicht.dev/blog/)**

## How it works

```
Grafana Alert → Klarsicht Agent → K8s API + Prometheus → LLM → RCA Result
```

1. Grafana fires a webhook to Klarsicht
2. The AI agent inspects pods, reads logs, pulls events, queries Prometheus
3. A structured root cause analysis is delivered with confidence score, fix steps, and postmortem

## Quick Start

```bash
helm install klarsicht oci://ghcr.io/outcept/klarsicht/helm/klarsicht \
  --namespace klarsicht --create-namespace \
  --set agent.llmApiKey=<your-api-key> \
  --set agent.metricsEndpoint=http://prometheus.monitoring.svc:9090
```

Then point your Grafana webhook contact point to:

```
http://klarsicht-agent.klarsicht.svc:8000/alert
```

## Test it

```bash
# Deploy a pod that intentionally crashes (missing env var)
kubectl apply -f examples/test-crashloop.yaml

# Or send a mock alert directly
curl -X POST http://klarsicht-agent.klarsicht.svc:8000/test
```

## Architecture

```
┌───────────────────────────────────────────┐
│  Your Kubernetes Cluster                  │
│                                           │
│  Grafana ──webhook──▸ Klarsicht Agent     │
│                       ├─▸ K8s API (r/o)   │
│                       ├─▸ Prometheus       │
│                       └─▸ PostgreSQL       │
│                       │                   │
│                       ▼                   │
│                    LLM API                │
│              (external or local)          │
└───────────────────────────────────────────┘
```

**Three deployment models:**
- **Standalone** — Single cluster. LLM runs externally or locally. Default.
- **Multi-Cluster** — Central backend + lightweight agents per cluster. Join-token registration.
- **On-Prem** — LLM runs in-cluster (Ollama, vLLM, watsonx). Zero external calls. Air-gap ready.

## Multi-Cluster

Deploy a lightweight agent on each cluster that registers with a central backend:

```bash
# Central backend (has LLM, stores results, serves dashboard)
helm install klarsicht-backend ... \
  --set agent.mode=backend \
  --set agent.joinToken=my-secret-token

# Agent on cluster B (no LLM, just exposes K8s tools)
helm install klarsicht-agent ... \
  --set agent.mode=agent \
  --set agent.clusterName=prod-eu-1 \
  --set agent.joinToken=my-secret-token \
  --set agent.backendUrl=http://klarsicht-backend.central.svc:8000
```

Agents auto-register on startup. The LLM tools include a `cluster` parameter so the AI can inspect any connected cluster.

## OIDC Authentication

Team-based access control via OIDC. Map token claims to alert labels — teams only see their own incidents:

```yaml
dashboard:
  oidc:
    enabled: true
    issuerUrl: https://login.microsoftonline.com/{tenant}/v2.0
    clientId: your-client-id
    claimMapping: '{"department": "team"}'
    teamMappings: '{"XY-Z": ["XY-Z1", "XY-Z2"]}'
    adminTeams: "sre,admin"
```

## Supported LLM Providers

```bash
# Anthropic Claude (default)
helm install klarsicht ... \
  --set agent.llmProvider=anthropic \
  --set agent.llmApiKey=sk-ant-...

# OpenAI
helm install klarsicht ... \
  --set agent.llmProvider=openai \
  --set agent.llmApiKey=sk-... \
  --set agent.llmModel=gpt-4o

# IBM watsonx
helm install klarsicht ... \
  --set agent.llmProvider=watsonx \
  --set agent.llmApiKey=your-iam-key \
  --set agent.llmModel=ibm/granite-3-8b-instruct \
  --set agent.llmBaseUrl=https://your-watsonx-endpoint \
  --set agent.watsonxProjectId=your-project-id

# Ollama (local, air-gapped)
helm install klarsicht ... \
  --set agent.llmProvider=ollama \
  --set agent.llmModel=llama3.1 \
  --set agent.llmBaseUrl=http://ollama.default.svc:11434/v1

# Any OpenAI-compatible API
helm install klarsicht ... \
  --set agent.llmProvider=openai \
  --set agent.llmBaseUrl=https://your-vllm-server/v1 \
  --set agent.llmApiKey=your-key \
  --set agent.llmModel=your-model
```

## What it inspects

| Tool | Data |
|------|------|
| `get_pod` | Pod status, restart count, exit codes, resource limits |
| `get_logs` | Container stdout/stderr (current + previous) |
| `get_events` | K8s warning events (BackOff, FailedMount, etc.) |
| `list_deployments` | Replica counts, images, rollout history |
| `get_node` | Node conditions, allocatable resources, taints |
| `query_metrics` | PromQL range queries against Prometheus/Mimir |
| `check_endpoint` | HTTP/TCP connectivity checks, TLS cert info, response time |
| `lookup_service` | Service catalog — tech stack, dependencies, team, runbook link |
| `search_runbook` | Fetch operations handbook (BHB) sections from Confluence |

All read-only. No write permissions. No exec. No secrets accessed.

## RCA Output

```json
{
  "root_cause": {
    "summary": "Missing DATABASE_URL environment variable",
    "confidence": 0.94,
    "category": "misconfiguration",
    "evidence": ["KeyError in logs", "7 restarts in 15 min"]
  },
  "fix_steps": [
    {"order": 1, "description": "Add DATABASE_URL to the secret", "command": "kubectl patch ..."}
  ],
  "postmortem": {
    "impact": "Worker pods unavailable for 15 minutes",
    "timeline": [{"timestamp": "...", "event": "Secret modified"}],
    "action_items": ["Add pre-deploy env var validation"]
  }
}
```

## Confluence Integration

Auto-discover operations handbooks (BHBs) from Confluence and build a service catalog:

```bash
# 1. Sync — crawls Confluence spaces, discovers BHBs
curl -X POST http://klarsicht:8000/catalog/sync

# 2. Match — LLM fuzzy-matches K8s deployments to BHB pages
curl -X POST http://klarsicht:8000/catalog/match

# 3. Done — agent now has lookup_service + search_runbook tools
```

The agent automatically fetches relevant runbook sections during investigations.

## Integrations

**Live:** Kubernetes, Prometheus, Mimir, Grafana, Confluence, Slack, Teams, Discord, GitLab CI/CD

**LLM Providers:** Anthropic Claude, OpenAI, IBM watsonx, Ollama, any OpenAI-compatible API

**Coming soon:** Loki, Tempo, ArgoCD, Cert-Manager, Cilium/Hubble, Flux, PagerDuty

## Test Results

Tested across 154 incidents covering 10 failure categories:

- Missing environment variables
- Connection failures (Redis, Postgres, gRPC, DNS)
- Authentication errors (OAuth, AWS, mTLS)
- Data/schema errors (JSON, Protobuf, migrations)
- Resource exhaustion (OOM, disk, fd limits)
- Application logic (NullPointer, panic, deadlock)
- Dependency issues (missing modules, version conflicts)
- Network errors (NetworkPolicy, service mesh, TLS)

**Average confidence: 94.5%** across all categories.

## Requirements

- Kubernetes 1.26+
- Helm 3
- Grafana with alerting
- Prometheus (optional, for metrics correlation)

## License

[MIT](LICENSE) — Copyright 2026 Outcept
