"""Click policy: confidence floor and duplicate-click lockout. Never touches the cursor itself."""
from __future__ import annotations

from dataclasses import dataclass

from backend.api.schemas import Mode
from backend.control.safety_manager import SafetyManager


@dataclass(frozen=True)
class ClickConfig:
    lockout_ms: float = 600.0  # a second click inside this window is rejected as a duplicate


@dataclass(frozen=True)
class ClickDecision:
    accepted: bool
    reason: str


class ClickEngine:
    def __init__(self, safety: SafetyManager, cfg: ClickConfig | None = None) -> None:
        self.safety = safety
        self.cfg = cfg or ClickConfig()
        self._last_click_ms: float | None = None

    def decide(self, confidence: float, t_ms: float, mode: Mode | None = None) -> ClickDecision:
        ok, reason = self.safety.click_allowed(confidence, mode)
        if not ok:
            return ClickDecision(False, reason)
        if self._last_click_ms is not None and 0 <= t_ms - self._last_click_ms < self.cfg.lockout_ms:
            return ClickDecision(False, "duplicate click lockout")
        self._last_click_ms = t_ms
        return ClickDecision(True, "ok")
