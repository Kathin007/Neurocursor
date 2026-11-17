"""GET /api/system/status."""
from __future__ import annotations

import platform
import sys
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.schemas import now_ms

APP_VERSION = "0.1.0"
router = APIRouter(prefix="/api/system")


class TelemetryStats(BaseModel):
    clients: int
    dropped_events: int


class SystemStatus(BaseModel):
    app: str
    version: str
    milestone: str
    timestamp: float
    uptime_s: float
    python: str
    platform: str
    telemetry: TelemetryStats
    # Subsystems report what is actually implemented; nothing is claimed as connected.
    subsystems: dict[str, str]


@router.get("/status", response_model=SystemStatus)
def system_status(request: Request) -> SystemStatus:
    hub = request.app.state.hub
    return SystemStatus(
        app="neurocursor",
        version=APP_VERSION,
        milestone="M4",
        timestamp=now_ms(),
        uptime_s=round(time.monotonic() - request.app.state.started_at, 3),
        python=sys.version.split()[0],
        platform=platform.platform(),
        telemetry=TelemetryStats(clients=hub.client_count, dropped_events=hub.dropped_events),
        subsystems={
            "vision": request.app.state.vision.state,
            "eeg": request.app.state.eeg.state,
            "cursor": request.app.state.cursor.name,
        },
    )
