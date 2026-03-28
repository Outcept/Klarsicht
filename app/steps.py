"""Investigation step tracker — stores live progress for each incident."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    timestamp: float
    event: str
    detail: str = ""
    tool: str = ""
    status: str = "running"  # running, done, error


@dataclass
class InvestigationProgress:
    steps: list[Step] = field(default_factory=list)
    status: str = "investigating"  # investigating, completed, failed
    _waiters: list[asyncio.Event] = field(default_factory=list, repr=False)

    def add_step(self, event: str, detail: str = "", tool: str = "", status: str = "running"):
        self.steps.append(Step(
            timestamp=time.time(),
            event=event,
            detail=detail,
            tool=tool,
            status=status,
        ))
        # Notify all waiters
        for w in self._waiters:
            w.set()
        self._waiters = [asyncio.Event() for _ in self._waiters]

    def complete(self, status: str = "completed"):
        self.status = status
        for w in self._waiters:
            w.set()

    async def wait_for_update(self, timeout: float = 30.0) -> bool:
        """Wait until a new step is added or investigation completes. Returns True if updated."""
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            if event in self._waiters:
                self._waiters.remove(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "steps": [
                {
                    "timestamp": s.timestamp,
                    "event": s.event,
                    "detail": s.detail,
                    "tool": s.tool,
                    "status": s.status,
                }
                for s in self.steps
            ],
        }


# Global store — incident_id -> progress
_progress: dict[str, InvestigationProgress] = {}


def get_progress(incident_id: str) -> InvestigationProgress:
    if incident_id not in _progress:
        _progress[incident_id] = InvestigationProgress()
    return _progress[incident_id]


def cleanup_progress(incident_id: str):
    """Remove progress after investigation is done (keep last 100)."""
    if len(_progress) > 100:
        oldest = sorted(_progress.keys(), key=lambda k: _progress[k].steps[0].timestamp if _progress[k].steps else 0)
        for k in oldest[:len(_progress) - 100]:
            del _progress[k]
