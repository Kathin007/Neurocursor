"""EEG pipeline -> router -> SimulatedCursor, driven by injected known-frequency signals (simulated time)."""
import numpy as np

from backend.api.schemas import Action, Mode
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.neural_commands import NeuralCommandMapper
from backend.control.safety_manager import SafetyManager
from backend.eeg.motor_imagery import AVAILABLE, MotorImageryClassifier
from backend.eeg.pipeline import EEGConfig, EEGPipeline, select_ssvep_channels
from backend.eeg.simulator import DEFAULT_CHANNELS, SignalModel, SSVEPSimulator
from backend.eeg.ssvep_classifier import ClassifierConfig, DEFAULT_TARGETS
import pytest

FS = 250.0
STRONG = SignalModel(ssvep_uv=8.0)


class Rig:
    def __init__(self, cfg=None, model=STRONG, active=Mode.NEURAL, seed=0):
        self.cfg = cfg or EEGConfig()
        self.safety = SafetyManager()
        self.safety.mode_floors[Mode.NEURAL] = self.cfg.classifier.min_confidence
        self.cursor = SimulatedCursor((1000, 1000))
        self.router = CommandRouter(CursorEngine(self.cursor, self.safety), active)
        self.mapper = NeuralCommandMapper(lambda: (self.cursor.position[0] / 999, self.cursor.position[1] / 999), self.cfg.step)
        self.pipe = EEGPipeline(FS, list(DEFAULT_CHANNELS), self.cfg, self.router, self.mapper, t0_ms=0.0)
        self.sim = SSVEPSimulator(FS, model=model, seed=seed, realtime=False)
        self.outputs = []
        self.run(3.0)  # settle on rest

    def run(self, seconds, target=None):
        self.sim.target_hz = DEFAULT_TARGETS.get(target) if isinstance(target, str) else target
        for _ in range(int(seconds * 10)):
            self.outputs += self.pipe.push(self.sim.read_n(int(0.1 * FS)))
        return self.outputs

    def pos(self):
        return np.array(self.cursor.position, dtype=float)


def test_attending_right_moves_the_cursor_right_and_only_right():
    r = Rig()
    r.cursor.position = (500, 500)
    r.run(8.0, "right")
    x, y = r.pos()
    assert x > 500 + 0.05 * 999 and abs(y - 500) < 1  # at least one 5% step right, no vertical drift
    assert {o.fired for o in r.outputs if o.fired} == {"right"}


def test_each_direction_target_moves_the_cursor_in_its_own_direction():
    for target, axis, sign in [("up", 1, -1), ("down", 1, 1), ("left", 0, -1), ("right", 0, 1)]:
        r = Rig(seed=hash(target) % 1000)
        r.cursor.position = (500, 500)
        r.run(7.0, target)
        delta = r.pos() - 500
        assert sign * delta[axis] > 20 and abs(delta[1 - axis]) < 1, (target, delta)


def test_select_clicks_once_where_the_cursor_is_and_not_again_while_held():
    r = Rig()
    r.cursor.position = (300, 700)
    r.run(10.0, "select")
    clicks = r.cursor.clicks()
    assert len(clicks) == 1 and (clicks[0].x, clicks[0].y) == (300, 700)


def test_rest_produces_no_commands_over_a_long_noise_only_stretch():
    r = Rig()
    r.run(40.0, None)
    assert [o.fired for o in r.outputs if o.fired] == []
    assert len(r.cursor.events) == 0


def test_a_weak_signal_below_the_confidence_threshold_never_acts():
    weak = Rig(model=SignalModel(ssvep_uv=0.3))
    weak.run(20.0, "right")
    assert len(weak.cursor.events) == 0


def test_commands_are_blocked_while_paused_and_after_emergency_stop():
    r = Rig()
    r.safety.pause()
    r.run(8.0, "right")
    assert len(r.cursor.events) == 0
    assert any(o.routed and o.routed.reason == "control paused" for o in r.outputs)
    r.safety.resume()
    r.safety.emergency_stop()
    n = len(r.outputs)
    r.run(6.0, "right")
    assert len(r.cursor.events) == 0 and all(not o.routed.accepted for o in r.outputs[n:] if o.routed)


def test_neural_commands_are_rejected_unless_neural_is_the_active_mode():
    r = Rig(active=Mode.VISION)
    r.run(8.0, "right")
    fired = [o for o in r.outputs if o.fired]
    assert fired and all(not o.routed.accepted and "not active" in o.routed.reason for o in fired)
    assert len(r.cursor.events) == 0


def test_cursor_commands_carry_the_neural_mode_and_timestamps_from_the_stream_clock():
    r = Rig()
    r.run(8.0, "left")
    cmds = [o.command for o in r.outputs if o.command]
    assert cmds and all(c.mode == Mode.NEURAL and c.action == Action.MOVE for c in cmds)
    assert all(a.timestamp < b.timestamp for a, b in zip(cmds, cmds[1:]))


def test_neural_click_floor_is_the_classifier_threshold_but_vision_floor_is_unchanged():
    r = Rig()
    assert r.safety.mode_floors[Mode.NEURAL] == ClassifierConfig().min_confidence
    assert r.safety.click_allowed(0.70, Mode.NEURAL)[0] is True
    assert r.safety.click_allowed(0.62, Mode.NEURAL)[0] is False  # below the neural floor (0.65) ...
    assert r.safety.click_allowed(0.62, Mode.VISION)[0] is True  # ... yet above the unchanged vision floor (0.6)
    assert r.safety.click_allowed(0.50, Mode.VISION)[0] is False


def test_mapper_steps_clamps_and_ignores_unknown_targets():
    m = NeuralCommandMapper(lambda: (0.98, 0.02), step=0.05)
    assert m.to_command("right", 0.9, 0).x == 1.0 and m.to_command("up", 0.9, 0).y == 0.0
    assert m.to_command("select", 0.9, 0).action == Action.CLICK
    assert m.to_command("bogus", 0.9, 0) is None
    assert m.to_command("up", 5.0, 0).confidence == 1.0  # confidence is clamped into [0, 1]


def test_ssvep_channel_selection_prefers_occipital_sites_and_falls_back_to_all():
    assert select_ssvep_channels(["Fz", "C3", "Pz", "PO7", "Oz", "PO8", "F5"]) == [2, 3, 4, 5]
    assert select_ssvep_channels(["Fz", "C3", "Cz"]) == [0, 1, 2]


def test_motor_imagery_is_an_honest_stub():
    assert AVAILABLE is False and MotorImageryClassifier.available is False
    with pytest.raises(NotImplementedError):
        MotorImageryClassifier().classify(np.zeros((4, 250)))


def test_pipeline_telemetry_pieces_arrive_at_their_cadence():
    r = Rig()
    r.run(5.0, "right")
    assert sum(o.quality is not None for o in r.outputs) >= 2  # about once per second
    assert sum(o.spectrum is not None for o in r.outputs) >= 5  # about twice per second
    assert all(o.proc_ms >= 0 for o in r.outputs)
