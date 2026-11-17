from collections import namedtuple

import pytest

Size = namedtuple("Size", "width height")

from backend.api.schemas import Action, Mode, UnifiedCommand
from backend.control.cursor_engine import CursorEngine, OSCursor, SimulatedCursor, create_cursor_backend
from backend.control.safety_manager import OptInRequired, SafetyManager


class FakePyAutoGUI:
    """Stands in for pyautogui so no test can ever move the real mouse."""

    FAILSAFE = False
    PAUSE = 0.1

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def size(self):
        return Size(1920, 1080)  # real pyautogui returns a (width, height) namedtuple

    def moveTo(self, x, y): self.calls.append(("move", x, y))
    def click(self): self.calls.append(("click",))
    def doubleClick(self): self.calls.append(("double",))


def cmd(action, x=0.5, y=0.5, conf=0.9, t=0.0):
    return UnifiedCommand(mode=Mode.VISION, action=action, x=x, y=y, confidence=conf, timestamp=t)


def make():
    safety = SafetyManager()
    backend = SimulatedCursor((1000, 500))
    return CursorEngine(backend, safety), backend, safety


# ---------- OSCursor is unreachable without explicit opt-in ----------
def test_os_cursor_cannot_be_constructed_without_opt_in():
    safety = SafetyManager()
    with pytest.raises(OptInRequired):
        OSCursor(safety, None, pyautogui_module=FakePyAutoGUI())


def test_factory_default_is_simulated_and_os_requires_the_token():
    safety = SafetyManager()
    assert isinstance(create_cursor_backend("simulated", safety), SimulatedCursor)
    with pytest.raises(OptInRequired):
        create_cursor_backend("os", safety)
    with pytest.raises(ValueError):
        create_cursor_backend("bogus", safety)


def test_stale_or_foreign_tokens_are_refused():
    a, b = SafetyManager(), SafetyManager()
    old = a.grant_os_cursor_opt_in()
    a.new_session()
    with pytest.raises(OptInRequired):
        OSCursor(a, old, pyautogui_module=FakePyAutoGUI())
    with pytest.raises(OptInRequired):
        OSCursor(b, a.grant_os_cursor_opt_in(), pyautogui_module=FakePyAutoGUI())


def test_with_a_valid_opt_in_os_cursor_keeps_the_pyautogui_failsafe_enabled():
    safety = SafetyManager()
    fake = FakePyAutoGUI()
    cursor = OSCursor(safety, safety.grant_os_cursor_opt_in(), pyautogui_module=fake)
    assert fake.FAILSAFE is True and fake.PAUSE == 0
    assert cursor.screen_size == (1920, 1080)
    cursor.move_to(10, 20)
    cursor.click()
    assert fake.calls == [("move", 10, 20), ("click",)]


def test_no_pyautogui_import_happens_unless_os_cursor_is_opted_in():
    import sys
    sys.modules.pop("pyautogui", None)
    safety = SafetyManager()
    create_cursor_backend("simulated", safety)
    with pytest.raises(OptInRequired):
        create_cursor_backend("os", safety)
    assert "pyautogui" not in sys.modules


# ---------- engine behaviour ----------
def test_move_maps_normalized_to_pixels_on_the_backend_screen():
    eng, backend, _ = make()
    r = eng.handle(cmd(Action.MOVE, 0.0 + 0.5, 0.5))
    assert r.accepted and r.px == (500, 250)  # round(0.5 * 999), round(0.5 * 499)
    assert backend.position == (500, 250)


def test_out_of_range_estimates_are_clamped_or_rejected_before_reaching_the_backend():
    eng, backend, _ = make()
    clamped = eng.handle(UnifiedCommand.model_construct(mode=Mode.VISION, action=Action.MOVE, x=1.1, y=0.5, confidence=1, timestamp=0))
    assert clamped.accepted and clamped.px[0] == round(0.99 * 999)
    rejected = eng.handle(UnifiedCommand.model_construct(mode=Mode.VISION, action=Action.MOVE, x=float("nan"), y=0.5, confidence=1, timestamp=0))
    assert not rejected.accepted and rejected.reason == "coordinates rejected"
    far = eng.handle(UnifiedCommand.model_construct(mode=Mode.VISION, action=Action.MOVE, x=3.0, y=0.5, confidence=1, timestamp=0))
    assert not far.accepted
    assert len(backend.events) == 1


def test_click_below_confidence_threshold_is_never_executed():
    eng, backend, _ = make()
    r = eng.handle(cmd(Action.CLICK, conf=0.3))
    assert not r.accepted and r.reason == "confidence below threshold"
    assert backend.clicks() == []


def test_duplicate_click_lockout():
    eng, backend, _ = make()
    assert eng.handle(cmd(Action.CLICK, t=1000)).accepted
    dup = eng.handle(cmd(Action.CLICK, t=1200))
    assert not dup.accepted and dup.reason == "duplicate click lockout"
    assert eng.handle(cmd(Action.CLICK, t=1700)).accepted
    assert len(backend.clicks()) == 2


def test_double_click_and_pause_resume_stop_actions():
    eng, backend, safety = make()
    assert eng.handle(cmd(Action.DOUBLE_CLICK)).accepted
    assert backend.clicks()[-1].kind == "double_click"

    eng.handle(cmd(Action.PAUSE))
    blocked = eng.handle(cmd(Action.MOVE))
    assert not blocked.accepted and blocked.reason == "control paused"
    assert eng.handle(cmd(Action.RESUME)).accepted
    assert eng.handle(cmd(Action.MOVE)).accepted

    eng.handle(cmd(Action.STOP))
    assert not eng.handle(cmd(Action.RESUME)).accepted
    assert not eng.handle(cmd(Action.MOVE)).accepted
    assert safety.state.value == "STOPPED"
