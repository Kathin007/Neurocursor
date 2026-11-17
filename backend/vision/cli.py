"""Developer harness for the vision engine, no UI needed.

  python -m backend.vision.cli probe       # camera + landmarker health: measured rates, detection, timings
  python -m backend.vision.cli calibrate   # full-screen 9-point calibration; prints held-out error; saves profile
  python -m backend.vision.cli live        # gaze -> SimulatedCursor with dwell/blink, shown in a window (Esc quits)

`probe` saves nothing. `calibrate` stores model parameters only (never images). The cursor is always simulated.
"""
from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

import cv2
import numpy as np

from backend.api.schemas import Mode
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.safety_manager import SafetyManager
from backend.db.store import DEFAULT_DB_PATH, ProfileStore
from backend.vision.blink_detection import landmarks_ear
from backend.vision.calibration import CALIBRATION_POINTS, CalibrationCollector, CalibrationError
from backend.vision.camera import CameraSource, OpenCVCamera, looks_infrared
from backend.vision.face_landmarks import LandmarkDetector, MediaPipeLandmarker
from backend.vision.gaze_estimation import extract_features
from backend.vision.head_pose import estimate_head_pose
from backend.vision.pipeline import VisionPipeline

WINDOW = "NEUROCURSOR vision"


def probe(camera: CameraSource, detector: LandmarkDetector, frames: int = 90) -> dict[str, Any]:
    """Measured health numbers over `frames` frames. Nothing is stored."""
    for _ in range(8):  # warm-up
        camera.read()
    found, ears, feats, detect_ms, stamps = 0, [], [], [], []
    last = None
    for _ in range(frames):
        f = camera.read()
        if f is None:
            continue
        last = f.image
        stamps.append(time.perf_counter())
        h, w = f.image.shape[:2]
        t0 = time.perf_counter()
        pts = detector.detect(f.image, f.timestamp_ms)
        detect_ms.append((time.perf_counter() - t0) * 1000)
        if pts is None:
            continue
        found += 1
        px = pts[:, :2] * np.array([w, h])
        ears.append(landmarks_ear(px))
        ft = extract_features(px, estimate_head_pose(px, w, h))
        if ft is not None:
            feats.append(ft)
    n = len(stamps)
    out: dict[str, Any] = {
        "frames_read": n,
        "capture_fps": round((n - 1) / (stamps[-1] - stamps[0]), 1) if n > 1 else 0.0,
        "face_detection_rate": round(found / n, 3) if n else 0.0,
        "infrared_like": looks_infrared(last) if last is not None else None,
    }
    if detect_ms:
        out["detect_ms_median"] = round(statistics.median(detect_ms), 1)
        out["detect_ms_p95"] = round(float(np.percentile(detect_ms, 95)), 1)
    if ears:
        out["ear_min_median_max"] = [round(min(ears), 3), round(statistics.median(ears), 3), round(max(ears), 3)]
    if feats:
        names = ("h_ratio", "v_ratio", "yaw", "pitch", "roll")
        arr = np.array(feats)
        out["features_median_std"] = {k: [round(float(np.median(c)), 3), round(float(c.std()), 3)] for k, c in zip(names, arr.T)}
    return out


