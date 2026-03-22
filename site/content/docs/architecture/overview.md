---
title: Architecture Overview
weight: 1
---

Klarsicht is an AI agent that sits on top of your existing monitoring stack. It doesn't collect data, doesn't store metrics, and doesn't build dashboards. It adds intelligence — layers 4 and 5 (correlation and reasoning).

## Components

```
┌─────────────────────────────────────────────────┐
│  Your Kubernetes Cluster                        │
│                                                 │
│  Grafana ──webhook──▸ Klarsicht Agent           │
│                       │  ├─▸ K8s API (read-only)│
│                       │  ├─▸ Prometheus (PromQL) │
│                       │  └─▸ PostgreSQL (storage)│
│                       │                         │
│                       ▼                         │
│                    LLM API                      │
│                  (external or local)            │
└─────────────────────────────────────────────────┘
```

## Investigation flow

When a Grafana alert fires:

1. **Receive** — Webhook payload arrives at `POST /alert` with alertname, namespace, pod, severity
2. **Parse** — Extract context: which pod, which namespace, when did it start
3. **Inspect** — Agent reads pod status, container states, restart count, exit codes
4. **Logs** — Pull last 100 lines from current and previous container
5. **Events** — Kubernetes warning events (BackOff, FailedMount, Unhealthy)
6. **Metrics** — PromQL queries for CPU, memory, error rate in ±30min window
7. **Correlate** — Check recent deployments, upstream pods, node health
8. **Synthesize** — LLM produces root cause, confidence score, fix steps, postmortem

The entire process takes 15-60 seconds.

## RBAC

The agent uses a ClusterRole with **read-only** access:

| Resource | Verbs |
|----------|-------|
| pods | get, list |
| pods/log | get |
| events | list |
| deployments | get, list |
| replicasets | get, list |
| nodes | get |

No write permissions. No exec. No delete. If the agent crashes, nothing else is affected.

## Deployment models

### Agent Mode
The LLM runs externally (Anthropic, OpenAI, etc.). Only investigation context — pod names, log snippets, metric values — is sent. No raw data export.

### On-Prem Mode
The LLM runs inside your cluster via Ollama, vLLM, or any OpenAI-compatible endpoint. Zero external calls. Suitable for air-gapped environments and regulated industries.
