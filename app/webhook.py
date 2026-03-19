import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import ValidationError

from app.agent.rca_agent import run_investigation
from app.config import settings
from app.models.alert import Alert, GrafanaWebhookPayload
from app.models.rca import RCAResult

logger = logging.getLogger(__name__)

# In-memory fallback when no database_url is configured
_memory_store: dict[str, RCAResult | None] = {}
_use_db = bool(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _use_db:
        from app.db import close_db, init_db
        await init_db()
    yield
    if _use_db:
        from app.db import close_db
        await close_db()


app = FastAPI(title="Klarsicht", version="0.1.0", lifespan=lifespan)


def verify_hmac_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _run_and_store(incident_id: UUID, alert: Alert) -> None:
    """Run RCA investigation in the background and store the result."""
    try:
        result = await run_investigation(incident_id, alert)
        if _use_db:
            from app.db import save_rca_result
            await save_rca_result(incident_id, result)
        else:
            _memory_store[str(incident_id)] = result
    except Exception:
        logger.exception("Investigation failed for incident %s", incident_id)
        if _use_db:
            from app.db import mark_incident_failed
            await mark_incident_failed(incident_id)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/alert")
async def receive_alert(
    request: Request,
    x_grafana_alerting_signature: str | None = Header(default=None),
):
    body = await request.body()

    if settings.webhook_secret:
        if not x_grafana_alerting_signature:
            raise HTTPException(status_code=401, detail="Missing signature header")
        if not verify_hmac_signature(body, x_grafana_alerting_signature, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = GrafanaWebhookPayload.model_validate_json(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    incident_ids = []
    for alert in payload.alerts:
        if alert.status != "firing":
            continue

        incident_id = uuid4()
        incident_ids.append(str(incident_id))

        logger.info(
            "Received alert %s for %s/%s — incident %s",
            alert.labels.get("alertname", "unknown"),
            alert.labels.get("namespace", "unknown"),
            alert.labels.get("pod", "unknown"),
            incident_id,
        )

        if _use_db:
            from app.db import create_incident
            await create_incident(
                incident_id,
                alert.labels.get("alertname", "unknown"),
                alert.labels.get("namespace", "unknown"),
                alert.labels.get("pod", "unknown"),
                alert.startsAt,
            )
        else:
            _memory_store[str(incident_id)] = None

        asyncio.create_task(_run_and_store(incident_id, alert))

    return {
        "status": "accepted",
        "incidents": incident_ids,
        "alerts_received": len(payload.alerts),
        "alerts_firing": len(incident_ids),
    }


@app.get("/incidents")
async def list_incidents_endpoint():
    """List all incidents and their investigation status."""
    if _use_db:
        from app.db import list_incidents
        return await list_incidents()

    return {
        iid: {
            "status": "completed" if result is not None else "investigating",
            "result": result.model_dump(mode="json") if result else None,
        }
        for iid, result in _memory_store.items()
    }


@app.get("/incidents/{incident_id}")
async def get_incident_endpoint(incident_id: str):
    """Get a specific incident's RCA result."""
    if _use_db:
        from app.db import get_incident
        try:
            uid = UUID(incident_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid incident ID")
        data = await get_incident(uid)
        if data is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return data

    if incident_id not in _memory_store:
        raise HTTPException(status_code=404, detail="Incident not found")
    result = _memory_store[incident_id]
    return {
        "status": "completed" if result is not None else "investigating",
        "result": result.model_dump(mode="json") if result else None,
    }
