import numpy as np
import pytest

from backend.vision.head_pose import estimate_head_pose
from tests.backend.synthetic_face import H, W, project


@pytest.mark.parametrize(
    "yaw,pitch,roll",
    [(0, 0, 0), (20, 0, 0), (-25, 5, 0), (0, 15, 0), (0, -12, 3), (15, -8, 10), (-30, 10, -8)],
)
def test_recovers_known_head_pose_from_a_known_projection(yaw, pitch, roll):
    pts = np.zeros((478, 2))
    for idx, p in zip((1, 152, 33, 263, 61, 291), project(yaw, pitch, roll)):
        pts[idx] = p
    pose = estimate_head_pose(pts, W, H)
    assert pose is not None
    assert abs(pose.yaw - yaw) < 1.0 and abs(pose.pitch - pitch) < 1.0 and abs(pose.roll - roll) < 1.0


def test_non_finite_landmarks_yield_none():
    pts = np.zeros((478, 2))
    pts[1] = (np.nan, 0.0)
    assert estimate_head_pose(pts, W, H) is None
