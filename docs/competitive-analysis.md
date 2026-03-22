# Competitive Analysis & Roadmap

## Deep Comparison

### Klarsicht vs IncidentFox

| Dimension | Klarsicht | IncidentFox |
|-----------|-----------|-------------|
| **Approach** | Alert → autonomous RCA with structured output | Alert → Slack thread investigation with follow-ups |
| **Deployment** | Self-hosted only (Helm) | SaaS, VPC, or self-hosted (open core) |
| **Air-gap / local LLM** | Ollama, vLLM, any OpenAI-compatible | Not available |
| **Integrations** | 4 (K8s, Prometheus, Mimir, Grafana) | 40+ (AWS, Datadog, Splunk, GitHub, Jira, ...) |
| **Slack** | Not yet (planned) | Core UX — everything runs in Slack threads |
| **Remediation** | Suggests kubectl commands (read-only) | One-click remediation with human approval |
| **PII handling** | Data stays in cluster (agent mode: only context to LLM) | PII redaction before LLM, secure credential proxy |
| **Postmortem** | Auto-generated with timeline, impact, action items | Yes, within Slack threads |
| **Pricing** | Free to start | Free trial, pricing not public |
| **Setup** | 5 minutes (Helm) | 30 minutes (integrations) |

**Where IncidentFox beats us:**
- 40+ integrations vs our 4 — they cover AWS, Datadog, Splunk, Sentry, Jira
- Slack-native UX — investigation happens where engineers already are
- Remediation actions (write operations) with human-in-the-loop
- Auto-learns your stack from codebase and past incidents
- More mature product with SOC 2 in progress

**Where we beat IncidentFox:**
- Full air-gap with local LLM — they can't do this
- Zero data leaves the cluster in on-prem mode
- 5 minutes vs 30 minutes setup
- No vendor dependency — self-hosted, no SaaS account needed
- Simpler architecture — one pod, one webhook, done
- DACH compliance story (FINMA, BaFin, GDPR) is stronger

**What to learn from them:**
- Slack integration is table stakes — we need it
- Auto-learning from past incidents is brilliant — build an incident memory
- Remediation suggestions should be more actionable
- Screenshot/file analysis in threads — multi-modal investigation

---

### Klarsicht vs K8sGPT

| Dimension | Klarsicht | K8sGPT |
|-----------|-----------|--------|
| **Approach** | Event-driven (webhook → investigation) | Scan-based (CLI/operator scans cluster) |
| **Trigger** | Grafana alert fires | Manual CLI run or operator poll |
| **Prometheus metrics** | Yes, PromQL queries | No |
| **Log analysis** | Yes, container logs + previous | Optional LogAnalyzer |
| **Cross-resource correlation** | Yes (pod → deployment → node → metrics) | No, per-resource analysis only |
| **Postmortem** | Yes, with timeline and action items | No |
| **LLM backends** | Anthropic (+ local LLM planned) | OpenAI, Azure, Gemini, Bedrock, Ollama, LocalAI, 10+ |
| **Output** | Structured JSON with confidence score | Plain text diagnosis |
| **Dashboard** | Yes, React dashboard | No (CLI output) |
| **Deployment** | Helm chart | CLI binary or K8s operator |

**Where K8sGPT beats us:**
- 10+ LLM backends vs our 1 (Anthropic) — Ollama, LocalAI, Gemini, Bedrock, etc.
- 14+ built-in analyzers covering HPA, PDB, NetworkPolicy, Gateway, etc.
- Mature open-source community (8k+ GitHub stars)
- CLI is great for ad-hoc debugging
- Operator mode for continuous monitoring
- Anonymization built-in

**Where we beat K8sGPT:**
- Event-driven vs scan-based — we react to alerts, they poll
- Prometheus metrics integration — we can correlate CPU spikes with crashes
- Cross-resource correlation — we trace from pod to deployment to node to upstream
- Structured postmortems with timeline, impact, action items
- Dashboard with incident history and overview stats
- Grafana webhook integration — seamless alert pipeline
- Confidence scoring on root cause

**What to learn from them:**
- Multi-LLM backend support is essential — especially Ollama/LocalAI for on-prem
- More analyzers — HPA, PDB, NetworkPolicy, Ingress, Gateway
- Anonymization before sending to LLM
- Operator pattern for continuous background analysis (not just alert-driven)

---

### Klarsicht vs Botkube

| Dimension | Klarsicht | Botkube |
|-----------|-----------|---------|
| **Approach** | Autonomous RCA agent | ChatOps platform with AI assistant |
| **Primary UX** | Dashboard + API | Slack/Teams/Discord |
| **RCA** | Fully autonomous investigation | AI assistant helps investigate |
| **Remediation** | Read-only suggestions | Full remediation with runbooks |
| **Multi-cluster** | Single cluster | Multi-cluster management |
| **Integrations** | K8s, Prometheus, Grafana | K8s, Prometheus, Helm, ArgoCD, Flux, Keptn |
| **Postmortem** | Auto-generated | Auto-compiled from investigation |
| **Pricing** | Free to start | Free tier + paid plans |

