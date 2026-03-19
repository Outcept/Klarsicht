"""Tests for the RCA agent with mocked LLM and tools."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from app.agent.rca_agent import _build_investigation_message, _parse_agent_output, run_investigation
from app.models.alert import Alert

SAMPLE_ALERT = Alert(
    status="firing",
    labels={
        "alertname": "CrashLoopBackOff",
        "namespace": "production",
        "pod": "worker-7d9f8b-xkj2p",
        "severity": "critical",
    },
    annotations={"summary": "Pod is crash looping"},
    startsAt=datetime(2025, 3, 19, 10, 0, 0, tzinfo=timezone.utc),
    fingerprint="abc123",
    values={"B": 5, "C": 1},
)

SAMPLE_AGENT_JSON = {
    "root_cause": {
        "summary": "Missing SECRET_KEY environment variable",
        "confidence": 0.94,
        "category": "misconfiguration",
        "evidence": [
            "Log line: KeyError: 'SECRET_KEY' at app/config.py:42",
            "Pod restart count: 7 in last 15 minutes",
        ],
    },
    "fix_steps": [
        {
            "order": 1,
            "description": "Verify the secret key exists",
            "command": "kubectl get secret app-secrets -n production -o jsonpath='{.data}' | jq 'keys'",
        },
        {
            "order": 2,
            "description": "Add the missing key to the secret",
            "command": "",
        },
    ],
    "postmortem": {
        "timeline": [
            {"timestamp": "2025-03-19T09:58:00Z", "event": "Secret modified"},
            {"timestamp": "2025-03-19T10:00:00Z", "event": "Alert fired"},
        ],
        "impact": "Worker pods unavailable for ~15 minutes",
        "action_items": ["Add pre-deploy checks for required env vars"],
    },
}


def test_build_investigation_message():
    msg = _build_investigation_message(SAMPLE_ALERT)
    assert "CrashLoopBackOff" in msg
    assert "production" in msg
    assert "worker-7d9f8b-xkj2p" in msg
    assert "Pod is crash looping" in msg
    assert "2025-03-19" in msg


def test_parse_agent_output_plain_json():
    text = json.dumps(SAMPLE_AGENT_JSON)
    result = _parse_agent_output(text)
    assert result["root_cause"]["summary"] == "Missing SECRET_KEY environment variable"


def test_parse_agent_output_with_fences():
    text = f"```json\n{json.dumps(SAMPLE_AGENT_JSON)}\n```"
    result = _parse_agent_output(text)
    assert result["root_cause"]["confidence"] == 0.94


def test_parse_agent_output_with_whitespace():
    text = f"\n\n  {json.dumps(SAMPLE_AGENT_JSON)}  \n\n"
    result = _parse_agent_output(text)
    assert result["root_cause"]["category"] == "misconfiguration"


@pytest.mark.asyncio
@patch("app.agent.rca_agent._build_agent")
async def test_run_investigation(mock_build_agent):
    # Mock the agent to return a pre-built response
    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {
        "messages": [AIMessage(content=json.dumps(SAMPLE_AGENT_JSON))]
    }
    mock_build_agent.return_value = mock_agent

    incident_id = uuid4()
    result = await run_investigation(incident_id, SAMPLE_ALERT)

    assert result.incident_id == incident_id
    assert result.alert_name == "CrashLoopBackOff"
    assert result.namespace == "production"
    assert result.pod == "worker-7d9f8b-xkj2p"
    assert result.root_cause is not None
    assert result.root_cause.summary == "Missing SECRET_KEY environment variable"
    assert result.root_cause.confidence == 0.94
    assert result.root_cause.category == "misconfiguration"
    assert len(result.root_cause.evidence) == 2
    assert len(result.fix_steps) == 2
    assert result.fix_steps[0].order == 1
    assert result.postmortem is not None
    assert result.postmortem.impact == "Worker pods unavailable for ~15 minutes"
    assert len(result.postmortem.timeline) == 2
    assert len(result.postmortem.action_items) == 1

    # Verify agent was called with the right message
    call_args = mock_agent.ainvoke.call_args
    messages = call_args[0][0]["messages"]
    assert len(messages) == 1
    assert "CrashLoopBackOff" in messages[0].content


@pytest.mark.asyncio
@patch("app.agent.rca_agent._build_agent")
async def test_run_investigation_unparseable_output(mock_build_agent):
    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {
        "messages": [AIMessage(content="I couldn't figure it out, sorry.")]
    }
    mock_build_agent.return_value = mock_agent

    incident_id = uuid4()
    result = await run_investigation(incident_id, SAMPLE_ALERT)

    # Should gracefully handle non-JSON output
    assert result.root_cause is not None
    assert result.root_cause.confidence == 0.0
    assert result.root_cause.category == "unknown"
    assert "non-parseable" in result.root_cause.summary.lower()