def _screen_size() -> tuple[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080


def _fullscreen(w: int, h: int) -> np.ndarray:
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    return np.zeros((h, w, 3), dtype=np.uint8)


def _build(detector: LandmarkDetector, screen: tuple[int, int]) -> tuple[VisionPipeline, SimulatedCursor, SafetyManager]:
    safety = SafetyManager()
    cursor = SimulatedCursor(screen)
    return VisionPipeline(detector, CommandRouter(CursorEngine(cursor, safety), Mode.VISION)), cursor, safety


def calibrate(camera: CameraSource, detector: LandmarkDetector, screen: tuple[int, int], samples_per_point: int, db: str) -> int:
    w, h = screen
    pipeline, _, _ = _build(detector, screen)
    collector = CalibrationCollector(screen)
    canvas = _fullscreen(w, h)
    print("Look at each dot and keep your head fairly still. Esc aborts.")
    for pid, (x, y) in enumerate(CALIBRATION_POINTS):
        got, t_start = 0, time.time()
        while got < samples_per_point:
            frame = camera.read()
            img = canvas.copy()
            settled = time.time() - t_start > 1.0  # give the eyes time to land on the dot first
            cv2.circle(img, (int(x * w), int(y * h)), 18, (255, 211, 34) if settled else (246, 92, 139), -1)
            cv2.putText(img, f"point {pid + 1}/9  {got}/{samples_per_point}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)
            cv2.imshow(WINDOW, img)
            if cv2.waitKey(1) == 27:
                cv2.destroyAllWindows()
                print("aborted")
                return 1
            if frame is None or not settled:
                continue
            out = pipeline.process(frame.image, frame.timestamp_ms, control=False)
            if out.features is not None and out.blink and not out.blink.closed and out.quality >= 0.5:
                collector.add(pid, out.features)
                got += 1
            if time.time() - t_start > 12:
                print(f"point {pid + 1}: only {got} usable samples (face lost / eyes closed / head turned)")
                break
    cv2.destroyAllWindows()
    try:
        result = collector.fit()
    except CalibrationError as e:
        print("calibration failed:", e)
        return 1
    s = result.summary()
    print(f"model: degree {s['degree']}, ridge alpha {s['alpha']}")
    print(f"HELD-OUT error (leave-one-point-out): mean {s['held_out_error_px']} px, worst {s['worst_point_error_px']} px "
          f"on a {w}x{h} screen")
    print("per point (px):", s["per_point_error_px"])
    print(f"training error (optimistic): {s['train_error_px']} px | {s['n_samples']} samples over {s['n_points']} points")
    pid = ProfileStore(db).save_profile("cli", result, camera.source.value)
    print(f"saved as profile {pid} in {db}")
    return 0


def live(camera: CameraSource, detector: LandmarkDetector, screen: tuple[int, int], db: str) -> int:
    profile = ProfileStore(db).load_profile()
    if profile is None:
        print("no saved calibration: run `calibrate` first")
        return 1
    w, h = profile.screen
    pipeline, cursor, _ = _build(detector, (w, h))
    pipeline.set_model(profile.model)
    canvas = _fullscreen(w, h)
    print(f"profile {profile.id} (held-out error {profile.held_out_error_px:.0f} px). Dwell + blink clicks are simulated. Esc quits.")
    flash, frames, proc, t_first = 0, 0, [], time.time()
    while True:
        frame = camera.read()
        if frame is not None:
            t0 = time.perf_counter()
            out = pipeline.process(frame.image, frame.timestamp_ms)
            proc.append((time.perf_counter() - t0) * 1000)
            frames += 1
            for c in out.clicks:
                print(f"{c.source:5s} click {'ACCEPTED' if c.accepted else 'rejected: ' + c.reason} (confidence {c.confidence:.2f})")
                flash = 8 if c.accepted else flash
            img = canvas.copy()
            if out.raw_gaze:
                cv2.circle(img, (int(out.raw_gaze[0] * w), int(out.raw_gaze[1] * h)), 14, (246, 92, 139), 2)
            cx, cy = cursor.position
            cv2.circle(img, (cx, cy), 10 + 14 * (flash > 0), (255, 211, 34), -1)
            cv2.ellipse(img, (cx, cy), (28, 28), -90, 0, int(360 * out.dwell_progress), (255, 255, 255), 3)
            flash = max(0, flash - 1)
            cv2.imshow(WINDOW, img)
        if cv2.waitKey(1) == 27:
            break
    cv2.destroyAllWindows()
    secs = time.time() - t_first
    print(f"{frames} frames in {secs:.1f}s ({frames / secs:.1f} fps), pipeline median {statistics.median(proc):.1f} ms, "
          f"simulated clicks: {len(cursor.clicks())}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["probe", "calibrate", "live"])
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--screen", help="WxH, default: detected primary screen")
    ap.add_argument("--samples", type=int, default=25)
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    a = ap.parse_args()
    screen = tuple(int(v) for v in a.screen.lower().split("x")) if a.screen else _screen_size()
    camera, detector = OpenCVCamera(a.camera), MediaPipeLandmarker()
    camera.open()
    try:
        if a.command == "probe":
            for k, v in probe(camera, detector).items():
                print(f"{k}: {v}")
            return 0
        return calibrate(camera, detector, screen, a.samples, a.db) if a.command == "calibrate" else live(camera, detector, screen, a.db)
    except KeyboardInterrupt:  # Ctrl+C in the terminal is a normal way to quit, not a crash
        print("\ninterrupted")
        return 130
    finally:
        cv2.destroyAllWindows()
        camera.close()
        detector.close()


if __name__ == "__main__":
    raise SystemExit(main())
