"""Dwell selection: hold the cursor still within a radius for dwell_ms to click (fallback click method)."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DwellState:
    progress: float  # 0-1
    fired: bool  # True only on the frame the dwell completes


class DwellController:
    """After firing, the controller disarms until the cursor leaves the radius, so holding still never repeats clicks."""

    def __init__(self, dwell_ms: float = 1200.0, radius: float = 0.03) -> None:
        self.dwell_ms = dwell_ms
        self.radius = radius
        self.reset()

    def reset(self) -> None:
        self._anchor: tuple[float, float] | None = None
        self._since = 0.0
        self._armed = True

    def update(self, x: float, y: float, t_ms: float) -> DwellState:
        if self._anchor is None or math.hypot(x - self._anchor[0], y - self._anchor[1]) > self.radius:
            self._anchor, self._since, self._armed = (x, y), t_ms, True
            return DwellState(0.0, False)
        if not self._armed:
            return DwellState(1.0, False)
        progress = min(1.0, (t_ms - self._since) / self.dwell_ms)
        if progress >= 1.0:
            self._armed = False
            return DwellState(1.0, True)
        return DwellState(progress, False)
