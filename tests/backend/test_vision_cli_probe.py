from backend.vision.cli import probe
from tests.backend.server_util import FakeCamera
from tests.backend.synthetic_face import ScriptedDetector


def test_probe_reports_measured_numbers_from_whatever_source_it_is_given():
    cam, det = FakeCamera(), ScriptedDetector()
    det.look(0.5, 0.5, ear=0.28)
    out = probe(cam, det, frames=30)
    assert out["frames_read"] == 30 and out["face_detection_rate"] == 1.0
    assert 15 < out["capture_fps"] < 40  # FakeCamera sleeps ~30 ms per frame
    assert abs(out["ear_min_median_max"][1] - 0.28) < 1e-3
    assert abs(out["features_median_std"]["h_ratio"][0] - 0.5) < 1e-3
    assert out["infrared_like"] is True  # a black test frame has identical channels: the heuristic says so


def test_probe_with_no_face_reports_zero_detection_and_no_feature_stats():
    cam, det = FakeCamera(), ScriptedDetector()
    out = probe(cam, det, frames=15)
    assert out["face_detection_rate"] == 0.0
    assert "ear_min_median_max" not in out and "features_median_std" not in out
