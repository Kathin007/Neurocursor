"""Synthetic 478-point face landmarks with KNOWN iris ratios, eye aspect ratio and head pose (ground truth for tests).

Everything produced here is test data: it must never be labelled or presented as a real camera source.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from backend.vision.head_pose import MODEL_POINTS, camera_matrix
from backend.vision.landmark_indices import N_LANDMARKS

W, H = 640, 480
BLANK = np.zeros((H, W, 3), dtype=np.uint8)
EYE_FRACTION = 0.3  # eye width as a fraction of the outer-corner distance


def project(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, distance: float = 1200.0) -> np.ndarray:
    """Pixel positions of the six pose model points for a head with the given angles."""
    rot = Rotation.from_euler("YXZ", [yaw, pitch, roll], degrees=True).as_matrix()
    cam = (rot @ MODEL_POINTS.T).T + np.array([0.0, 0.0, distance])
    k = camera_matrix(W, H)
    return np.stack([k[0, 0] * cam[:, 0] / cam[:, 2] + k[0, 2], k[1, 1] * cam[:, 1] / cam[:, 2] + k[1, 2]], axis=1)


def synthetic_landmarks(h: float, v: float, ear: float, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> np.ndarray:
    """(478, 3) normalized landmarks. h, v = iris ratios (0-1) in image direction; ear = eye aspect ratio."""
    pts = np.tile(np.array([W / 2, H / 2]), (N_LANDMARKS, 1)).astype(np.float64)
    nose, chin, eye_l, eye_r, mouth_l, mouth_r = project(yaw, pitch, roll)
    for idx, p in zip((1, 152, 33, 263, 61, 291), (nose, chin, eye_l, eye_r, mouth_l, mouth_r)):
        pts[idx] = p

    d = eye_r - eye_l
    uh = d / np.linalg.norm(d)  # image-rightward along the eye line
    vh = np.array([-uh[1], uh[0]])  # image-downward, perpendicular
    width = EYE_FRACTION * np.linalg.norm(d)
    gap = ear * width

    pts[133] = eye_l + EYE_FRACTION * d  # subject-right eye inner corner (image-left eye)
    pts[362] = eye_r - EYE_FRACTION * d  # subject-left eye inner corner (image-right eye)
    centers = {"R": (pts[33] + pts[133]) / 2, "L": (pts[362] + pts[263]) / 2}

    def lid(c: np.ndarray, du: float, up: bool) -> np.ndarray:
        return c + uh * du * width - vh * gap / 2 * (1 if up else -1)

    for c, (p2, p3, p5, p6), (up_c, lo_c), iris in (
        (centers["R"], (160, 158, 153, 144), (159, 145), 468),
        (centers["L"], (385, 387, 373, 380), (386, 374), 473),
    ):
        # In both eyes p2/p6 sit at the image-left end and p3/p5 at the image-right end, as vertical pairs.
        pts[p2], pts[p3] = lid(c, -0.2, True), lid(c, 0.2, True)
        pts[p6], pts[p5] = lid(c, -0.2, False), lid(c, 0.2, False)
        pts[up_c], pts[lo_c] = lid(c, 0.0, True), lid(c, 0.0, False)
        pts[iris] = c + uh * (h - 0.5) * width + vh * (v - 0.5) * gap

    out = np.zeros((N_LANDMARKS, 3))
    out[:, 0], out[:, 1] = pts[:, 0] / W, pts[:, 1] / H
    return out


class ScriptedDetector:
    """LandmarkDetector whose output is set by the test: `look(...)` selects the next face; `None` = no face."""

    def __init__(self) -> None:
        self.face: np.ndarray | None = None

    def look(self, h: float, v: float, ear: float = 0.3, **pose: float) -> None:
        self.face = synthetic_landmarks(h, v, ear, **pose)

    def lose_face(self) -> None:
        self.face = None

    def detect(self, image_bgr: np.ndarray, timestamp_ms: float) -> np.ndarray | None:
        return self.face

    def close(self) -> None:
        pass


def gaze_to_ratios(x: float, y: float) -> tuple[float, float]:
    """The ground-truth mapping used across tests: screen position -> iris ratios."""
    return 0.5 + 0.25 * (x - 0.5), 0.5 + 0.2 * (y - 0.5)
