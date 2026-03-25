---
title: "CrashLoopBackOff: A Systematic Debugging Guide"
date: 2026-03-22
author: "Klarsicht Team"
readtime: 8
description: "Your pod is crash-looping. Here's the exact sequence of commands to find the root cause in under 5 minutes — and how to automate the entire process."
---

It's 3am. PagerDuty fires. You open your laptop, squint at the screen, and see the words every SRE dreads:

```
NAME                    READY   STATUS             RESTARTS
api-gateway-7f8b9c-x2k  0/1    CrashLoopBackOff   7 (2m ago)
```

Your pod is crash-looping. Kubernetes keeps restarting it. Every restart takes longer because of exponential backoff. Your users are getting 502s.

Here's the systematic approach to debug it — fast.

## Step 1: Check the pod status

```bash
kubectl describe pod api-gateway-7f8b9c-x2k -n production
```

Look for three things:
- **Last State** — `Terminated` with a reason (`Error`, `OOMKilled`, `Completed`)
- **Exit Code** — `1` = app error, `137` = OOMKilled, `139` = segfault
- **Events** — `BackOff`, `FailedScheduling`, `FailedMount`

The exit code tells you the category:

| Exit Code | Meaning | Next Step |
|-----------|---------|-----------|
| 0 | Container completed (shouldn't restart) | Check `restartPolicy` |
| 1 | Application error | Read logs |
| 137 | OOMKilled (SIGKILL) | Check memory limits |
| 139 | Segfault | Check native dependencies |
| 143 | SIGTERM (graceful shutdown failed) | Check shutdown handlers |

## Step 2: Read the logs

```bash
# Current container (might be empty if it crashed instantly)
kubectl logs api-gateway-7f8b9c-x2k -n production

# Previous container (the one that actually crashed)
kubectl logs api-gateway-7f8b9c-x2k -n production --previous
```

> **The previous logs are the important ones.** The current container just started and hasn't crashed yet. The previous one has the error.

Common patterns you'll see:

**Missing environment variable:**
```
KeyError: 'DATABASE_URL'
```
→ Check your ConfigMap, Secret, or Helm values. The variable isn't set.

**Connection refused:**
```
FATAL: failed to connect to postgres:5432
  error: connection refused
```
→ The dependency is down. Check if the upstream service/database is running.

**OOMKilled (no logs, exit code 137):**
```
Last State: Terminated
  Reason: OOMKilled
  Exit Code: 137
```
→ Container hit its memory limit. Check `resources.limits.memory`.

## Step 3: Check events

```bash
kubectl get events -n production --sort-by='.lastTimestamp' | grep api-gateway
```

Events tell you what Kubernetes itself observed:

- `BackOff` — Container keeps crashing, backoff increasing
- `FailedMount` — Volume or Secret couldn't be mounted
- `FailedScheduling` — No node has enough resources
- `Unhealthy` — Readiness/liveness probe failing

## Step 4: Check recent changes

Most CrashLoopBackOffs happen right after a deployment:

```bash
# Recent deployments
kubectl rollout history deployment/api-gateway -n production

# What changed in the last deploy
kubectl describe deployment api-gateway -n production | grep -A5 "Events"
```

If the crash started after a deploy, compare the new image with the old one. Common causes:
- New code requires an env var that wasn't added to the manifest
- New dependency isn't in the container image
- Database migration didn't run

## Step 5: Check resource pressure

```bash
# Node resources
kubectl top nodes

# Pod resource usage (if it stays up long enough)
kubectl top pods -n production
```

If the node is at 90%+ memory, your pod might be getting OOMKilled by the kernel even below its container limit.

## The pattern

90% of CrashLoopBackOffs fall into four categories:

1. **Missing config** (40%) — env var, secret, configmap not set
2. **Dependency down** (25%) — database, Redis, external API unreachable
3. **Resource limits** (20%) — OOMKilled, CPU throttling at startup
4. **Code bug** (15%) — null pointer, unhandled exception, panic

The debugging sequence is always the same: **exit code → logs (previous!) → events → recent changes → resources.**

## Automate it

This is exactly the process Klarsicht automates. When a CrashLoopBackOff alert fires in Grafana:

1. The agent checks pod status, exit code, and restart count
2. Reads both current and previous container logs
3. Pulls Kubernetes events for the pod
4. Queries Prometheus for memory/CPU anomalies
5. Checks recent deployments in the namespace
6. Delivers a root cause analysis with fix steps

What takes you 30-120 minutes at 3am takes Klarsicht under 60 seconds.

We tested this across 154 incidents covering missing env vars, connection failures, OOM kills, schema errors, auth failures, and more. Average confidence: 94.5%.

<div class="callout callout-tip">
<strong>Try it yourself:</strong> Deploy our test scenario to see Klarsicht diagnose a CrashLoopBackOff in real time.

<pre><code>kubectl apply -f https://raw.githubusercontent.com/outcept/Klarsicht/main/examples/test-crashloop.yaml</code></pre>
</div>

---

*Klarsicht is a self-hosted AI agent for Kubernetes root cause analysis. It runs in your cluster, reads your pods and metrics, and delivers structured RCA reports. No data leaves your infrastructure.*
