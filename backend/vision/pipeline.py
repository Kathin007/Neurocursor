"""Frame -> landmarks -> features -> calibration regression -> smoothing -> cursor commands.

Pure of threads and hardware: time is passed in, the detector and cursor are injected, so the whole chain is
testable end to end with scripted landmarks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.api.schemas import Action, Mode, UnifiedCommand
from backend.control.click_engine import ClickConfig
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import EngineResult
from backend.control.dwell_controller import DwellController
from backend.control.smoothing import Deadzone, apply_sensitivity
from backend.vision.blink_detection import BlinkConfig, BlinkDetector, BlinkResult, landmarks_ear
from backend.vision.calibration import GazeModel
from backend.vision.config import VisionConfig
from backend.vision.face_landmarks import LandmarkDetector
from backend.vision.gaze_estimation import extract_features, gaze_quality
from backend.vision.gaze_smoothing import AdaptiveEma
from backend.vision.head_pose import HeadPose, estimate_head_pose


@dataclass(frozen=True)
class ClickOutcome:
    source: str  # BLINK | DWELL
    accepted: bool
    reason: str
    confidence: float
    x: float
    y: float
    t_ms: float


@dataclass
class FrameOutput:
    t_ms: float
    face_found: bool = False
    ear: float | None = None
    blink: BlinkResult | None = None
    head_pose: HeadPose | None = None
    features: np.ndarray | None = None
    quality: float = 0.0
    raw_gaze: tuple[float, float] | None = None  # regression output before smoothing, sanitised
    cursor: tuple[float, float] | None = None  # normalized, after smoothing/sensitivity
    dwell_progress: float = 0.0
    move_accepted: bool | None = None
    clicks: list[ClickOutcome] = field(default_factory=list)
    landmarks_px: np.ndarray | None = None


class VisionPipeline:
    def __init__(self, detector: LandmarkDetector, router: CommandRouter, cfg: VisionConfig | None = None,
                 model: GazeModel | None = None) -> None:
        self.detector = detector
        self.router = router
        self.model = model
        self.blink = BlinkDetector()
        self.smoother = AdaptiveEma()
        self.deadzone = Deadzone()
        self.dwell = DwellController()
        self._last_open_quality = 0.0
        self._last_cursor: tuple[float, float] | None = None
        self.cfg = VisionConfig()
        self.set_config(cfg or VisionConfig())

    def set_config(self, cfg: VisionConfig) -> None:
        self.cfg = cfg
        self.smoother.configure(cfg.smoothing_alpha, cfg.smoothing_alpha_max, cfg.smoothing_speed_ref)
        self.deadzone.radius = cfg.deadzone
        self.dwell.dwell_ms, self.dwell.radius = cfg.dwell_ms, cfg.dwell_radius
        self.blink.cfg = BlinkConfig(cfg.ear_threshold, self.blink.cfg.hysteresis, cfg.blink_min_ms,
                                     cfg.blink_max_ms, cfg.blink_refractory_ms)
        safety = self.router.engine.safety
        safety.min_click_confidence = cfg.min_click_confidence
        self.router.engine.clicks.cfg = ClickConfig(lockout_ms=cfg.click_lockout_ms)

    def set_model(self, model: GazeModel | None) -> None:
        self.model = model
        self.smoother.reset()
        self.deadzone.reset()
        self.dwell.reset()
        self._last_cursor = None

    def _send(self, action: Action, x: float, y: float, conf: float, t_ms: float) -> EngineResult:
        return self.router.route(UnifiedCommand(mode=Mode.VISION, action=action, x=x, y=y, confidence=conf, timestamp=t_ms))

    def process(self, image: np.ndarray, t_ms: float, control: bool = True) -> FrameOutput:
        """`control=False` computes everything but sends nothing to the cursor (used while calibrating)."""
        out = FrameOutput(t_ms)
        lm = self.detector.detect(image, t_ms)
        if lm is None:
            self.blink.update(None, t_ms)
            self.dwell.reset()
            return out
        h, w = image.shape[:2]
        px = lm[:, :2] * np.array([w, h], dtype=np.float64)
        out.face_found, out.landmarks_px = True, px
        out.ear = landmarks_ear(px)
        out.blink = self.blink.update(out.ear, t_ms)
        out.head_pose = estimate_head_pose(px, w, h)
        out.features = extract_features(px, out.head_pose)
        out.quality = gaze_quality(out.ear, out.head_pose)
        if not out.blink.closed:
            self._last_open_quality = out.quality

        if control and self.model is not None and out.features is not None and not out.blink.closed:
            self._move(out, t_ms)
        out.cursor = self._last_cursor

        if control and out.cursor is not None:
            cx, cy = out.cursor
            if out.blink.blink and self.cfg.blink_click_enabled:
                # Confidence comes from the last open-eye frame: while the eye is closed quality is 0 by definition.
                out.clicks.append(self._click("BLINK", cx, cy, self._last_open_quality, t_ms))
            if self.cfg.dwell_enabled and self.router.engine.safety.active and not out.blink.closed:
                state = self.dwell.update(cx, cy, t_ms)
                out.dwell_progress = state.progress
                if state.fired:
                    out.clicks.append(self._click("DWELL", cx, cy, out.quality, t_ms))
            elif not self.router.engine.safety.active:
                self.dwell.reset()
        return out

    def _move(self, out: FrameOutput, t_ms: float) -> None:
        assert self.model is not None and out.features is not None
        gx, gy = self.model.predict(out.features)
        safe = self.router.engine.safety.sanitize_point(gx, gy)
        if safe is None:  # NaN or implausibly far outside the screen: drop the sample
            out.move_accepted = False
            return
        out.raw_gaze = safe
        sx, sy = self.smoother.update(*safe, t_ms / 1000.0)
        sx, sy = apply_sensitivity(sx, sy, self.cfg.sensitivity)
        sx, sy = self.deadzone.filter(sx, sy)
        result = self._send(Action.MOVE, sx, sy, out.quality, t_ms)
        out.move_accepted = result.accepted
        if result.accepted:
            self._last_cursor = (sx, sy)

    def _click(self, source: str, x: float, y: float, conf: float, t_ms: float) -> ClickOutcome:
        result = self._send(Action.CLICK, x, y, conf, t_ms)
        return ClickOutcome(source, result.accepted, result.reason, conf, x, y, t_ms)
