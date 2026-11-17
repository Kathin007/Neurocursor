"""Runs the vision pipeline on a worker thread and publishes telemetry. The camera loop never blocks the event loop."""
from __future__ import annotations

import asyncio
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from backend.api.schemas import DataSource, Mode, TelemetryEvent, log_event, now_ms
from backend.api.telemetry import TelemetryHub
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import SimulatedCursor
from backend.db.store import ProfileStore
from backend.vision.calibration import CALIBRATION_POINTS, CalibrationCollector, CalibrationError, CalibrationResult
from backend.vision.camera import CameraSource
from backend.vision.config import VisionConfig
from backend.vision.face_landmarks import LandmarkDetector
from backend.vision.landmark_indices import L_EAR, L_IRIS, R_EAR, R_IRIS
from backend.vision.pipeline import FrameOutput, VisionPipeline

MAX_CONSECUTIVE_READ_FAILURES = 30
PREVIEW_EVERY_N_FRAMES = 2
MIN_CAPTURE_QUALITY = 0.5


class VisionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class _Capture:
    point: int
    needed: int
    done: asyncio.Future[int]
    loop: asyncio.AbstractEventLoop
    got: int = 0


class VisionService:
    def __init__(self, hub: TelemetryHub, store: ProfileStore, router: CommandRouter, cursor: SimulatedCursor,
                 camera_factory: Callable[[int], CameraSource], detector_factory: Callable[[], LandmarkDetector]) -> None:
        self.hub, self.store, self.router, self.cursor = hub, store, router, cursor
        self._camera_factory, self._detector_factory = camera_factory, detector_factory
        self.state = "IDLE"  # IDLE | RUNNING | ERROR
        self.capture_timeout_s = 8.0
        self.last_error: str | None = None
        self.cfg = VisionConfig()
        self.profile_info: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._camera: CameraSource | None = None
        self._pipeline: VisionPipeline | None = None
        self._source = DataSource.REAL_WEBCAM
        # calibration
        self._collector: CalibrationCollector | None = None
        self._capture: _Capture | None = None
        self._pending: CalibrationResult | None = None
        # measurements
        self._latencies: deque[float] = deque(maxlen=300)
        self._frame_times: deque[float] = deque(maxlen=60)
        self._last_out: FrameOutput | None = None
        self._frames = 0
        # preview
        self._preview_clients = 0
        self._jpeg: bytes | None = None

    # ------------------------------------------------------------------ lifecycle
    async def start(self, camera_index: int = 0, profile_id: int | None = None, cfg: VisionConfig | None = None) -> dict[str, Any]:
        if self.state == "RUNNING":
            raise VisionError(409, "vision already running")
        self._loop = asyncio.get_running_loop()
        self.cfg = cfg or self.cfg
        try:
            detector = await asyncio.to_thread(self._detector_factory)
        except Exception as e:  # model file missing etc.
            raise VisionError(503, f"face landmarker unavailable: {e}") from e
        camera: CameraSource | None = None
        try:
            camera = self._camera_factory(camera_index)
            await asyncio.to_thread(camera.open)
        except Exception as e:
            detector.close()
            if camera is not None:
                camera.close()
            raise VisionError(503, f"camera unavailable: {e}") from e

        profile = self.store.load_profile(profile_id)
        if profile_id is not None and profile is None:
            camera.close(); detector.close()
            raise VisionError(404, f"calibration profile {profile_id} not found")
        self._camera, self._source = camera, camera.source
        self.router.active_mode = Mode.VISION  # one input mode drives the cursor at a time
        self._pipeline = VisionPipeline(detector, self.router, self.cfg, profile.model if profile else None)
        self.profile_info = profile.info() if profile else None
        self._reset_measurements()
        self.state, self.last_error = "RUNNING", None
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="vision-worker", daemon=True)
        self._thread.start()
        self._emit(log_event("vision started" + (f" with calibration profile {profile.id}" if profile else " (uncalibrated)")))
        self._device_status("streaming")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            await asyncio.to_thread(thread.join, 5.0)
        self._thread = None
        self._cleanup()
        if self.state == "RUNNING":
            self.state = "IDLE"
        self._emit(log_event("vision stopped"))
        self._device_status("stopped")
        return self.status()

    def _cleanup(self) -> None:
        if self._camera is not None:
            self._camera.close()
        if self._pipeline is not None:
            self._pipeline.detector.close()
        self._camera, self._pipeline, self._capture = None, None, None
        self._jpeg = None

    def _reset_measurements(self) -> None:
        self._latencies.clear(); self._frame_times.clear(); self._frames = 0; self._last_out = None

    def set_config(self, cfg: VisionConfig) -> None:
        self.cfg = cfg
        if self._pipeline is not None:
            self._pipeline.set_config(cfg)

    # ------------------------------------------------------------------ worker thread
    def _worker(self) -> None:
        failures = 0
        try:
            while not self._stop.is_set():
                assert self._camera is not None and self._pipeline is not None
                frame = self._camera.read()
                if frame is None:
                    failures += 1
                    if failures >= MAX_CONSECUTIVE_READ_FAILURES:
                        raise RuntimeError("camera stopped delivering frames (disconnected?)")
                    time.sleep(0.01)
                    continue
                failures = 0
                t0 = time.perf_counter()
                out = self._pipeline.process(frame.image, frame.timestamp_ms, control=self._collector is None)
                proc_ms = (time.perf_counter() - t0) * 1000.0
                self._frames += 1
                self._frame_times.append(time.perf_counter())
                self._last_out = out
                self._feed_calibration(out)
                self._publish_frame(out, proc_ms)
                if self._preview_clients and self._frames % PREVIEW_EVERY_N_FRAMES == 0:
                    self._jpeg = self._render_preview(frame.image, out)
        except Exception as e:  # device lost or processing crashed: fail safe by pausing control
            self.last_error, self.state = str(e), "ERROR"
            self.router.engine.safety.pause()
            self._emit(log_event(f"vision error: {e}; control paused", level="error"))
            self._device_status("error")

    def _feed_calibration(self, out: FrameOutput) -> None:
        cap, col = self._capture, self._collector
        if cap is None or col is None or out.features is None or out.blink is None or out.blink.closed:
            return
        if out.quality < MIN_CAPTURE_QUALITY:
            return
        col.add(cap.point, out.features)
        cap.got += 1
        if cap.got >= cap.needed:
            self._capture = None
            cap.loop.call_soon_threadsafe(lambda: cap.done.done() or cap.done.set_result(cap.got))

    def _publish_frame(self, out: FrameOutput, proc_ms: float) -> None:
        latency = now_ms() - out.t_ms
        self._latencies.append(latency)
        pose = out.head_pose
        self._emit(TelemetryEvent(type="gaze_update", source=self._source, payload={
            "face_found": out.face_found, "ear": out.ear, "quality": round(out.quality, 3),
            "eyes_closed": bool(out.blink and out.blink.closed), "blink": bool(out.blink and out.blink.blink),
            "head_pose": {"yaw": pose.yaw, "pitch": pose.pitch, "roll": pose.roll} if pose else None,
            "gaze": {"x": out.raw_gaze[0], "y": out.raw_gaze[1]} if out.raw_gaze else None,
            "calibrated": bool(self._pipeline and self._pipeline.model), "dwell": round(out.dwell_progress, 3),
            "fps": self.fps(), "latency_ms": round(latency, 2), "proc_ms": round(proc_ms, 2),
        }))
        if out.cursor is not None:
            x, y = out.cursor
            self._emit(TelemetryEvent(type="cursor_update", source=self._source, payload={
                "x": x, "y": y, "px": list(self.cursor.position), "backend": self.cursor.name,
                "control_state": self.router.engine.safety.state.value,
            }))
        for c in out.clicks:
            self._emit(TelemetryEvent(type="interaction_event", source=self._source, payload={
                "kind": "CLICK", "trigger": c.source, "accepted": c.accepted, "reason": c.reason,
                "confidence": round(c.confidence, 3), "x": c.x, "y": c.y, "latency_ms": round(latency, 2),
            }))

    def _emit(self, event: TelemetryEvent) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.hub.publish, event)

    def _device_status(self, state: str) -> None:
        info = self._camera.info() if self._camera else {}
        self._emit(TelemetryEvent(type="device_status", source=self._source, payload={
            "device": "webcam", "state": state, "error": self.last_error, **info,
        }))

    # ------------------------------------------------------------------ measurements
    def fps(self) -> float:
        ft = self._frame_times
        return round((len(ft) - 1) / (ft[-1] - ft[0]), 1) if len(ft) > 5 and ft[-1] > ft[0] else 0.0

    def status(self) -> dict[str, Any]:
        lat = list(self._latencies)
        out = self._last_out
        return {
            "state": self.state, "source": self._source.value, "last_error": self.last_error,
            "camera": self._camera.info() if self._camera else None,
            "tracking": {
                "face_found": bool(out and out.face_found), "fps": self.fps(), "frames": self._frames,
                "latency_ms_median": round(statistics.median(lat), 2) if lat else None,
                "latency_ms_p95": round(float(np.percentile(lat, 95)), 2) if lat else None,
            },
            "calibration": {
                "calibrated": bool(self._pipeline and self._pipeline.model),
                "active_session": self._collector is not None,
                "unsaved_result": self._pending is not None,
                "profile": self.profile_info,
                "points": [{"x": x, "y": y} for x, y in CALIBRATION_POINTS],
            },
            "control_state": self.router.engine.safety.state.value,
            "cursor_backend": self.cursor.name,
            "config": self.cfg.model_dump(),
        }

    # ------------------------------------------------------------------ calibration
    def _require_running(self) -> VisionPipeline:
        if self.state != "RUNNING" or self._pipeline is None:
            raise VisionError(409, "start vision before calibrating")
        return self._pipeline

    def calibration_start(self, screen_w: int, screen_h: int) -> dict[str, Any]:
        self._require_running()
        self.cursor.screen_size = (screen_w, screen_h)
        self._collector, self._pending, self._capture = CalibrationCollector((screen_w, screen_h)), None, None
        return {"points": [{"x": x, "y": y} for x, y in CALIBRATION_POINTS], "screen": [screen_w, screen_h]}

    async def calibration_capture(self, point_index: int, n_samples: int, timeout_s: float = 8.0) -> dict[str, Any]:
        self._require_running()
        if self._collector is None:
            raise VisionError(409, "calibration not started")
        if not 0 <= point_index < len(CALIBRATION_POINTS):
            raise VisionError(422, "point_index out of range")
        loop = asyncio.get_running_loop()
        cap = _Capture(point_index, n_samples, loop.create_future(), loop)
        self._capture = cap
        try:
            await asyncio.wait_for(cap.done, timeout_s)
        except TimeoutError:
            self._capture = None
            raise VisionError(408, f"only {cap.got}/{n_samples} usable samples (face lost, eyes closed or head turned)") from None
        return {"point_index": point_index, "samples": cap.got, "total_for_point": self._collector.count(point_index)}

    async def calibration_finish(self) -> dict[str, Any]:
        pipeline = self._require_running()
        if self._collector is None:
            raise VisionError(409, "calibration not started")
        collector = self._collector
        try:
            result = await asyncio.to_thread(collector.fit)
        except CalibrationError as e:
            raise VisionError(422, str(e)) from e
        self._pending, self._collector = result, None
        pipeline.set_model(result.model)  # active immediately; persisted only on save
        self._emit(log_event(f"calibration fitted: held-out error {result.held_out_error_px:.1f} px (unsaved)"))
        return {"saved": False, **result.summary()}

    def calibration_save(self, name: str) -> dict[str, Any]:
        if self._pending is None:
            raise VisionError(409, "no fitted calibration to save")
        pid = self.store.save_profile(name, self._pending, self._source.value)
        stored = self.store.load_profile(pid)
        self.profile_info = stored.info() if stored else None
        self._pending = None
        self._emit(log_event(f"calibration profile {pid} saved"))
        return {"saved": True, "profile": self.profile_info}

    def calibration_cancel(self) -> dict[str, Any]:
        self._collector, self._capture, self._pending = None, None, None
        return {"cancelled": True}

    def load_profile(self, profile_id: int | None) -> dict[str, Any]:
        pipeline = self._require_running()
        stored = self.store.load_profile(profile_id)
        if stored is None:
            raise VisionError(404, "calibration profile not found")
        pipeline.set_model(stored.model)
        self.cursor.screen_size = stored.screen
        self.profile_info = stored.info()
        return {"loaded": True, "profile": self.profile_info}

    # ------------------------------------------------------------------ MJPEG preview (video never goes over the WebSocket)
    @staticmethod
    def _render_preview(image: np.ndarray, out: FrameOutput) -> bytes | None:
        img = image.copy()
        if out.landmarks_px is not None:
            for idx in (*R_EAR, *L_EAR):
                cv2.circle(img, tuple(int(v) for v in out.landmarks_px[idx]), 1, (255, 211, 34), -1)
            for idx in (R_IRIS, L_IRIS):
                cv2.circle(img, tuple(int(v) for v in out.landmarks_px[idx]), 3, (246, 92, 139), 1)
        label = f"ear {out.ear:.2f}" if out.ear is not None else "no face"
        cv2.putText(img, label + (" BLINK" if out.blink and out.blink.closed else ""), (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else None

    async def preview_stream(self):
        """Async generator of multipart MJPEG chunks; encodes frames only while a client is connected."""
        self._preview_clients += 1
        try:
            last: bytes | None = None
            while self.state == "RUNNING":
                jpeg = self._jpeg
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
                await asyncio.sleep(1 / 20)
        finally:
            self._preview_clients -= 1
