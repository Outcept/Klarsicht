"""ReAct agent that performs root cause analysis on Kubernetes alerts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from app.agent.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_NO_METRICS
from app.agent.tools import get_tools
from app.config import settings
from app.models.alert import Alert
from app.models.rca import FixStep, Postmortem, RCAResult, RootCause, TimelineEntry

logger = logging.getLogger(__name__)


def _build_agent():
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=settings.llm_api_key,
        max_tokens=4096,
        temperature=0,
    )
    tools = get_tools()
    prompt = SYSTEM_PROMPT if settings.mimir_endpoint else SYSTEM_PROMPT_NO_METRICS
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
    """Run the full RCA investigation for a single alert.

    Args:
        incident_id: Unique ID for this incident.
        alert: The parsed Grafana alert.

    Returns:
        RCAResult with root cause, fix steps, and postmortem.
    """
    logger.info("Starting investigation for incident %s", incident_id)

    agent = _build_agent()
    message = _build_investigation_message(alert)

    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})

    # The final message from the agent contains the RCA JSON
    final_message = result["messages"][-1]
    raw_output = final_message.content

    try:
        agent_output = _parse_agent_output(raw_output)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse agent output: %s", raw_output[:500])
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
    logger.info(
        "Investigation complete for incident %s — root cause: %s (confidence: %.0f%%)",
        incident_id,
        rca.root_cause.summary if rca.root_cause else "unknown",
        (rca.root_cause.confidence * 100) if rca.root_cause else 0,
    )
    return rca
