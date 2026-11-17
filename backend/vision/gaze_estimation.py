"""Gaze features. Iris position alone is not absolute gaze, so features combine
iris-relative-to-eye-corner ratios with head-pose angles; the calibration regression maps them to the screen.
"""
from __future__ import annotations

import numpy as np

from backend.vision.head_pose import HeadPose
from backend.vision.landmark_indices import (
    L_INNER, L_IRIS, L_LOWER, L_OUTER, L_UPPER, R_INNER, R_IRIS, R_LOWER, R_OUTER, R_UPPER,
)

FEATURE_NAMES = ("h_ratio", "v_ratio", "yaw", "pitch", "roll")


def _ratio_along(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> float | None:
    """Position of p projected on the segment a->b: 0 at a, 1 at b."""
    ab = b - a
    denom = float(ab @ ab)
    if denom < 1e-6:
        return None
    return float((p - a) @ ab / denom)


def eye_ratios(pts: np.ndarray, outer: int, inner: int, upper: int, lower: int, iris: int) -> tuple[float, float] | None:
    """(horizontal, vertical) iris position. Horizontal runs outer corner -> inner corner, vertical upper -> lower lid."""
    h = _ratio_along(pts[outer, :2], pts[inner, :2], pts[iris, :2])
    v = _ratio_along(pts[upper, :2], pts[lower, :2], pts[iris, :2])
    if h is None or v is None:
        return None
    return h, v


def extract_features(pts_px: np.ndarray, pose: HeadPose | None) -> np.ndarray | None:
    """[h_ratio, v_ratio, yaw, pitch, roll]; ratios are averaged over both eyes in image direction
    (h grows toward image-right, v toward image-bottom). None if the geometry is degenerate."""
    if pose is None:
        return None
    right = eye_ratios(pts_px, R_OUTER, R_INNER, R_UPPER, R_LOWER, R_IRIS)
    left = eye_ratios(pts_px, L_OUTER, L_INNER, L_UPPER, L_LOWER, L_IRIS)
    if right is None or left is None:
        return None
    # The subject's right eye has its outer corner on the image-left, so h already grows rightward;
    # the left eye is mirrored (outer corner on the image-right), so flip it.
    h = (right[0] + (1.0 - left[0])) / 2.0
    v = (right[1] + left[1]) / 2.0
    feats = np.array([h, v, pose.yaw, pose.pitch, pose.roll], dtype=np.float64)
    return feats if np.all(np.isfinite(feats)) else None


def gaze_quality(ear: float, pose: HeadPose | None, ear_open: float = 0.12) -> float:
    """Heuristic 0-1 quality score (NOT a probability): penalises half-closed eyes and large head turns."""
    if pose is None:
        return 0.0
    openness = float(np.clip((ear - ear_open) / 0.12, 0.0, 1.0))
    pose_ok = float(np.clip(1.0 - max(abs(pose.yaw), abs(pose.pitch)) / 40.0, 0.0, 1.0))
    return openness * pose_ok
