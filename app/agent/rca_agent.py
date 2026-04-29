"""ReAct agent that performs root cause analysis on Kubernetes alerts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from app.agent.prompt import (
    SYSTEM_PROMPT, SYSTEM_PROMPT_NO_METRICS,
    COMPACT_PROMPT, COMPACT_PROMPT_NO_METRICS,
)
from app.agent.tools import get_tools, get_compact_tools
from app.config import settings
from app.models.alert import Alert
from app.models.rca import FixStep, Postmortem, RCAResult, RootCause, TimelineEntry

logger = logging.getLogger(__name__)

# Default models per provider
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "ollama": "llama3.1",
    "watsonx": "ibm/granite-3-8b-instruct",
}


def _openai_extra_body() -> dict[str, Any]:
    """top_k and min_p aren't part of the OpenAI spec; vLLM and Ollama accept
    them via extra_body in the request. Only include params the user set."""
    extra: dict[str, Any] = {}
    if settings.llm_top_k >= 0:
        extra["top_k"] = settings.llm_top_k
    if settings.llm_min_p >= 0:
        extra["min_p"] = settings.llm_min_p
    return extra


def _build_llm() -> BaseChatModel:
    """Build the LLM client based on the configured provider."""
    provider = settings.llm_provider.lower()
    model = settings.llm_model or _DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": settings.llm_api_key,
            "max_tokens": 4096,
            "temperature": settings.llm_temperature,
        }
        if settings.llm_top_p >= 0:
            kwargs["top_p"] = settings.llm_top_p
        if settings.llm_top_k >= 0:
            kwargs["top_k"] = settings.llm_top_k
        # Anthropic API does not support min_p — silently dropped
        return ChatAnthropic(**kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": model, "temperature": settings.llm_temperature, "max_tokens": 4096}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        if settings.llm_top_p >= 0:
            kwargs["top_p"] = settings.llm_top_p
        extra = _openai_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        return ChatOpenAI(**kwargs)

    if provider == "ollama":
        from langchain_openai import ChatOpenAI
        base_url = settings.llm_base_url or "http://ollama.default.svc:11434/v1"
        kwargs = {
            "model": model,
            "base_url": base_url,
            "api_key": "ollama",
            "temperature": settings.llm_temperature,
            "max_tokens": 4096,
        }
        if settings.llm_top_p >= 0:
            kwargs["top_p"] = settings.llm_top_p
        extra = _openai_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        return ChatOpenAI(**kwargs)

    if provider == "watsonx":
        from langchain_ibm import ChatWatsonx
        kwargs = {
            "model_id": model,
            "temperature": settings.llm_temperature,
            "max_tokens": 4096,
        }
        if settings.llm_top_p >= 0:
            kwargs["top_p"] = settings.llm_top_p
        if settings.llm_top_k >= 0:
            kwargs["top_k"] = settings.llm_top_k
        if settings.llm_min_p >= 0:
            kwargs["min_p"] = settings.llm_min_p
        if settings.llm_base_url:
            kwargs["url"] = settings.llm_base_url
        if settings.llm_api_key:
            kwargs["apikey"] = settings.llm_api_key
        if settings.watsonx_project_id:
            kwargs["project_id"] = settings.watsonx_project_id
        # CP4D / on-prem auth
        if settings.watsonx_username:
            kwargs["username"] = settings.watsonx_username
        if settings.watsonx_password:
            kwargs["password"] = settings.watsonx_password
        if settings.watsonx_instance_id:
            kwargs["instance_id"] = settings.watsonx_instance_id
        return ChatWatsonx(**kwargs)

    raise ValueError(f"Unknown LLM provider: {provider}. Use: anthropic, openai, ollama, watsonx")


def _resolve_profile() -> str:
    """Determine the effective LLM profile (full or compact)."""
    profile = settings.llm_profile.lower()
    if profile != "auto":
        return profile

    # Auto-detect based on model name
    model = (settings.llm_model or "").lower()
    # Known small models
    small_patterns = [
        "7b", "8b", "13b", "14b", "20b", "27b", "32b",
        "qwen", "mistral-7", "llama-2-7", "llama-2-13",
        "phi-", "gemma-", "oss-20",
        "granite-3-8b", "granite-3-2b",
    ]
    for pattern in small_patterns:
        if pattern in model:
            return "compact"
    return "full"


def _cluster_addendum() -> str:
    """Build a prompt addendum listing available clusters (backend mode only)."""
    if not settings.is_backend:
        return ""
    from app.cluster_registry import list_agents
    agents = list_agents()
    if not agents:
        return "\n\nNOTE: No cluster agents are registered yet. K8s tools are unavailable until an agent joins.\n"
    lines = ["\n\n## Available clusters\n"]
    lines.append("All K8s/metrics tools require a `cluster` parameter. Use one of these cluster names:\n")
    for a in agents:
        metrics = "yes" if a.has_metrics else "no"
        lines.append(f"- **{a.name}** (metrics: {metrics})")
    return "\n".join(lines) + "\n"


def _build_agent():
    profile = _resolve_profile()
    llm = _build_llm()

    cluster_info = _cluster_addendum()

    if profile == "compact":
        tools = get_compact_tools()
        prompt = COMPACT_PROMPT + cluster_info
        max_calls = settings.llm_max_tool_calls or 8
        logger.info("Agent using %s (model: %s, profile: compact, max_calls: %d, tools: %d)",
                     settings.llm_provider, settings.llm_model or "default", max_calls, len(tools))
    else:
        tools = get_tools()
        base_prompt = SYSTEM_PROMPT if settings.mimir_endpoint else SYSTEM_PROMPT_NO_METRICS
        prompt = base_prompt + cluster_info
        max_calls = settings.llm_max_tool_calls or 20
        logger.info("Agent using %s (model: %s, profile: full, tools: %d)",
                     settings.llm_provider, settings.llm_model or "default", len(tools))

    return create_react_agent(llm, tools, prompt=prompt)


def _build_investigation_message(alert: Alert) -> str:
    """Build the human message that kicks off the investigation."""
    labels = alert.labels
    annotations = alert.annotations
    return (
        f"A Grafana alert has fired. Investigate and determine the root cause.\n\n"
        f"**Alert:** {labels.get('alertname', 'unknown')}\n"
        f"**Status:** {alert.status}\n"
        f"**Severity:** {labels.get('severity', 'unknown')}\n"
        f"**Namespace:** {labels.get('namespace', 'unknown')}\n"
        f"**Pod:** {labels.get('pod', 'unknown')}\n"
        f"**Node:** {labels.get('node', 'unknown')}\n"
        f"**Started at:** {alert.startsAt.isoformat()}\n"
        f"**Summary:** {annotations.get('summary', 'N/A')}\n"
        f"**Description:** {annotations.get('description', 'N/A')}\n"
        f"**Runbook URL:** {annotations.get('runbook_url', 'N/A')}\n"
        f"**Values:** {json.dumps(alert.values)}\n"
        f"**All labels:** {json.dumps(labels)}\n"
    )


def _parse_agent_output(text: str) -> dict[str, Any]:
    """Extract JSON from the agent's final response, even if surrounded by text."""
    text = text.strip()

    # Strip markdown fences if present
    if "```" in text:
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Some models echo the doubled braces from older prompt examples back at us.
    # Collapse runs of {{ → { and }} → } and retry before giving up.
    if "{{" in text or "}}" in text:
        try:
            return json.loads(text.replace("{{", "{").replace("}}", "}"))
        except json.JSONDecodeError:
            pass

    # Find the first { and last } to extract embedded JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return json.loads(candidate.replace("{{", "{").replace("}}", "}"))

    raise json.JSONDecodeError("No JSON object found", text, 0)


