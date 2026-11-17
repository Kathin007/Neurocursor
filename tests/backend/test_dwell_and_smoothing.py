import pytest

from backend.control.dwell_controller import DwellController
from backend.control.smoothing import Deadzone, apply_sensitivity
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.safety_manager import SafetyManager
from backend.api.schemas import Action, Mode, UnifiedCommand


def test_dwell_fires_once_after_the_dwell_time_and_progress_is_monotonic():
    d = DwellController(dwell_ms=1000, radius=0.03)
    states = [d.update(0.5, 0.5, t) for t in range(0, 1301, 100)]
    assert [s.fired for s in states].count(True) == 1
    first = next(i for i, s in enumerate(states) if s.fired)
    assert states[first].progress == 1.0 and first == 10  # at t = 1000 ms
    progress = [s.progress for s in states[: first + 1]]
    assert progress == sorted(progress)


def test_holding_still_does_not_repeat_clicks_until_the_cursor_leaves():
    d = DwellController(dwell_ms=500, radius=0.03)
    fires = sum(d.update(0.5, 0.5, t).fired for t in range(0, 5000, 50))
    assert fires == 1
    d.update(0.8, 0.8, 5100)  # leave the radius -> re-arms
    assert sum(d.update(0.8, 0.8, t).fired for t in range(5150, 7000, 50)) == 1


def test_moving_within_the_radius_keeps_the_dwell_but_leaving_restarts_it():
    d = DwellController(dwell_ms=1000, radius=0.03)
    d.update(0.5, 0.5, 0)
    assert d.update(0.51, 0.5, 500).progress == 0.5  # drift inside the radius is tolerated
    assert d.update(0.7, 0.5, 600).progress == 0.0  # jump out: restart
    assert d.update(0.7, 0.5, 1100).progress == 0.5


def test_reset_clears_progress():
    d = DwellController(dwell_ms=1000)
    d.update(0.5, 0.5, 0)
    d.update(0.5, 0.5, 600)
    d.reset()
    assert d.update(0.5, 0.5, 700).progress == 0.0


def test_sensitivity_scales_about_the_centre_and_clamps():
    assert apply_sensitivity(0.5, 0.5, 2.0) == (0.5, 0.5)
    assert apply_sensitivity(0.6, 0.4, 2.0) == pytest.approx((0.7, 0.3))
    assert apply_sensitivity(0.9, 0.1, 3.0) == (1.0, 0.0)
    assert apply_sensitivity(0.7, 0.3, 1.0) == pytest.approx((0.7, 0.3))


def test_deadzone_suppresses_jitter_but_passes_real_moves():
    z = Deadzone(radius=0.01)
    assert z.filter(0.5, 0.5) == (0.5, 0.5)
    assert z.filter(0.503, 0.5) == (0.5, 0.5)
    assert z.filter(0.52, 0.5) == (0.52, 0.5)


def test_router_only_accepts_commands_from_the_active_mode():
    engine = CursorEngine(SimulatedCursor(), SafetyManager())
    router = CommandRouter(engine, active_mode=Mode.VISION)
    mk = lambda m: UnifiedCommand(mode=m, action=Action.MOVE, x=0.4, y=0.4, confidence=1.0)
    assert router.route(mk(Mode.VISION)).accepted
    other = router.route(mk(Mode.NEURAL))
    assert not other.accepted and "not active" in other.reason
    router.active_mode = Mode.NEURAL
    assert router.route(mk(Mode.NEURAL)).accepted
    assert len(router.log) == 3
