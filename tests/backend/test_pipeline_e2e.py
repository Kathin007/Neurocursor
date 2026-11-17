"""End to end: scripted face -> features -> calibration -> regression -> smoothing -> router -> SimulatedCursor."""
import numpy as np
import pytest

from backend.api.schemas import Mode
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.safety_manager import SafetyManager
from backend.vision.calibration import CALIBRATION_POINTS, CalibrationCollector
from backend.vision.config import VisionConfig
from backend.vision.pipeline import VisionPipeline
from tests.backend.synthetic_face import BLANK, ScriptedDetector, gaze_to_ratios

SCREEN = (1920, 1080)
FRAME_MS = 33.0


class Rig:
    def __init__(self, cfg: VisionConfig | None = None) -> None:
        self.det = ScriptedDetector()
        self.safety = SafetyManager()
        self.cursor = SimulatedCursor(SCREEN)
        self.router = CommandRouter(CursorEngine(self.cursor, self.safety), Mode.VISION)
        self.pipe = VisionPipeline(self.det, self.router, cfg)
        self.t = 1000.0

    def look(self, x: float, y: float, ear: float = 0.3, **pose: float) -> None:
        self.det.look(*gaze_to_ratios(x, y), ear=ear, **pose)

    def run(self, ms: float, control: bool = True):
        outs = []
        for _ in range(int(ms / FRAME_MS)):
            self.t += FRAME_MS
            outs.append(self.pipe.process(BLANK, self.t, control=control))
        return outs

    def calibrate(self):
        collector = CalibrationCollector(SCREEN)
        for pid, (x, y) in enumerate(CALIBRATION_POINTS):
            self.look(x, y)
            for out in self.run(400, control=False):
                assert out.features is not None
                collector.add(pid, out.features)
        result = collector.fit()
        self.pipe.set_model(result.model)
        return result

    def px(self) -> np.ndarray:
        return np.array(self.cursor.position, dtype=float)

    def target_px(self, x: float, y: float) -> np.ndarray:
        return np.array([x * (SCREEN[0] - 1), y * (SCREEN[1] - 1)])


@pytest.fixture
def rig():
    r = Rig()
    r.calibrate()
    return r


def test_calibration_through_the_real_feature_chain_has_tiny_held_out_error():
    r = Rig()
    res = r.calibrate()
    assert res.n_points == 9 and res.held_out_error_px < 5  # exact synthetic geometry, so near-zero is expected


def test_gaze_drives_the_simulated_cursor_to_the_target(rig):
    for x, y in [(0.25, 0.3), (0.7, 0.65), (0.5, 0.5)]:
        rig.look(x, y)
        rig.run(900)
        assert np.linalg.norm(rig.px() - rig.target_px(x, y)) < 25, (x, y, rig.cursor.position)
    assert rig.cursor.clicks() == [] or all(c.kind == "click" for c in rig.cursor.clicks())


def test_cursor_never_moves_before_calibration():
    r = Rig()
    r.look(0.2, 0.2)
    outs = r.run(500)
    assert all(o.cursor is None for o in outs) and r.cursor.events == type(r.cursor.events)()


def test_dwell_clicks_exactly_once_while_the_gaze_holds_still():
    r = Rig(VisionConfig(blink_click_enabled=False, dwell_ms=1000))
    r.calibrate()
    r.cursor.events.clear()
    r.look(0.6, 0.4)
    outs = r.run(500)  # settle
    assert not any(o.clicks for o in outs)
    outs = r.run(3000)
    clicks = [c for o in outs for c in o.clicks]
    assert len(clicks) == 1 and clicks[0].source == "DWELL" and clicks[0].accepted
    assert len(r.cursor.clicks()) == 1
    progress = [o.dwell_progress for o in outs]
    assert max(progress) == 1.0


def test_blink_clicks_once_at_the_held_cursor_position(rig):
    rig.pipe.set_config(VisionConfig(dwell_enabled=False))
    rig.look(0.4, 0.6)
    rig.run(900)
    before = rig.px().copy()
    rig.look(0.4, 0.6, ear=0.08)  # eyes close...
    closed = rig.run(166)
    rig.look(0.4, 0.6, ear=0.3)  # ...and reopen
    opened = rig.run(300)
    clicks = [c for o in closed + opened for c in o.clicks]
    assert len(clicks) == 1 and clicks[0].source == "BLINK" and clicks[0].accepted
    assert len(rig.cursor.clicks()) == 1
    assert np.linalg.norm(rig.px() - before) < 3  # closing the eyes did not drag the cursor
    assert any(o.blink and o.blink.blink for o in opened)


