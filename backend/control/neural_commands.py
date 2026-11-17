"""Adapter: debounced SSVEP commands -> UnifiedCommands for the shared cursor engine (cursor control side)."""
from __future__ import annotations

from collections.abc import Callable

from backend.api.schemas import Action, Mode, UnifiedCommand

DIRECTIONS: dict[str, tuple[float, float]] = {"up": (0.0, -1.0), "down": (0.0, 1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0)}


class NeuralCommandMapper:
    """Direction targets nudge the cursor by `step` (normalized); `select` clicks where it is.

    The current position comes from the cursor backend, so moves stay correct if something else moved the cursor.
    """

    def __init__(self, get_position: Callable[[], tuple[float, float]], step: float = 0.05) -> None:
        self.get_position, self.step = get_position, step

    def to_command(self, target_id: str, confidence: float, t_ms: float) -> UnifiedCommand | None:
        x, y = self.get_position()
        conf = min(max(confidence, 0.0), 1.0)
        if target_id in DIRECTIONS:
            dx, dy = DIRECTIONS[target_id]
            nx, ny = min(max(x + dx * self.step, 0.0), 1.0), min(max(y + dy * self.step, 0.0), 1.0)
            return UnifiedCommand(mode=Mode.NEURAL, action=Action.MOVE, x=nx, y=ny, confidence=conf, timestamp=t_ms)
        if target_id == "select":
            return UnifiedCommand(mode=Mode.NEURAL, action=Action.CLICK, x=x, y=y, confidence=conf, timestamp=t_ms)
        return None  # unknown target: never guess an action
