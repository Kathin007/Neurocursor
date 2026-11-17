"""MediaPipe Face Landmarker wrapper: BGR frame -> (478, 3) normalized landmarks, or None if no face."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from backend.vision.landmark_indices import N_LANDMARKS

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"


class ModelMissing(FileNotFoundError):
    pass


class LandmarkDetector(Protocol):
    def detect(self, image_bgr: np.ndarray, timestamp_ms: float) -> np.ndarray | None: ...
    def close(self) -> None: ...


class MediaPipeLandmarker:
    def __init__(self, model_path: Path = MODEL_PATH) -> None:
        if not model_path.exists():
            raise ModelMissing(
                f"{model_path} not found. Fetch it once with:\n"
                f'  Invoke-WebRequest "{MODEL_URL}" -OutFile "{model_path}"'
            )
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, image_bgr: np.ndarray, timestamp_ms: float) -> np.ndarray | None:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = max(int(timestamp_ms), self._last_ts + 1)  # VIDEO mode requires strictly increasing timestamps
        self._last_ts = ts
        result = self._landmarker.detect_for_video(mp_image, ts)
        if not result.face_landmarks:
            return None
        pts = np.array([(p.x, p.y, p.z) for p in result.face_landmarks[0]], dtype=np.float64)
        return pts if pts.shape[0] >= N_LANDMARKS else None

    def close(self) -> None:
        self._landmarker.close()
