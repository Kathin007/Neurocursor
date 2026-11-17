import numpy as np

from backend.vision.blink_detection import BlinkConfig, BlinkDetector, eye_aspect_ratio, landmarks_ear
from tests.backend.synthetic_face import W, H, synthetic_landmarks

OPEN, CLOSED = 0.30, 0.10


def run(det: BlinkDetector, samples: list[tuple[float, float]]):
    return [det.update(ear, t) for t, ear in samples]


def frames(start: float, ear: float, ms: float, step: float = 33.0):
    return [(start + i * step, ear) for i in range(int(ms / step) + 1)]


def test_eye_aspect_ratio_geometry():
    # 6 points: width 10, both vertical gaps 3 -> EAR = (3 + 3) / (2 * 10) = 0.3
    p = np.array([(0, 0), (3, -1.5), (7, -1.5), (10, 0), (7, 1.5), (3, 1.5)], dtype=float)
    assert abs(eye_aspect_ratio(p) - 0.3) < 1e-9
    assert eye_aspect_ratio(np.zeros((6, 2))) == 0.0  # degenerate width


def test_landmarks_ear_recovers_the_synthetic_value():
    for ear in (0.12, 0.25, 0.32):
        pts = synthetic_landmarks(0.5, 0.5, ear)[:, :2] * np.array([W, H])
        assert abs(landmarks_ear(pts) - ear) < 1e-6


def test_valid_blink_fires_exactly_once_on_reopening():
    det = BlinkDetector()
    seq = frames(0, OPEN, 100) + frames(100, CLOSED, 150) + frames(300, OPEN, 200)
    results = run(det, seq)
    assert sum(r.blink for r in results) == 1
    blink = next(r for r in results if r.blink)
    assert 60 <= blink.duration_ms <= 400 and not blink.closed


def test_too_short_closure_is_ignored():
    det = BlinkDetector(BlinkConfig(min_ms=60))
    results = run(det, [(0, OPEN), (10, CLOSED), (30, OPEN), (60, OPEN)])
    assert not any(r.blink for r in results)


def test_prolonged_closure_never_clicks_and_never_repeats():
    det = BlinkDetector(BlinkConfig(max_ms=400))
    results = run(det, frames(0, OPEN, 100) + frames(100, CLOSED, 3000) + frames(3200, OPEN, 300))
    assert not any(r.blink for r in results)
    assert any(r.prolonged for r in results)
    assert results[-1].closed is False


def test_closure_just_over_max_is_rejected_on_reopen():
    det = BlinkDetector(BlinkConfig(max_ms=400))
    results = run(det, [(0, OPEN), (50, CLOSED), (200, CLOSED), (520, OPEN)])
    assert not any(r.blink for r in results)


def test_refractory_period_blocks_a_second_blink_but_allows_a_later_one():
    det = BlinkDetector(BlinkConfig(refractory_ms=500))
    def blink_at(t0: float):
        return [(t0, CLOSED), (t0 + 100, CLOSED), (t0 + 200, OPEN)]
    # Blinks complete at t=233, 530 and 1100. The second is only 297 ms after the first (< 500): rejected.
    # The third is 867 ms after the first: accepted.
    seq = [(0, OPEN)] + blink_at(33) + [(300, OPEN)] + blink_at(330) + [(700, OPEN)] + blink_at(900) + [(1300, OPEN)]
    fired_at = [t for (t, _), r in zip(seq, run(det, seq)) if r.blink]
    assert fired_at == [233, 1100]


def test_hysteresis_prevents_chatter_around_the_threshold():
    det = BlinkDetector(BlinkConfig(ear_threshold=0.2, hysteresis=0.1))
    # Hovering at 0.21 after closing must not count as reopened (needs > 0.22).
    results = run(det, [(0, OPEN), (50, 0.15), (100, 0.21), (150, 0.15), (200, 0.21), (250, 0.15), (300, 0.30)])
    assert sum(r.blink for r in results) == 1


def test_tracking_loss_resets_and_never_produces_a_blink():
    det = BlinkDetector()
    results = run(det, [(0, OPEN), (50, CLOSED), (100, None), (150, OPEN), (200, OPEN)])  # type: ignore[list-item]
    assert not any(r.blink for r in results)
