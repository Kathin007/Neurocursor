import numpy as np
import pytest

from backend.vision.gaze_smoothing import AdaptiveEma


def test_first_sample_passes_through():
    assert AdaptiveEma().update(0.3, 0.7, 0.0) == (0.3, 0.7)


def test_matches_the_ema_formula_when_alpha_is_fixed():
    s = AdaptiveEma(alpha=0.5, alpha_max=0.5)  # alpha == alpha_max disables the adaptation
    s.update(0.0, 0.0, 0.0)
    assert s.update(1.0, 1.0, 0.033) == pytest.approx((0.5, 0.5))
    assert s.update(1.0, 1.0, 0.066) == pytest.approx((0.75, 0.75))


def test_alpha_one_is_a_passthrough():
    s = AdaptiveEma(alpha=1.0)
    s.update(0.1, 0.1, 0.0)
    assert s.update(0.9, 0.2, 0.03) == pytest.approx((0.9, 0.2))


def test_jitter_is_reduced_for_a_still_gaze():
    rng = np.random.default_rng(0)
    raw = 0.5 + rng.normal(0, 0.01, size=(300, 2))
    s = AdaptiveEma(alpha=0.2)
    out = np.array([s.update(x, y, i / 30) for i, (x, y) in enumerate(raw)])
    assert out[50:].std() < 0.6 * raw[50:].std()


def test_a_sustained_sweep_is_tracked_with_small_lag_while_jitter_is_not():
    # Cross the screen in 0.5 s at 30 fps (speed 2 screens/s) with the same jitter as above.
    rng = np.random.default_rng(1)
    t = np.arange(0, 1.0, 1 / 30)
    truth = np.clip((t - 0.2) / 0.5, 0, 1)
    raw = np.stack([truth, truth], axis=1) + rng.normal(0, 0.01, (len(t), 2))
    adaptive = AdaptiveEma(alpha=0.2, alpha_max=0.9)
    fixed = AdaptiveEma(alpha=0.2, alpha_max=0.2)
    a = np.array([adaptive.update(x, y, ti) for (x, y), ti in zip(raw, t)])
    f = np.array([fixed.update(x, y, ti) for (x, y), ti in zip(raw, t)])
    mid = slice(10, 24)  # during the sweep
    assert np.abs(a[mid, 0] - truth[mid]).mean() < 0.6 * np.abs(f[mid, 0] - truth[mid]).mean()


def test_alpha_rises_with_speed_so_fast_moves_are_tracked_closely():
    s = AdaptiveEma(alpha=0.2, alpha_max=0.9, speed_ref=0.6)
    assert s.effective_alpha(0.0) == pytest.approx(0.2)
    assert s.effective_alpha(10.0) == pytest.approx(0.9)
    assert s.effective_alpha(0.3) == pytest.approx(0.55)

    slow, fast = AdaptiveEma(alpha=0.2), AdaptiveEma(alpha=0.2)
    for s_ in (slow, fast):
        s_.update(0.0, 0.0, 0.0)
    slow_out = slow.update(0.01, 0.0, 0.1)[0] / 0.01  # tiny, slow move: heavily smoothed
    fast_out = fast.update(0.8, 0.0, 0.05)[0] / 0.8  # big jump in 50 ms: follows closely
    assert fast_out > slow_out


def test_reset_forgets_history_and_invalid_config_is_rejected():
    s = AdaptiveEma()
    s.update(0.0, 0.0, 0.0)
    s.reset()
    assert s.update(0.7, 0.7, 1.0) == (0.7, 0.7)
    with pytest.raises(ValueError):
        AdaptiveEma(alpha=0.0)
    with pytest.raises(ValueError):
        AdaptiveEma(alpha=1.5)
