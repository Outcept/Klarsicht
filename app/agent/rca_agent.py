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

from app.agent.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_NO_METRICS
from app.agent.tools import get_tools
from app.config import settings
from app.models.alert import Alert
from app.models.rca import FixStep, Postmortem, RCAResult, RootCause, TimelineEntry

logger = logging.getLogger(__name__)

# Default models per provider
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "ollama": "llama3.1",
}


def _build_llm() -> BaseChatModel:
    """Build the LLM client based on the configured provider."""
    provider = settings.llm_provider.lower()
    model = settings.llm_model or _DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=settings.llm_api_key,
            max_tokens=4096,
            temperature=0,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": model, "temperature": 0, "max_tokens": 4096}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOpenAI(**kwargs)

    if provider == "ollama":
        from langchain_openai import ChatOpenAI
        base_url = settings.llm_base_url or "http://ollama.default.svc:11434/v1"
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key="ollama",  # ollama doesn't need a real key
            temperature=0,
            max_tokens=4096,
        )

    raise ValueError(f"Unknown LLM provider: {provider}. Use: anthropic, openai, ollama")


def _build_agent():
    llm = _build_llm()
    tools = get_tools()
    prompt = SYSTEM_PROMPT if settings.mimir_endpoint else SYSTEM_PROMPT_NO_METRICS
    logger.info("Agent using %s (model: %s)", settings.llm_provider, settings.llm_model or "default")
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

    # Find the first { and last } to extract embedded JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)


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
    postmortem = Postmortem(
        timeline=[
            TimelineEntry(timestamp=t["timestamp"], event=t["event"])
            for t in pm_data.get("timeline", [])
        ],
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

    progress.add_step("Alert received", f"{alert.labels.get('alertname', '?')} in {alert.labels.get('namespace', '?')}/{alert.labels.get('pod', '?')}")

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
                # Tool execution completed
                msgs = state_update.get("messages", [])
                for msg in msgs:
                    tool_name = getattr(msg, "name", "")
                    content = str(getattr(msg, "content", ""))[:100]
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
                        input_summary = ", ".join(f"{k}={v}" for k, v in args.items())[:150] if isinstance(args, dict) else ""
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
