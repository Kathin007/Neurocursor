"""Camera acquisition. Hardware access lives here and nowhere else; frames are never stored."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from backend.api.schemas import DataSource


@dataclass(frozen=True)
class Frame:
    image: np.ndarray  # BGR
    timestamp_ms: float  # wall clock at capture


class CameraSource(Protocol):
    source: DataSource

    def open(self) -> None: ...
    def read(self) -> Frame | None: ...
    def close(self) -> None: ...
    def info(self) -> dict[str, object]: ...


def looks_infrared(image: np.ndarray, tolerance: float = 3.0) -> bool:
    """IR cameras report near-identical B/G/R channels (monochrome); a colour webcam does not."""
    if image.ndim != 3 or image.shape[2] != 3:
        return True
    b, g, r = (image[..., i].astype(np.int16) for i in range(3))
    return float(np.abs(b - g).mean() + np.abs(g - r).mean()) < tolerance


class OpenCVCamera:
    """A real webcam through OpenCV (DirectShow on Windows: opens quickly and honours buffer settings)."""

    source = DataSource.REAL_WEBCAM

    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index, self.width, self.height = index, width, height
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        api = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, api)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"could not open camera {self.index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always work on the newest frame
        self._cap = cap

    def read(self) -> Frame | None:
        if self._cap is None:
            return None
        ok, image = self._cap.read()
        return Frame(image, time.time() * 1000.0) if ok and image is not None else None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def info(self) -> dict[str, object]:
        cap = self._cap
        return {
            "index": self.index,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap else 0,
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap else 0,
            "reported_fps": float(cap.get(cv2.CAP_PROP_FPS)) if cap else 0.0,
        }
