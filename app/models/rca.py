from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    detail: str


class RootCause(BaseModel):
    summary: str
    confidence: float
    category: str
    evidence: list[str]


class FixStep(BaseModel):
    order: int
    description: str
    command: str = ""


class TimelineEntry(BaseModel):
    # Free-form string — LLMs return varied formats (ISO, "approx 10:30",
    # "T+5min"). Display only; never compared as a datetime.
    timestamp: str = ""
    event: str = ""


class Postmortem(BaseModel):
    timeline: list[TimelineEntry] = []
    impact: str = ""
    action_items: list[str] = []


class RCAResult(BaseModel):
    incident_id: UUID = Field(default_factory=uuid4)
    alert_name: str
    namespace: str
    pod: str
    started_at: datetime
    investigated_at: datetime = Field(default_factory=datetime.utcnow)
    root_cause: RootCause | None = None
    fix_steps: list[FixStep] = []
    postmortem: Postmortem | None = None
