"""/api/eeg/*"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.schemas import TelemetryEvent, log_event
from backend.eeg.device_manager import KINDS, DeviceError
from backend.eeg.pipeline import EEGConfig
from backend.eeg.preprocessing import FilterConfig
from backend.eeg.service import EEGService
from backend.eeg.ssvep_classifier import DEFAULT_TARGETS, ClassifierConfig

router = APIRouter(prefix="/api/eeg")


class ConnectRequest(BaseModel):
    kind: Literal["injected_synthetic", "brainflow_synthetic", "playback", "brainflow_real"] = "injected_synthetic"
    target_hz: float | None = Field(None, gt=0, le=60, description="injected_synthetic: ground-truth SSVEP target")
    seed: int = 0
    file: str | None = None
    master_board_id: int | None = None
    board_id: int | None = None
    serial_port: str = ""
    ip_address: str = ""


class StartRequest(BaseModel):
    targets: dict[str, float] | None = None
    window_s: float = Field(2.0, ge=1.0, le=6.0)
    hop_s: float = Field(0.25, ge=0.05, le=1.0)
    consistent_n: int = Field(3, ge=1, le=10)
    n_harmonics: int = Field(2, ge=1, le=3)
    min_confidence: float = Field(ClassifierConfig().min_confidence, ge=0.0, le=1.0)
    min_margin: float = Field(ClassifierConfig().min_margin, ge=0.0, le=0.5)
    step: float = Field(0.05, ge=0.005, le=0.25)
    notch_hz: float | None = Field(50.0, description="mains frequency (50 or 60), null to disable")

    def to_config(self) -> EEGConfig:
        targets = dict(self.targets or DEFAULT_TARGETS)
        flt = FilterConfig(notch_hz=self.notch_hz)
        top = max(targets.values()) * self.n_harmonics
        if min(targets.values()) <= flt.low_hz:
            raise DeviceError(422, f"targets must be above the {flt.low_hz} Hz high-pass edge")
        if top >= flt.high_hz:
            raise DeviceError(422, f"{self.n_harmonics} harmonics of {max(targets.values())} Hz reach {top} Hz, above the {flt.high_hz} Hz low-pass")
        hz = sorted(targets.values())
        if any(b - a < 0.5 for a, b in zip(hz, hz[1:])):
            raise DeviceError(422, "target frequencies must differ by at least 0.5 Hz")
        return EEGConfig(
            classifier=ClassifierConfig(targets, self.n_harmonics, self.min_confidence, self.min_margin),
            filter=flt, window_s=self.window_s, hop_s=self.hop_s, consistent_n=self.consistent_n, step=self.step,
        )


def _svc(request: Request) -> EEGService:
    return request.app.state.eeg


def _guard(e: DeviceError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.detail)


@router.get("/status")
def eeg_status(request: Request) -> dict[str, Any]:
    return {**_svc(request).status(), "device_kinds": list(KINDS)}


@router.post("/connect")
async def eeg_connect(request: Request, body: ConnectRequest | None = None) -> dict[str, Any]:
    body = body or ConnectRequest()
    try:
        return await _svc(request).connect(body.kind, body.model_dump())
    except DeviceError as e:
        raise _guard(e) from e


@router.post("/disconnect")
async def eeg_disconnect(request: Request) -> dict[str, Any]:
    return await _svc(request).disconnect()


@router.post("/start")
async def eeg_start(request: Request, body: StartRequest | None = None) -> dict[str, Any]:
    try:
        return await _svc(request).start((body or StartRequest()).to_config())
    except DeviceError as e:
        raise _guard(e) from e


@router.post("/stop")
async def eeg_stop(request: Request) -> dict[str, Any]:
    return await _svc(request).stop()


def set_synthetic_target_handler(service: EEGService):
    """WebSocket client message {"type": "set_synthetic_target", "hz": 12.0 | null}: moves the simulator's ground truth."""

    def handle(msg: dict[str, Any]) -> TelemetryEvent:
        hz = msg.get("hz")
        if hz is not None and not (isinstance(hz, (int, float)) and 0 < hz <= 60):
            return log_event("invalid synthetic target", level="warning")
        if not service.set_synthetic_target(None if hz is None else float(hz)):
            return log_event("synthetic target only applies to the injected_synthetic source", level="warning")
        return log_event("synthetic target set", injected_target_hz=hz)

    return handle