def _build_skipped_rca(incident_id: UUID, alert: Alert, namespace: str) -> RCAResult:
    """Synthetic RCA for alerts that target a non-existent namespace."""
    return RCAResult(
        incident_id=incident_id,
        alert_name=alert.labels.get("alertname", "unknown"),
        namespace=namespace,
        pod=alert.labels.get("pod", "unknown"),
        started_at=alert.startsAt,
        investigated_at=datetime.now(timezone.utc),
        root_cause=RootCause(
            summary=f"Alert references namespace '{namespace}' which does not exist on this cluster.",
            confidence=1.0,
            category="stale_alert",
            evidence=[
                f"kubectl get ns {namespace} → not found",
                "No pods, deployments or events to inspect — investigation skipped.",
            ],
        ),
        fix_steps=[
            FixStep(order=1, description="Check the alert source — the workload may have been deleted, the alert may target the wrong cluster, or this may be a test alert."),
            FixStep(order=2, description=f"If the alert is intentional, create the namespace: kubectl create namespace {namespace}", command=f"kubectl create namespace {namespace}"),
        ],
        postmortem=Postmortem(
            timeline=[],
            impact="None — alert target does not exist.",
            action_items=[
                "Update the Grafana alert query/labels to point at a real workload, OR",
                "Silence the alert if it's a leftover from a deleted workload.",
            ],
        ),
    )


def _build_rca_result(
    incident_id: UUID,
    alert: Alert,
    agent_output: dict[str, Any],
) -> RCAResult:
    """Convert parsed agent JSON into an RCAResult model."""
    rc = agent_output.get("root_cause", {})
    root_cause = RootCause(
        summary=rc.get("summary", "Unknown"),
        confidence=rc.get("confidence", 0.0),
        category=rc.get("category", "unknown"),
        evidence=rc.get("evidence", []),
    )

    fix_steps = [
        FixStep(order=s.get("order", i + 1), description=s["description"], command=s.get("command", ""))
        for i, s in enumerate(agent_output.get("fix_steps", []))
    ]

    pm_data = agent_output.get("postmortem", {})
    timeline = []
    for t in pm_data.get("timeline", []):
        if not isinstance(t, dict):
            continue
        ts = t.get("timestamp", "")
        timeline.append(TimelineEntry(timestamp=str(ts) if ts else "", event=t.get("event", "")))
    postmortem = Postmortem(
        timeline=timeline,
        impact=pm_data.get("impact", ""),
        action_items=pm_data.get("action_items", []),
    )

    return RCAResult(
        incident_id=incident_id,
        alert_name=alert.labels.get("alertname", "unknown"),
        namespace=alert.labels.get("namespace", "unknown"),
        pod=alert.labels.get("pod", "unknown"),
        started_at=alert.startsAt,
        investigated_at=datetime.now(timezone.utc),
        root_cause=root_cause,
        fix_steps=fix_steps,
        postmortem=postmortem,
    )


