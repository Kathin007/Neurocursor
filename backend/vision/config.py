"""Runtime-tunable vision settings, validated (used by the REST/WebSocket layer and the pipeline)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VisionConfig(BaseModel):
    sensitivity: float = Field(1.0, ge=0.5, le=3.0, description="cursor gain around screen centre")
    smoothing_alpha: float = Field(0.35, gt=0.0, le=1.0, description="base EMA weight of the new sample")
    smoothing_alpha_max: float = Field(0.9, gt=0.0, le=1.0)
    smoothing_speed_ref: float = Field(1.5, gt=0.0, description="normalized screen units/s at which alpha reaches its max")
    deadzone: float = Field(0.004, ge=0.0, le=0.05)
    dwell_enabled: bool = True
    dwell_ms: float = Field(1200.0, ge=300.0, le=5000.0)
    dwell_radius: float = Field(0.03, gt=0.0, le=0.2)
    blink_click_enabled: bool = True
    ear_threshold: float = Field(0.2, ge=0.05, le=0.4)
    blink_min_ms: float = Field(60.0, ge=0.0, le=500.0)
    blink_max_ms: float = Field(400.0, ge=100.0, le=2000.0)
    blink_refractory_ms: float = Field(500.0, ge=0.0, le=5000.0)
    click_lockout_ms: float = Field(600.0, ge=0.0, le=5000.0)
    min_click_confidence: float = Field(0.6, ge=0.0, le=1.0)
