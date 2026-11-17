"""/api/vision/* and /api/control/{pause,resume}."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from backend.api.schemas import TelemetryEvent, log_event
from backend.vision.config import VisionConfig
from backend.vision.service import VisionError, VisionService

router = APIRouter()


class StartRequest(BaseModel):
    camera_index: int = Field(0, ge=0, le=8)
    profile_id: int | None = None
    config: VisionConfig | None = None


class CalibrateRequest(BaseModel):
    step: Literal["start", "capture", "finish", "save", "cancel", "load"]
    point_index: int | None = Field(None, ge=0, le=8)
    n_samples: int = Field(25, ge=5, le=120)
    screen_w: int = Field(1920, ge=320, le=16384)
    screen_h: int = Field(1080, ge=240, le=16384)
    name: str = Field("default", min_length=1, max_length=80)
    profile_id: int | None = None


def _service(request: Request) -> VisionService:
    return request.app.state.vision


def _guard(e: VisionError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.detail)


@router.get("/api/vision/status")
def vision_status(request: Request) -> dict[str, Any]:
    return _service(request).status()


@router.post("/api/vision/start")
async def vision_start(request: Request, body: StartRequest | None = None) -> dict[str, Any]:
    body = body or StartRequest()
    try:
        return await _service(request).start(body.camera_index, body.profile_id, body.config)
    except VisionError as e:
        raise _guard(e) from e


@router.post("/api/vision/stop")
async def vision_stop(request: Request) -> dict[str, Any]:
    return await _service(request).stop()


@router.post("/api/vision/calibrate")
async def vision_calibrate(request: Request, body: CalibrateRequest) -> dict[str, Any]:
    svc = _service(request)
    try:
        match body.step:
            case "start":
                return svc.calibration_start(body.screen_w, body.screen_h)
            case "capture":
                if body.point_index is None:
                    raise VisionError(422, "point_index required for capture")
                return await svc.calibration_capture(body.point_index, body.n_samples, svc.capture_timeout_s)
            case "finish":
                return await svc.calibration_finish()
            case "save":
                return svc.calibration_save(body.name)
            case "cancel":
                return svc.calibration_cancel()
            case "load":
                return svc.load_profile(body.profile_id)
    except VisionError as e:
        raise _guard(e) from e


@router.get("/api/vision/preview.mjpg")
async def vision_preview(request: Request) -> StreamingResponse:
    svc = _service(request)
    if svc.state != "RUNNING":
        raise HTTPException(status_code=409, detail="vision is not running")
    return StreamingResponse(svc.preview_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/api/control/pause")
def control_pause(request: Request) -> dict[str, str]:
    safety = request.app.state.safety
    safety.pause()
    return {"control_state": safety.state.value}


@router.post("/api/control/resume")
def control_resume(request: Request) -> dict[str, str]:
    safety = request.app.state.safety
    if not safety.resume():
        raise HTTPException(status_code=409, detail="emergency stop active: re-arm required")
    return {"control_state": safety.state.value}


def set_vision_config_handler(service: VisionService):
    """WebSocket client message {"type": "set_vision_config", "config": {...}}: live tuning from the control room."""

    def handle(msg: dict[str, Any]) -> TelemetryEvent:
        try:
            merged = service.cfg.model_copy(update={}).model_dump() | dict(msg.get("config") or {})
            service.set_config(VisionConfig(**merged))
        except (ValidationError, TypeError) as e:
            return log_event("invalid vision config", level="warning", detail=str(e)[:300])
        return log_event("vision config applied", config=service.cfg.model_dump())

    return handle
