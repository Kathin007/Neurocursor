"""Adaptive exponential smoothing: P(t) = a * P_new + (1 - a) * P_prev, with a rising with movement speed.

Speed is the magnitude of a low-passed velocity VECTOR (as in the One Euro filter). Frame-to-frame jitter points in
random directions and averages out, so it does not look like movement; a sustained sweep adds up and does.
"""
from __future__ import annotations

import math

VELOCITY_ALPHA = 0.3  # smoothing of the velocity estimate


class AdaptiveEma:
    """Still gaze is smoothed hard (alpha near `alpha`); fast deliberate moves pass through (alpha -> `alpha_max`)."""

    def __init__(self, alpha: float = 0.35, alpha_max: float = 0.9, speed_ref: float = 1.5) -> None:
        self.alpha_max, self.speed_ref = alpha_max, speed_ref
        self.configure(alpha, alpha_max, speed_ref)
        self.reset()

    def configure(self, alpha: float, alpha_max: float | None = None, speed_ref: float | None = None) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        if speed_ref is not None and speed_ref <= 0:
            raise ValueError("speed_ref must be positive")
        self.alpha = alpha
        self.alpha_max = max(alpha, alpha_max if alpha_max is not None else self.alpha_max)
        self.speed_ref = speed_ref if speed_ref is not None else self.speed_ref

    def reset(self) -> None:
        self._out: tuple[float, float] | None = None
        self._raw: tuple[float, float] | None = None
        self._t: float | None = None
        self._vel = (0.0, 0.0)

    def effective_alpha(self, speed: float) -> float:
        """speed in normalized screen units per second."""
        return self.alpha + (self.alpha_max - self.alpha) * min(1.0, speed / self.speed_ref)

    def update(self, x: float, y: float, t_s: float) -> tuple[float, float]:
        if self._out is None or self._raw is None or self._t is None:
            self._out, self._raw, self._t = (x, y), (x, y), t_s
            return x, y
        dt = max(t_s - self._t, 1e-3)
        vx, vy = (x - self._raw[0]) / dt, (y - self._raw[1]) / dt
        self._vel = (self._vel[0] + VELOCITY_ALPHA * (vx - self._vel[0]), self._vel[1] + VELOCITY_ALPHA * (vy - self._vel[1]))
        a = self.effective_alpha(math.hypot(*self._vel))
        self._out = (a * x + (1.0 - a) * self._out[0], a * y + (1.0 - a) * self._out[1])
        self._raw, self._t = (x, y), t_s
        return self._out
