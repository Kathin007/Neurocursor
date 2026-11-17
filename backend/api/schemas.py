"""Shared wire types: data-source labels, telemetry event envelope, unified command."""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DataSource(StrEnum):
    """Every data source must carry exactly one of these labels, in code and in the UI."""

    REAL_WEBCAM = "REAL_WEBCAM"
    REAL_EEG = "REAL_EEG"
    SYNTHETIC_EEG = "SYNTHETIC_EEG"
    RECORDED_EEG = "RECORDED_EEG"
    DEMO_DATA = "DEMO_DATA"


class Mode(StrEnum):
    VISION = "VISION"
    NEURAL = "NEURAL"


class Action(StrEnum):
    MOVE = "MOVE"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"


EventType = Literal[
    "gaze_update",
    "eeg_update",
    "cursor_update",
    "classification_update",
    "device_status",
    "interaction_event",
    "system_log",
]


def now_ms() -> float:
    """Wall-clock timestamp, milliseconds since the Unix epoch."""
    return time.time() * 1000.0


def _contains_binary(value: Any) -> bool:
    """True if value holds raw bytes or an inline image, i.e. something shaped like a camera frame."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, str):
        return value.startswith("data:image")
    if isinstance(value, dict):
        return any(_contains_binary(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(v) for v in value)
    return False


class TelemetryEvent(BaseModel):
    """Envelope for everything sent over /ws/telemetry. Never carries camera frames."""

    type: EventType
    timestamp: float = Field(default_factory=now_ms)
    source: DataSource | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _no_binary_frames(cls, payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_binary(payload):
            raise ValueError("binary / image data is not allowed on the telemetry channel")
        return payload


class UnifiedCommand(BaseModel):
    """Single command shape both input modes feed into the cursor engine (normalized 0-1)."""

    mode: Mode
    action: Action
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=now_ms)


def log_event(message: str, level: str = "info", **extra: Any) -> TelemetryEvent:
    return TelemetryEvent(type="system_log", payload={"level": level, "message": message, **extra})
