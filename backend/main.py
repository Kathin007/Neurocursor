"""FastAPI application factory.

Run: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend.api import routes_eeg, routes_system, routes_vision, telemetry
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.safety_manager import SafetyManager
from backend.eeg.acquisition import EEGSource
from backend.db.store import DEFAULT_DB_PATH, ProfileStore
from backend.eeg.device_manager import DeviceManager
from backend.eeg.service import EEGService
from backend.vision.camera import CameraSource, OpenCVCamera
from backend.vision.face_landmarks import LandmarkDetector, MediaPipeLandmarker
from backend.vision.service import VisionService


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    camera_factory: Callable[[int], CameraSource] | None = None,
    detector_factory: Callable[[], LandmarkDetector] | None = None,
    eeg_factory: Callable[[str, dict[str, Any]], EEGSource] | None = None,
) -> FastAPI:
    """Hardware is only touched when /api/vision/start is called. The cursor backend is always SimulatedCursor:
    no route can select OSCursor (its opt-in endpoint is added in M5 pending API-contract approval)."""
    hub = telemetry.TelemetryHub()
    safety = SafetyManager()
    cursor = SimulatedCursor()
    router = CommandRouter(CursorEngine(cursor, safety))
    service = VisionService(
        hub, ProfileStore(db_path), router, cursor,
        camera_factory or (lambda index: OpenCVCamera(index)),
        detector_factory or MediaPipeLandmarker,
    )
    eeg = EEGService(hub, router, cursor, safety, DeviceManager(eeg_factory) if eeg_factory else DeviceManager())
    hub.register_handler("set_vision_config", routes_vision.set_vision_config_handler(service))
    hub.register_handler("set_synthetic_target", routes_eeg.set_synthetic_target_handler(eeg))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await service.stop()  # releases the camera on shutdown
        await eeg.disconnect()  # and the EEG device

    app = FastAPI(title="NEUROCURSOR backend", lifespan=lifespan)
    app.state.hub, app.state.safety, app.state.cursor, app.state.vision = hub, safety, cursor, service
    app.state.eeg = eeg
    app.state.started_at = time.monotonic()
    app.include_router(routes_system.router)
    app.include_router(routes_vision.router)
    app.include_router(routes_eeg.router)
    app.include_router(telemetry.router)
    return app


app = create_app()
