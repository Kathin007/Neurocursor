"""Eye-aspect-ratio blink detection with duration limits and a refractory period."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.vision.landmark_indices import L_EAR, R_EAR


def eye_aspect_ratio(p: np.ndarray) -> float:
    """EAR for six points (corner, upper, upper, corner, lower, lower) in pixel coordinates."""
    vertical = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    horizontal = np.linalg.norm(p[0] - p[3])
    return float(vertical / (2.0 * horizontal)) if horizontal > 1e-6 else 0.0


def landmarks_ear(pts_px: np.ndarray) -> float:
    """Mean EAR of both eyes from a (N, 2+) pixel-space landmark array."""
    right = eye_aspect_ratio(pts_px[list(R_EAR), :2])
    left = eye_aspect_ratio(pts_px[list(L_EAR), :2])
    return (right + left) / 2.0


@dataclass(frozen=True)
class BlinkConfig:
    ear_threshold: float = 0.2  # below this the eye counts as closed
    hysteresis: float = 0.1  # eye reopens above threshold * (1 + hysteresis)
    min_ms: float = 60.0  # shorter closures are noise
    max_ms: float = 400.0  # longer closures are deliberate/prolonged: never a click
    refractory_ms: float = 500.0  # minimum spacing between accepted blinks


@dataclass(frozen=True)
class BlinkResult:
    closed: bool
    blink: bool  # True on the single frame where a valid blink completes
    prolonged: bool  # closure exceeded max_ms
    duration_ms: float | None = None


class BlinkDetector:
    """A blink fires once, on reopening, if its duration is within [min_ms, max_ms] and outside the refractory window.

    A closure longer than max_ms is marked prolonged and produces no click, however long it lasts.
    """

    def __init__(self, cfg: BlinkConfig | None = None) -> None:
        self.cfg = cfg or BlinkConfig()
        self._state = "open"  # open | closing | prolonged
        self._closed_at = 0.0
        self._last_blink_at: float | None = None

    def reset(self) -> None:
        self._state = "open"

    def update(self, ear: float | None, t_ms: float) -> BlinkResult:
        if ear is None:  # tracking lost: never infer a blink from missing data
            self.reset()
            return BlinkResult(False, False, False)
        cfg = self.cfg
        reopen = cfg.ear_threshold * (1.0 + cfg.hysteresis)

        if self._state == "open":
            if ear < cfg.ear_threshold:
                self._state, self._closed_at = "closing", t_ms
                return BlinkResult(True, False, False)
            return BlinkResult(False, False, False)

        if ear > reopen:
            duration = t_ms - self._closed_at
            was_prolonged = self._state == "prolonged"
            self._state = "open"
            valid = (
                not was_prolonged
                and cfg.min_ms <= duration <= cfg.max_ms
                and (self._last_blink_at is None or t_ms - self._last_blink_at >= cfg.refractory_ms)
            )
            if valid:
                self._last_blink_at = t_ms
            return BlinkResult(False, valid, was_prolonged or duration > cfg.max_ms, duration)

        if self._state == "closing" and t_ms - self._closed_at > cfg.max_ms:
            self._state = "prolonged"
        return BlinkResult(True, False, self._state == "prolonged")
