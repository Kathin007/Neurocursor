import numpy as np
import pytest

from backend.vision.calibration import (
    CALIBRATION_POINTS, CalibrationCollector, CalibrationError, CalibrationSample, GazeModel,
    fit_calibration, reject_outliers,
)

SCREEN = (1920, 1080)


def features_for(x: float, y: float, rng: np.random.Generator, noise: float = 0.0, quad: float = 0.0) -> np.ndarray:
    """Ground-truth feature model: ratios (optionally mildly nonlinear) plus pose angles that also shift the gaze."""
    yaw, pitch = rng.uniform(-5, 5), rng.uniform(-4, 4)
    h = 0.5 + 0.25 * (x - 0.5) + quad * (x - 0.5) ** 2 - 0.004 * yaw
    v = 0.5 + 0.2 * (y - 0.5) + quad * (y - 0.5) ** 2 - 0.004 * pitch
    return np.array([h, v, yaw, pitch, 0.0]) + rng.normal(0, noise, 5)


def make_samples(n_per_point: int = 20, noise: float = 0.002, quad: float = 0.0, seed: int = 1) -> list[CalibrationSample]:
    rng = np.random.default_rng(seed)
    return [
        CalibrationSample(i, features_for(x, y, rng, noise, quad), (x, y))
        for i, (x, y) in enumerate(CALIBRATION_POINTS)
        for _ in range(n_per_point)
    ]


def test_nine_points_defined_on_a_3x3_grid():
    assert len(CALIBRATION_POINTS) == 9
    assert {p[0] for p in CALIBRATION_POINTS} == {0.1, 0.5, 0.9}


def test_fit_recovers_a_linear_ground_truth_with_small_held_out_error():
    res = fit_calibration(make_samples(), SCREEN)
    assert res.n_points == 9
    assert res.held_out_error_px < 40  # px on a 1920x1080 screen, for 0.2% feature noise
    # Fresh, unseen gaze positions map back accurately.
    rng = np.random.default_rng(99)
    errs = []
    for x, y in rng.uniform(0.15, 0.85, size=(50, 2)):
        px, py = res.model.predict(features_for(x, y, rng))
        errs.append(np.hypot((px - x) * SCREEN[0], (py - y) * SCREEN[1]))
    assert np.mean(errs) < 40


def test_held_out_error_is_reported_per_point_and_is_not_the_training_error():
    res = fit_calibration(make_samples(noise=0.01), SCREEN)
    assert set(res.per_point_error_px) == set(range(9))
    assert res.worst_point_error_px == max(res.per_point_error_px.values())
    assert res.held_out_error_px >= res.train_error_px  # held-out is the honest (larger) number


def test_selection_picks_polynomial_when_a_low_dimensional_mapping_is_strongly_nonlinear():
    rng = np.random.default_rng(4)
    samples = [
        CalibrationSample(i, np.array([0.5 + 0.25 * (x - 0.5) + 1.0 * (x - 0.5) ** 2,
                                       0.5 + 0.2 * (y - 0.5) + 1.0 * (y - 0.5) ** 2]) + rng.normal(0, 0.0003, 2), (x, y))
        for i, (x, y) in enumerate(CALIBRATION_POINTS) for _ in range(15)
    ]
    res = fit_calibration(samples, SCREEN)
    assert res.degree == 2
    assert {(s["degree"], s["alpha"]) for s in res.search} == {(d, a) for d in (1, 2) for a in (0.01, 0.1, 1.0, 10.0)}


def test_chosen_model_is_the_argmin_of_the_held_out_search():
    # With 9 points and 5 features, degree 2 (20 terms) overfits under leave-one-point-out; the selector must see that.
    res = fit_calibration(make_samples(quad=0.6, noise=0.0005), SCREEN)
    best = min(res.search, key=lambda s: s["held_out_error_px"])
    assert (res.degree, res.alpha) == (best["degree"], best["alpha"])
    worst_poly = max(s["held_out_error_px"] for s in res.search if s["degree"] == 2)
    assert worst_poly > res.held_out_error_px


def test_outliers_are_rejected_per_point():
    f = np.tile([0.5, 0.5, 0, 0, 0], (20, 1)) + np.random.default_rng(0).normal(0, 0.002, (20, 5))
    f[3] = [0.9, 0.1, 40, -30, 20]  # a glance away mid-capture
    keep = reject_outliers(f)
    assert not keep[3] and keep.sum() >= 18


def test_too_few_points_or_samples_raise():
    with pytest.raises(CalibrationError):
        fit_calibration([s for s in make_samples() if s.point_id < 3], SCREEN)
    with pytest.raises(CalibrationError):
        fit_calibration(make_samples(n_per_point=2), SCREEN)


def test_model_round_trips_through_json_exactly():
    res = fit_calibration(make_samples(), SCREEN)
    clone = GazeModel.from_dict(res.model.to_dict())
    rng = np.random.default_rng(5)
    for _ in range(20):
        f = features_for(*rng.uniform(0, 1, 2), rng)
        assert clone.predict(f) == pytest.approx(res.model.predict(f), abs=1e-12)


def test_collector_validates_points_and_counts():
    c = CalibrationCollector(SCREEN)
    c.add(4, np.zeros(5))
    assert c.count(4) == 1 and c.count(0) == 0
    with pytest.raises(CalibrationError):
        c.add(9, np.zeros(5))


def test_non_finite_samples_are_ignored():
    samples = make_samples()
    samples.append(CalibrationSample(0, np.array([np.nan, 0, 0, 0, 0]), CALIBRATION_POINTS[0]))
    assert fit_calibration(samples, SCREEN).n_points == 9
