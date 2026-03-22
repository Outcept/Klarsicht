---
title: Quick Start
weight: 1
---

Get Klarsicht running in your cluster in under 5 minutes.

## Prerequisites

- Kubernetes cluster (1.26+)
- Helm 3
- Grafana with alerting enabled
- Prometheus (optional, for metrics correlation)

## 1. Install with Helm

```bash
helm install klarsicht oci://registry.gitlab.com/outcept/klarsicht/helm/klarsicht \
  --namespace klarsicht --create-namespace \
  --set agent.llmApiKey=<your-api-key> \
  --set agent.metricsEndpoint=http://prometheus.monitoring.svc:9090
```

This deploys:
- **klarsicht-agent** — FastAPI service that receives webhooks and runs investigations
- **klarsicht-dashboard** — React UI for viewing incidents and RCA results
- **klarsicht-postgres** — PostgreSQL for incident storage

## 2. Configure Grafana

Create a webhook contact point in Grafana:

1. Go to **Alerting → Contact points → Add contact point**
2. Name: `klarsicht`
3. Type: **Webhook**
4. URL: `http://klarsicht-agent.klarsicht.svc:8000/alert`

Set it as the default receiver in **Alerting → Notification policies**.

Or use the one-click setup in the Klarsicht dashboard at `/setup`.

## 3. Test it

Send a test alert to verify the pipeline:

```bash
# Option A: Mock alert via API
curl -X POST http://klarsicht-agent.klarsicht.svc:8000/test

# Option B: Deploy a pod that actually crashes
kubectl apply -f https://gitlab.com/outcept/klarsicht/-/raw/main/examples/test-crashloop.yaml
```

The investigation result will appear in the dashboard within 60 seconds.

## 4. Clean up test

```bash
kubectl delete -f https://gitlab.com/outcept/klarsicht/-/raw/main/examples/test-crashloop.yaml
```

## What's next

- [Architecture Overview](/site/docs/architecture/overview/) — understand how the agent investigates
- [Integrations](/site/docs/integrations/kubernetes/) — configure Prometheus, Grafana
- [Helm Values Reference](/site/docs/configuration/helm-values/) — all configuration options
