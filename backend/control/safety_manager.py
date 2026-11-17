"""Safety rules enforced in code (not only in the UI): control state, coordinate sanitising, OS-cursor opt-in.

M3 scope: state machine, coordinate validation/clamping, click-confidence floor and the OS-cursor opt-in token.
Global hotkey, device-disconnect policy wiring and recording consent are completed in M5.
"""
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from enum import StrEnum

from backend.api.schemas import Mode

SAFE_MARGIN = 0.01  # clamp inside [0.01, 0.99]: never reach the exact corners (PyAutoGUI failsafe lives there)
IMPLAUSIBLE_OVERSHOOT = 0.25  # estimates further than this outside the screen are rejected, not clamped
DEFAULT_MIN_CLICK_CONFIDENCE = 0.6


class ControlState(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"  # emergency stop: only an explicit rearm() resumes control


class OptInRequired(PermissionError):
    """Raised when something tries to obtain the real OS cursor without a valid opt-in for this session."""


@dataclass(frozen=True)
class OSCursorOptIn:
    """Proof that the user opted in to real OS cursor control in the current session."""

    session_id: str
    _nonce: str


class SafetyManager:
    def __init__(self, min_click_confidence: float = DEFAULT_MIN_CLICK_CONFIDENCE) -> None:
        self.min_click_confidence = min_click_confidence  # default floor
        self.mode_floors: dict[Mode, float] = {}  # per-mode override: confidence means different things in VISION and NEURAL
        self.state = ControlState.ACTIVE
        self._session_id = secrets.token_hex(8)
        self._nonce: str | None = None

    # ---- control state -------------------------------------------------
    def pause(self) -> None:
        if self.state == ControlState.ACTIVE:
            self.state = ControlState.PAUSED

    def resume(self) -> bool:
        """Resume from PAUSED. Returns False (and stays stopped) after an emergency stop."""
        if self.state == ControlState.PAUSED:
            self.state = ControlState.ACTIVE
        return self.state == ControlState.ACTIVE

    def emergency_stop(self) -> None:
        self.state = ControlState.STOPPED
        self.revoke_os_cursor()

    def rearm(self) -> None:
        if self.state == ControlState.STOPPED:
            self.state = ControlState.PAUSED  # re-arm lands paused: a second, deliberate resume is required

    @property
    def active(self) -> bool:
        return self.state == ControlState.ACTIVE

    # ---- coordinates ---------------------------------------------------
    @staticmethod
    def sanitize_point(x: float, y: float) -> tuple[float, float] | None:
        """None for non-finite or implausibly far-off estimates; otherwise clamped to the safe bounds."""
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        lo, hi = -IMPLAUSIBLE_OVERSHOOT, 1.0 + IMPLAUSIBLE_OVERSHOOT
        if not (lo <= x <= hi and lo <= y <= hi):
            return None
        return min(max(x, SAFE_MARGIN), 1.0 - SAFE_MARGIN), min(max(y, SAFE_MARGIN), 1.0 - SAFE_MARGIN)

    def click_allowed(self, confidence: float, mode: Mode | None = None) -> tuple[bool, str]:
        if not self.active:
            return False, f"control {self.state.value.lower()}"
        floor = self.mode_floors.get(mode, self.min_click_confidence) if mode is not None else self.min_click_confidence
        if not (math.isfinite(confidence) and confidence >= floor):
            return False, "confidence below threshold"
        return True, "ok"

    # ---- OS cursor opt-in ---------------------------------------------
    def grant_os_cursor_opt_in(self) -> OSCursorOptIn:
        """Called only from an explicit, user-initiated UI action. Valid for the current session only."""
        self._nonce = secrets.token_hex(16)
        return OSCursorOptIn(self._session_id, self._nonce)

    def is_valid_opt_in(self, token: OSCursorOptIn | None) -> bool:
        return (
            token is not None
            and self._nonce is not None
            and token.session_id == self._session_id
            and secrets.compare_digest(token._nonce, self._nonce)
        )

    def revoke_os_cursor(self) -> None:
        self._nonce = None

    def new_session(self) -> None:
        """Starts a new session: every earlier opt-in becomes invalid."""
        self._session_id = secrets.token_hex(8)
        self._nonce = None