def test_prolonged_closure_produces_no_click_at_all(rig):
    rig.pipe.set_config(VisionConfig(dwell_enabled=False))
    rig.look(0.5, 0.5)
    rig.run(600)
    rig.look(0.5, 0.5, ear=0.05)
    rig.run(3000)  # eyes shut for 3 s
    rig.look(0.5, 0.5, ear=0.3)
    rig.run(600)
    assert rig.cursor.clicks() == []


def test_blink_with_low_confidence_head_pose_is_rejected_not_executed():
    r = Rig(VisionConfig(dwell_enabled=False))
    r.calibrate()
    r.look(0.5, 0.5, yaw=38)  # head turned far away: quality ~ 0.05
    r.run(600)
    r.look(0.5, 0.5, ear=0.08, yaw=38)
    r.run(166)
    r.look(0.5, 0.5, ear=0.3, yaw=38)
    outs = r.run(300)
    clicks = [c for o in outs for c in o.clicks]
    assert len(clicks) == 1 and not clicks[0].accepted and clicks[0].reason == "confidence below threshold"
    assert r.cursor.clicks() == []


def test_a_blink_right_after_a_dwell_click_hits_the_duplicate_lockout(rig):
    rig.pipe.set_config(VisionConfig(dwell_ms=600, click_lockout_ms=800, blink_refractory_ms=0))
    rig.look(0.3, 0.3)
    rig.run(1000)  # dwell fires during this window
    n = len(rig.cursor.clicks())
    assert n == 1
    rig.look(0.3, 0.3, ear=0.08)
    rig.run(133)
    rig.look(0.3, 0.3, ear=0.3)
    outs = rig.run(133)
    blink_clicks = [c for o in outs for c in o.clicks if c.source == "BLINK"]
    assert blink_clicks and blink_clicks[0].reason == "duplicate click lockout"
    assert len(rig.cursor.clicks()) == n


def test_pause_stops_all_cursor_activity_and_resume_restores_it(rig):
    rig.look(0.3, 0.3)
    rig.run(900)
    rig.safety.pause()
    rig.cursor.events.clear()
    rig.look(0.8, 0.8)
    rig.run(1500)
    assert len(rig.cursor.events) == 0
    rig.safety.resume()
    rig.run(900)
    assert np.linalg.norm(rig.px() - rig.target_px(0.8, 0.8)) < 25


def test_emergency_stop_is_not_undone_by_resume(rig):
    rig.safety.emergency_stop()
    rig.cursor.events.clear()
    rig.look(0.9, 0.2)
    rig.run(1200)
    rig.safety.resume()
    rig.run(1200)
    assert len(rig.cursor.events) == 0


def test_implausible_gaze_estimates_are_dropped_not_clamped_onto_the_screen(rig):
    rig.look(0.5, 0.5)
    rig.run(600)
    rig.cursor.events.clear()
    rig.det.look(0.95, 0.5)  # ratios far outside anything calibrated: regression extrapolates way off-screen
    outs = rig.run(600)
    assert all(o.raw_gaze is None for o in outs)
    assert len(rig.cursor.events) == 0


def test_losing_the_face_never_clicks_or_crashes(rig):
    rig.look(0.5, 0.5)
    rig.run(600)
    rig.cursor.events.clear()
    rig.det.lose_face()
    outs = rig.run(1500)
    assert all(not o.face_found and not o.clicks for o in outs)
    assert len(rig.cursor.events) == 0
    rig.look(0.5, 0.5)
    assert rig.run(200)[-1].face_found


def test_commands_from_an_inactive_mode_are_rejected(rig):
    rig.router.active_mode = Mode.NEURAL
    rig.cursor.events.clear()
    rig.look(0.2, 0.2)
    outs = rig.run(500)
    assert all(o.move_accepted is False for o in outs if o.move_accepted is not None)
    assert len(rig.cursor.events) == 0


def test_sensitivity_gain_extends_reach_around_the_centre():
    r = Rig(VisionConfig(sensitivity=2.0, dwell_enabled=False, blink_click_enabled=False))
    r.calibrate()
    r.look(0.65, 0.5)
    r.run(900)
    assert abs(r.px()[0] - r.target_px(0.8, 0.5)[0]) < 25  # 0.5 + (0.65 - 0.5) * 2
