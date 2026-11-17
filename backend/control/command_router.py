"""Routes unified commands from whichever input mode is active into the single cursor engine."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from backend.api.schemas import Mode, UnifiedCommand
from backend.control.cursor_engine import CursorEngine, EngineResult


@dataclass(frozen=True)
class RoutedCommand:
    command: UnifiedCommand
    result: EngineResult


class CommandRouter:
    """Only the active mode may drive the cursor. Both modes share one engine and one safety manager."""

    def __init__(self, engine: CursorEngine, active_mode: Mode = Mode.VISION, history: int = 200) -> None:
        self.engine = engine
        self.active_mode = active_mode
        self.log: deque[RoutedCommand] = deque(maxlen=history)

    def route(self, cmd: UnifiedCommand) -> EngineResult:
        if cmd.mode != self.active_mode:
            result = EngineResult(False, f"mode {cmd.mode.value} is not active", cmd.action)
        else:
            result = self.engine.handle(cmd)
        self.log.append(RoutedCommand(cmd, result))
        return result
