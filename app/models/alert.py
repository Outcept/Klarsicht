from datetime import datetime

from pydantic import BaseModel


class Alert(BaseModel):
    status: str
    labels: dict[str, str]
    annotations: dict[str, str] = {}
    startsAt: datetime
    endsAt: datetime | None = None
    generatorURL: str = ""
    fingerprint: str = ""
    values: dict[str, float] = {}


class GrafanaWebhookPayload(BaseModel):
    receiver: str
    status: str
    orgId: int = 0
    alerts: list[Alert]
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
    externalURL: str = ""
