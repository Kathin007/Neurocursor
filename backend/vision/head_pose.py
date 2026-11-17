"""Head pose (yaw/pitch/roll in degrees) from six face landmarks via solvePnP.

Convention: angles of the face frame in camera coordinates (x right, y down, z away from the camera),
decomposed as intrinsic Y-X-Z. Signs are consistent, which is all the calibration regression needs.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from backend.vision.landmark_indices import POSE_IDX

# Generic face model (arbitrary units), camera-style axes, in POSE_IDX order:
# nose tip, chin, eye outer (image-left), eye outer (image-right), mouth (image-left), mouth (image-right).
MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),
        (0.0, 330.0, 65.0),
        (-225.0, -170.0, 135.0),
        (225.0, -170.0, 135.0),
        (-150.0, 150.0, 125.0),
        (150.0, 150.0, 125.0),
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class HeadPose:
    yaw: float
    pitch: float
    roll: float


def camera_matrix(width: int, height: int) -> np.ndarray:
    """Pinhole approximation: focal length = image width, principal point at the centre."""
    f = float(width)
    return np.array([[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1]], dtype=np.float64)


def estimate_head_pose(pts_px: np.ndarray, width: int, height: int) -> HeadPose | None:
    image_points = np.ascontiguousarray(pts_px[list(POSE_IDX), :2], dtype=np.float64)
    if not np.all(np.isfinite(image_points)):
        return None
    ok, rvec, _ = cv2.solvePnP(
        MODEL_POINTS, image_points, camera_matrix(width, height), None, flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not ok:
        return None
    yaw, pitch, roll = Rotation.from_rotvec(rvec.ravel()).as_euler("YXZ", degrees=True)
    return HeadPose(float(yaw), float(pitch), float(roll))
