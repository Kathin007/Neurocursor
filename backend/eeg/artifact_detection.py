"""Window-level artifact detection. Simple amplitude rules only: they catch blinks, movement, flat and railed channels,
but NOT subtle muscle or cardiac contamination. Rejection is conservative by design."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class ArtifactConfig:
    max_ptp_uv: float = 150.0  # peak-to-peak above this: blink / movement
    min_std_uv: float = 0.05  # below this: flat (disconnected lead)
    railed_uv: float = 500.0  # absolute value above this: amplifier saturated
    min_good_channels: int = 3


@dataclass
class ArtifactReport:
    bad_channels: dict[int, str] = field(default_factory=dict)  # channel index -> reason
    window_ok: bool = True

    @property
    def reason(self) -> str:
        return "ok" if self.window_ok else f"artifact: {len(self.bad_channels)} bad channels"


def detect_artifacts(window: np.ndarray, cfg: ArtifactConfig | None = None) -> ArtifactReport:
    cfg = cfg or ArtifactConfig()
    bad: dict[int, str] = {}
    for k, ch in enumerate(window):
        if not np.all(np.isfinite(ch)):
            bad[k] = "non-finite"
        elif np.abs(ch).max() > cfg.railed_uv:
            bad[k] = "railed"
        elif np.ptp(ch) > cfg.max_ptp_uv:
            bad[k] = "amplitude"
        elif ch.std() < cfg.min_std_uv:
            bad[k] = "flat"
    return ArtifactReport(bad, window.shape[0] - len(bad) >= cfg.min_good_channels)
