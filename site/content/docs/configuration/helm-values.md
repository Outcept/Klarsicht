---
title: Helm Values Reference
weight: 1
---

All configuration is done via Helm values. Here's the complete reference.

## Agent

```yaml
agent:
  image:
    repository: ghcr.io/outcept/klarsicht/agent
    tag: latest
    pullPolicy: Always
  replicas: 1

  # Namespaces to watch (empty = all)
  watchNamespaces: []

  # Prometheus/Mimir endpoint for metrics queries
  # Prometheus: http://prometheus.monitoring.svc:9090
  # Mimir: http://mimir.monitoring.svc:9009/prometheus
  metricsEndpoint: ""

  # LLM configuration
  llmProvider: anthropic    # anthropic, openai, or ollama
  llmApiKey: ""             # API key (set via --set, not in values file)

  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: "1"
      memory: 512Mi
```

## Dashboard

```yaml
dashboard:
  image:
    repository: ghcr.io/outcept/klarsicht/dashboard
    tag: latest
  replicas: 1
  ingress:
    enabled: false
    className: ""           # nginx, haproxy, traefik
    host: ""                # klarsicht.example.com
    tls: []
```

## PostgreSQL

```yaml
postgres:
  enabled: true             # false to use external DB
  image:
    repository: postgres
    tag: "16"
  storage: 5Gi
  storageClassName: ""      # default storage class if empty
  password: ""              # auto-generated if empty

# External database (when postgres.enabled=false)
externalDatabase:
  url: ""                   # postgresql://user:pass@host:5432/klarsicht
```

## Grafana

```yaml
grafana:
  webhookPath: /alert
  webhookSecret: ""         # HMAC-SHA256 shared secret (optional)
```

## Environment variables

The agent reads configuration from environment variables with the `KLARSICHT_` prefix:

| Variable | Description |
|----------|-------------|
| `KLARSICHT_LLM_API_KEY` | LLM API key |
| `KLARSICHT_LLM_PROVIDER` | `anthropic`, `openai`, or `ollama` |
| `KLARSICHT_MIMIR_ENDPOINT` | Prometheus/Mimir URL |
| `KLARSICHT_WATCH_NAMESPACES` | Comma-separated namespace list |
| `KLARSICHT_WEBHOOK_SECRET` | HMAC shared secret |
| `KLARSICHT_DATABASE_URL` | PostgreSQL connection string |
