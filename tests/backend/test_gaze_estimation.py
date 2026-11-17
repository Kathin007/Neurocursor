import numpy as np
import pytest

from backend.vision.gaze_estimation import FEATURE_NAMES, extract_features, eye_ratios, gaze_quality
from backend.vision.head_pose import HeadPose, estimate_head_pose
from backend.vision.landmark_indices import R_INNER, R_IRIS, R_LOWER, R_OUTER, R_UPPER
from tests.backend.synthetic_face import H, W, synthetic_landmarks


def px(lm: np.ndarray) -> np.ndarray:
    return lm[:, :2] * np.array([W, H])


@pytest.mark.parametrize("h,v", [(0.5, 0.5), (0.3, 0.5), (0.7, 0.4), (0.45, 0.65)])
def test_features_recover_the_known_iris_ratios_in_image_direction(h, v):
    pts = px(synthetic_landmarks(h, v, 0.3))
    feats = extract_features(pts, HeadPose(0, 0, 0))
    assert feats is not None and feats.shape == (len(FEATURE_NAMES),)
    assert abs(feats[0] - h) < 1e-6 and abs(feats[1] - v) < 1e-6


def test_each_eye_ratio_is_measured_between_its_own_corners():
    pts = px(synthetic_landmarks(0.62, 0.4, 0.3))
    h, v = eye_ratios(pts, R_OUTER, R_INNER, R_UPPER, R_LOWER, R_IRIS)  # type: ignore[misc]
    assert abs(h - 0.62) < 1e-6 and abs(v - 0.4) < 1e-6


def test_features_append_head_pose_angles():
    pts = px(synthetic_landmarks(0.5, 0.5, 0.3, yaw=12, pitch=-6, roll=3))
    pose = estimate_head_pose(pts, W, H)
    feats = extract_features(pts, pose)
    assert feats is not None
    assert abs(feats[2] - 12) < 1 and abs(feats[3] + 6) < 1 and abs(feats[4] - 3) < 1


def test_same_iris_position_with_a_turned_head_gives_different_features():
    # Iris-only would be identical; the pose features are what lets the regression separate them.
    a = extract_features(px(synthetic_landmarks(0.5, 0.5, 0.3)), HeadPose(0, 0, 0))
    b = extract_features(px(synthetic_landmarks(0.5, 0.5, 0.3, yaw=20)), HeadPose(20, 0, 0))
    assert a is not None and b is not None and abs(b[2] - a[2]) > 15


def test_degenerate_geometry_and_missing_pose_give_none():
    pts = px(synthetic_landmarks(0.5, 0.5, 0.3))
    assert extract_features(pts, None) is None
    pts[R_INNER] = pts[R_OUTER]  # zero-width eye
    assert extract_features(pts, HeadPose(0, 0, 0)) is None


def test_quality_penalises_closed_eyes_and_large_head_turns():
    assert gaze_quality(0.30, HeadPose(0, 0, 0)) == 1.0
    assert gaze_quality(0.10, HeadPose(0, 0, 0)) == 0.0
    assert gaze_quality(0.30, HeadPose(45, 0, 0)) == 0.0
    assert 0 < gaze_quality(0.30, HeadPose(20, 0, 0)) < 1
    assert gaze_quality(0.30, None) == 0.0
