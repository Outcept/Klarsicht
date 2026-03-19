import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.webhook import app

MOCK_ALERT_PAYLOAD = {
    "receiver": "klarsicht",
    "status": "firing",
    "orgId": 1,
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "CrashLoopBackOff",
                "namespace": "production",
                "pod": "worker-7d9f8b-xkj2p",
                "severity": "critical",
            },
            "annotations": {
                "summary": "Pod is crash looping",
            },
            "startsAt": "2025-03-19T10:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "https://grafana.example.com/alerting/grafana/abc123/view",
            "fingerprint": "abc123",
            "values": {"B": 5, "C": 1},
        }
    ],
    "groupLabels": {"alertname": "CrashLoopBackOff"},
    "commonLabels": {"namespace": "production", "severity": "critical"},
    "commonAnnotations": {"summary": "Pod is crash looping"},
    "externalURL": "https://grafana.example.com",
}


@pytest.fixture(autouse=True)
def clear_webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "")
    # Force in-memory mode for tests (no DB)
    import app.webhook as wh
    monkeypatch.setattr(wh, "_use_db", False)


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_healthz(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_receive_alert_no_auth(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/alert", json=MOCK_ALERT_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["alerts_received"] == 1
    assert data["alerts_firing"] == 1
    assert len(data["incidents"]) == 1


@pytest.mark.asyncio
async def test_receive_alert_with_hmac(transport, monkeypatch):
    secret = "test-secret-key"
    monkeypatch.setattr(settings, "webhook_secret", secret)

    body = json.dumps(MOCK_ALERT_PAYLOAD).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/alert",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Grafana-Alerting-Signature": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_reject_missing_signature(transport, monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "some-secret")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/alert", json=MOCK_ALERT_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reject_bad_signature(transport, monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "real-secret")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/alert",
            json=MOCK_ALERT_PAYLOAD,
            headers={"X-Grafana-Alerting-Signature": "bad-sig"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resolved_alert_not_enqueued(transport):
    payload = MOCK_ALERT_PAYLOAD.copy()
    payload["alerts"] = [{**MOCK_ALERT_PAYLOAD["alerts"][0], "status": "resolved"}]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/alert", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["alerts_firing"] == 0
    assert len(data["incidents"]) == 0


@pytest.mark.asyncio
async def test_invalid_payload(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/alert", content=b"not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
