import math

import pytest

from backend.control.safety_manager import ControlState, SafetyManager


def test_pause_resume_and_emergency_stop_requires_rearm_then_resume():
    s = SafetyManager()
    assert s.active
    s.pause()
    assert s.state == ControlState.PAUSED and not s.active
    assert s.resume() and s.active
    s.emergency_stop()
    assert s.state == ControlState.STOPPED
    assert s.resume() is False and s.state == ControlState.STOPPED  # resume cannot undo an emergency stop
    s.rearm()
    assert s.state == ControlState.PAUSED  # re-arming lands paused
    assert s.resume() and s.active


@pytest.mark.parametrize("pt", [(math.nan, 0.5), (0.5, math.inf), (1.6, 0.5), (0.5, -0.4), (-5, 7)])
def test_non_finite_or_implausible_points_are_rejected(pt):
    assert SafetyManager.sanitize_point(*pt) is None


def test_slightly_out_of_range_points_are_clamped_inside_the_safe_bounds():
    assert SafetyManager.sanitize_point(1.1, -0.1) == (0.99, 0.01)
    assert SafetyManager.sanitize_point(0.0, 1.0) == (0.01, 0.99)  # never the exact corner
    assert SafetyManager.sanitize_point(0.4, 0.6) == (0.4, 0.6)


def test_click_allowed_requires_active_state_and_confidence():
    s = SafetyManager(min_click_confidence=0.6)
    assert s.click_allowed(0.9) == (True, "ok")
    assert s.click_allowed(0.59) == (False, "confidence below threshold")
    assert s.click_allowed(math.nan)[0] is False
    s.pause()
    assert s.click_allowed(1.0) == (False, "control paused")


def test_opt_in_tokens_are_session_scoped_and_revocable():
    s = SafetyManager()
    assert not s.is_valid_opt_in(None)
    token = s.grant_os_cursor_opt_in()
    assert s.is_valid_opt_in(token)
    s.revoke_os_cursor()
    assert not s.is_valid_opt_in(token)

    token = s.grant_os_cursor_opt_in()
    s.new_session()  # opt-in does not carry across sessions
    assert not s.is_valid_opt_in(token)


def test_emergency_stop_revokes_os_cursor_opt_in():
    s = SafetyManager()
    token = s.grant_os_cursor_opt_in()
    s.emergency_stop()
    assert not s.is_valid_opt_in(token)


def test_a_token_from_another_safety_manager_is_not_valid():
    a, b = SafetyManager(), SafetyManager()
    assert not b.is_valid_opt_in(a.grant_os_cursor_opt_in())


def test_click_floor_can_differ_per_mode_without_weakening_the_default():
    from backend.api.schemas import Mode
    s = SafetyManager(min_click_confidence=0.6)
    s.mode_floors[Mode.NEURAL] = 0.3
    assert s.click_allowed(0.35, Mode.NEURAL)[0] is True
    assert s.click_allowed(0.35, Mode.VISION)[0] is False  # vision keeps the 0.6 floor
    assert s.click_allowed(0.35)[0] is False  # no mode given: default floor
    assert s.click_allowed(0.2, Mode.NEURAL) == (False, "confidence below threshold")