**Where Botkube beats us:**
- ChatOps in Slack/Teams/Discord — engineers don't leave their chat
- Multi-cluster management
- Remediation automation with runbooks and health checks
- More integrations (Helm, ArgoCD, Flux, Keptn)
- Developer self-service without CLI access
- Mature product with pricing model

**Where we beat Botkube:**
- Fully autonomous — Botkube's AI is an assistant, we're an agent
- Deeper RCA — we correlate logs + metrics + events + deployments
- Air-gap with local LLM
- Simpler setup — no chat platform dependency
- Structured output with confidence scoring

**What to learn from them:**
- Multi-cluster is needed for enterprise
- ChatOps is a distribution channel — meet engineers where they are
- Runbook execution is a natural extension of fix steps
- Custom executor plugins for extensibility

---

### Klarsicht vs Kagent

| Dimension | Klarsicht | Kagent |
|-----------|-----------|--------|
| **Type** | Product (RCA agent) | Framework (build your own agents) |
| **Approach** | Opinionated alert → RCA pipeline | Flexible agent framework |
| **Setup** | Helm install, works immediately | Build and configure your own agents |
| **K8s native** | Yes | Yes (designed for K8s) |
| **Multi-agent** | Single agent | Multi-agent coordination (A2A protocol) |
| **MCP support** | No | Yes, via kmcp companion project |
| **Integrations** | Built-in K8s + Prometheus tools | Build your own via MCP servers |

**Where Kagent beats us:**
- Framework flexibility — build any agent for any task
- Multi-agent coordination via A2A protocol
- MCP server support for tool extensibility
- Open standards (A2A, ADK, MCP) — vendor independent
- Can compose agents that do things beyond RCA

**Where we beat Kagent:**
- Product vs framework — we work out of the box
- No development needed — Helm install and done
- Opinionated pipeline that covers the full RCA flow
- Dashboard, postmortem generation, incident tracking
- Not a build-it-yourself solution

**What to learn from them:**
- MCP protocol for tool extensibility — huge potential
- A2A for multi-agent (e.g., separate agent per namespace or per concern)
- Framework thinking — could we make Klarsicht extensible?

---

## Where Klarsicht Wins Overall

1. **Air-gap / local LLM** — Nobody else does full on-prem with local LLM + Prometheus + postmortems
2. **Zero-config setup** — 5 minutes Helm install, one webhook, done
3. **Structured RCA output** — JSON with confidence score, not chat messages
4. **No data export** — Investigation context only (agent mode), or nothing at all (on-prem)
5. **Simplicity** — One pod, one webhook, one dashboard. No chat dependency, no framework.

## Where Klarsicht Needs to Improve

1. **LLM backends** — Only Anthropic. Need Ollama, OpenAI, Azure, Gemini, Bedrock
2. **Integrations** — 4 vs IncidentFox's 40+. Need Loki, Slack, ArgoCD minimum
3. **Slack/ChatOps** — Not having Slack is a gap. Engineers live there
4. **Remediation** — We only suggest, others execute
5. **Multi-cluster** — Enterprise need, we don't have it
6. **Anonymization** — K8sGPT anonymizes before LLM, we should too
7. **Continuous analysis** — We're alert-driven only, should also scan proactively
8. **Incident memory** — Learn from past incidents to improve future investigations

---

## Roadmap

### Q2 2026 — Foundation

**Must-have for first paying customers:**

- [ ] Multi-LLM backend (Ollama, OpenAI, Azure) — blocks on-prem story
- [ ] Loki integration — LogQL queries, already in most stacks
- [ ] Slack integration — post RCA to incident channel
- [ ] Data anonymization — strip sensitive values before LLM
- [ ] Incident deduplication — don't investigate the same pod 5 times

### Q3 2026 — Enterprise Ready

**Must-have for enterprise pilots:**

- [ ] Multi-cluster support — central dashboard, per-cluster agents
- [ ] Tempo integration — trace correlation for latency issues
- [ ] ArgoCD/Flux integration — deployment correlation
- [ ] RBAC on dashboard — SSO, team-scoped views
- [ ] Retention policies — auto-cleanup old incidents
- [ ] Webhook output — send RCA to any endpoint (Teams, email, Jira)
- [ ] Cert-Manager + Cilium/Hubble integrations

### Q4 2026 — Intelligence Layer

**Differentiation features:**

- [ ] Incident memory — learn from past RCAs, detect patterns
- [ ] Proactive scanning — K8sGPT-style continuous analysis, not just alert-driven
- [ ] Runbook execution — "apply this fix" with approval flow
- [ ] Alert correlation — group related alerts into a single incident
- [ ] SLA tracking — time-to-detect, time-to-investigate, time-to-resolve
- [ ] Cost of downtime estimation per incident

### Q1 2027 — Platform

- [ ] MCP protocol support — extensible tool interface
- [ ] Plugin system — community-built integrations
- [ ] Multi-tenant — managed service offering
- [ ] SOC 2 Type 2 certification
- [ ] Grafana plugin — embed RCA panel directly in dashboards
