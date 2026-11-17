"""Cursor backends and the engine that applies unified commands to one of them.

SimulatedCursor is the default. OSCursor drives the real mouse through PyAutoGUI and cannot even be constructed
without a valid, session-scoped opt-in from the SafetyManager.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

from backend.control.click_engine import ClickConfig, ClickEngine
from backend.control.safety_manager import OptInRequired, OSCursorOptIn, SafetyManager
from backend.api.schemas import Action, UnifiedCommand

DEFAULT_SCREEN = (1920, 1080)


class CursorBackend(ABC):
    name: str
    screen_size: tuple[int, int]

    @abstractmethod
    def move_to(self, x_px: int, y_px: int) -> None: ...

    @abstractmethod
    def click(self) -> None: ...

    @abstractmethod
    def double_click(self) -> None: ...


@dataclass(frozen=True)
class SimEvent:
    kind: Literal["move", "click", "double_click"]
    x: int
    y: int


class SimulatedCursor(CursorBackend):
    """Records what a real cursor would have done. No OS side effects."""

    name = "SimulatedCursor"

    def __init__(self, screen_size: tuple[int, int] = DEFAULT_SCREEN, history: int = 500) -> None:
        self.screen_size = screen_size
        self.position = (screen_size[0] // 2, screen_size[1] // 2)
        self.events: deque[SimEvent] = deque(maxlen=history)

    def move_to(self, x_px: int, y_px: int) -> None:
        self.position = (x_px, y_px)
        self.events.append(SimEvent("move", x_px, y_px))

    def click(self) -> None:
        self.events.append(SimEvent("click", *self.position))

    def double_click(self) -> None:
        self.events.append(SimEvent("double_click", *self.position))

    def clicks(self) -> list[SimEvent]:
        return [e for e in self.events if e.kind != "move"]


class OSCursor(CursorBackend):
    """Real mouse via PyAutoGUI. Requires an explicit opt-in token valid for the current session."""

    name = "OSCursor"

    def __init__(self, safety: SafetyManager, opt_in: OSCursorOptIn | None, pyautogui_module: Any = None) -> None:
        if not safety.is_valid_opt_in(opt_in):
            raise OptInRequired("OSCursor requires explicit user opt-in for this session")
        if pyautogui_module is None:
            import pyautogui as pyautogui_module  # lazy: the module is never imported unless opted in
        self._pag = pyautogui_module
        self._pag.FAILSAFE = True  # slamming the mouse into a corner aborts; never disabled
        self._pag.PAUSE = 0
        w, h = self._pag.size()
        self.screen_size = (int(w), int(h))

    def move_to(self, x_px: int, y_px: int) -> None:
        self._pag.moveTo(x_px, y_px)

    def click(self) -> None:
        self._pag.click()

    def double_click(self) -> None:
        self._pag.doubleClick()


def create_cursor_backend(kind: str, safety: SafetyManager, opt_in: OSCursorOptIn | None = None,
                          screen_size: tuple[int, int] = DEFAULT_SCREEN) -> CursorBackend:
    if kind == "simulated":
        return SimulatedCursor(screen_size)
    if kind == "os":
        return OSCursor(safety, opt_in)
    raise ValueError(f"unknown cursor backend {kind!r}")


@dataclass(frozen=True)
class EngineResult:
    accepted: bool
    reason: str
    action: Action
    px: tuple[int, int] | None = None


class CursorEngine:
    """Applies UnifiedCommands to a backend, after the safety rules."""

    def __init__(self, backend: CursorBackend, safety: SafetyManager, click_cfg: ClickConfig | None = None) -> None:
        self.backend = backend
        self.safety = safety
        self.clicks = ClickEngine(safety, click_cfg)

    def _to_px(self, x: float, y: float) -> tuple[int, int]:
        w, h = self.backend.screen_size
        return round(x * (w - 1)), round(y * (h - 1))

    def handle(self, cmd: UnifiedCommand, now_ms: float | None = None) -> EngineResult:
        t = cmd.timestamp if now_ms is None else now_ms
        a = cmd.action
        if a == Action.PAUSE:
            self.safety.pause()
            return EngineResult(True, "paused", a)
        if a == Action.RESUME:
            ok = self.safety.resume()
            return EngineResult(ok, "resumed" if ok else "stopped: re-arm required", a)
        if a == Action.STOP:
            self.safety.emergency_stop()
            return EngineResult(True, "emergency stop", a)

        if not self.safety.active:
            return EngineResult(False, f"control {self.safety.state.value.lower()}", a)
        point = self.safety.sanitize_point(cmd.x, cmd.y)
        if point is None:
            return EngineResult(False, "coordinates rejected", a)
        px = self._to_px(*point)

        if a == Action.MOVE:
            self.backend.move_to(*px)
            return EngineResult(True, "moved", a, px)
        # CLICK / DOUBLE_CLICK: the click engine enforces confidence floor and duplicate lockout.
        decision = self.clicks.decide(cmd.confidence, t, cmd.mode)
        if not decision.accepted:
            return EngineResult(False, decision.reason, a, px)
        self.backend.move_to(*px)
        (self.backend.double_click if a == Action.DOUBLE_CLICK else self.backend.click)()
        return EngineResult(True, "clicked", a, px)