async def run_investigation(incident_id: UUID, alert: Alert) -> RCAResult:
    """Run the full RCA investigation for a single alert."""
    from app.steps import get_progress

    progress = get_progress(str(incident_id))
    logger.info("Starting investigation for incident %s", incident_id)

    ns = alert.labels.get("namespace", "")
    progress.add_step("Alert received", f"{alert.labels.get('alertname', '?')} in {ns or '?'}/{alert.labels.get('pod', '?')}")

    # Short-circuit: if the alert targets a namespace that doesn't exist, skip
    # the LLM call entirely — otherwise the agent runs k8s tools that all 404
    # and the model hallucinates an RCA from empty data.
    if ns and not settings.is_backend:
        from app.tools.k8s import k8s_namespace_exists
        if not k8s_namespace_exists(ns):
            progress.add_step(
                "Namespace not found",
                f"Namespace '{ns}' does not exist on this cluster — likely a stale or test alert.",
                status="done",
            )
            progress.complete("completed")
            return _build_skipped_rca(incident_id, alert, ns)

    agent = _build_agent()
    message = _build_investigation_message(alert)

    progress.add_step("Agent initialized", f"Provider: {settings.llm_provider}, tools: {len(get_tools())}")

    # Stream agent execution to capture tool calls
    progress.add_step("Starting investigation", "ReAct agent running...")

    last_tool = ""
    final_state = None
    async for event in agent.astream(
        {"messages": [HumanMessage(content=message)]},
        stream_mode="updates",
    ):
        # Each event is a dict with node name -> state update
        for node_name, state_update in event.items():
            if node_name == "tools":
                # Tool execution completed — capture full output (capped) so the
                # dashboard execution-trace shows what the agent actually saw.
                msgs = state_update.get("messages", [])
                for msg in msgs:
                    tool_name = getattr(msg, "name", "")
                    content = str(getattr(msg, "content", ""))[:8000]
                    if tool_name:
                        progress.add_step(f"{tool_name} completed", content, tool=tool_name, status="done")

            elif node_name == "agent":
                # Agent decided to call a tool or produce final output
                msgs = state_update.get("messages", [])
                for msg in msgs:
                    tool_calls = getattr(msg, "tool_calls", [])
                    for tc in tool_calls:
                        tool_name = tc.get("name", "unknown")
                        args = tc.get("args", {})
                        try:
                            input_summary = json.dumps(args, default=str)[:2000] if isinstance(args, dict) else str(args)[:2000]
                        except Exception:
                            input_summary = str(args)[:2000]
                        progress.add_step(f"Calling {tool_name}", input_summary, tool=tool_name)

                    # If no tool calls, this is the final response
                    if not tool_calls and hasattr(msg, "content") and msg.content:
                        final_state = msg.content

        # Keep track of final state from last event
        if "agent" in event:
            msgs = event["agent"].get("messages", [])
            if msgs:
                last_msg = msgs[-1]
                if hasattr(last_msg, "content") and last_msg.content and not getattr(last_msg, "tool_calls", []):
                    final_state = last_msg.content

    raw_output = final_state or ""
    progress.add_step("Parsing results", "Extracting RCA from agent output...")

    try:
        agent_output = _parse_agent_output(raw_output)
        progress.add_step("RCA parsed", "Root cause analysis extracted successfully", status="done")
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse agent output: %s", raw_output[:500])
        progress.add_step("Parse failed", "Could not extract JSON from agent output", status="error")
        agent_output = {
            "root_cause": {
                "summary": "Agent produced non-parseable output",
                "confidence": 0.0,
                "category": "unknown",
                "evidence": [f"Raw output: {raw_output[:1000]}"],
            },
            "fix_steps": [],
            "postmortem": {},
        }

    rca = _build_rca_result(incident_id, alert, agent_output)

    summary = rca.root_cause.summary if rca.root_cause else "unknown"
    confidence = (rca.root_cause.confidence * 100) if rca.root_cause else 0
    progress.add_step("Investigation complete", f"{summary} ({confidence:.0f}% confidence)", status="done")
    progress.complete("completed")

    logger.info("Investigation complete for incident %s — %s (%.0f%%)", incident_id, summary, confidence)
    return rca
