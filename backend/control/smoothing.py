"""Cursor-side shaping applied after gaze smoothing: sensitivity gain and a jitter dead-zone."""
from __future__ import annotations

import math


def apply_sensitivity(x: float, y: float, gain: float) -> tuple[float, float]:
    """Scale displacement from the screen centre by `gain` (1.0 = unchanged), clamped to the unit square.

    gain > 1 lets modest eye movement reach the screen edges; gain < 1 makes the cursor calmer.
    """
    return (
        min(max(0.5 + (x - 0.5) * gain, 0.0), 1.0),
        min(max(0.5 + (y - 0.5) * gain, 0.0), 1.0),
    )


class Deadzone:
    """Ignores moves smaller than `radius` (normalized) from the last emitted position."""

    def __init__(self, radius: float = 0.004) -> None:
        self.radius = radius
        self._last: tuple[float, float] | None = None

    def reset(self) -> None:
        self._last = None

    def filter(self, x: float, y: float) -> tuple[float, float]:
        if self._last is None or math.hypot(x - self._last[0], y - self._last[1]) >= self.radius:
            self._last = (x, y)
        return self._last
