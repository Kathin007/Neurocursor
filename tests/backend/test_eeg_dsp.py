import numpy as np
import pytest
from sklearn.cross_decomposition import CCA

from backend.eeg.artifact_detection import ArtifactConfig, detect_artifacts
from backend.eeg.feature_extraction import CCAFeatures, band_spectrum, max_canonical_correlation, reference_signals
from backend.eeg.preprocessing import FilterConfig, RingBuffer, StreamingFilter, design_sos, filter_window
from backend.eeg.signal_quality import channel_quality

FS = 250.0


def sine(f, n=2000, amp=1.0, phase=0.0):
    return amp * np.sin(2 * np.pi * f * np.arange(n) / FS + phase)


def gain_at(f, cfg=None):
    """Steady-state amplitude gain of the filter at frequency f (zero-phase run on a long sine)."""
    x = np.tile(sine(f, 5000), (1, 1))
    y = filter_window(x, FS, cfg)
    return float(np.abs(y[0, 1500:-1500]).max())


# ------------------------------------------------------------------ preprocessing
def test_bandpass_passes_the_ssvep_band_and_attenuates_outside_it():
    assert gain_at(10) > 0.95 and gain_at(15) > 0.95
    assert gain_at(1) < 0.05  # drift
    assert gain_at(60) < 0.05  # above the band


def test_notch_removes_mains_even_when_the_band_is_widened_to_include_it():
    wide = FilterConfig(low_hz=5, high_hz=100, notch_hz=50.0)
    assert gain_at(50, wide) < 0.1 and gain_at(30, wide) > 0.9
    assert gain_at(50, FilterConfig(low_hz=5, high_hz=100, notch_hz=None)) > 0.9  # without the notch it passes


def test_invalid_filter_settings_are_rejected():
    with pytest.raises(ValueError):
        design_sos(FS, FilterConfig(low_hz=30, high_hz=10))
    with pytest.raises(ValueError):
        design_sos(FS, FilterConfig(high_hz=200))
    with pytest.raises(ValueError):
        design_sos(FS, FilterConfig(notch_hz=200))


def test_streaming_filter_is_chunk_size_invariant():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 10, (4, 3000)) + sine(12, 3000)
    whole = StreamingFilter(FS, 4).process(x)
    for size in (1, 7, 250, 999):
        f = StreamingFilter(FS, 4)
        parts = np.concatenate([f.process(x[:, i:i + size]) for i in range(0, 3000, size)], axis=1)
        assert np.allclose(parts, whole, atol=1e-9), size


def test_streaming_filter_handles_a_large_dc_offset_without_a_startup_blast():
    x = 50000.0 + sine(10, 1000) * 5  # raw amplifier output carries a big DC level
    y = StreamingFilter(FS, 1).process(x[None, :])
    assert np.abs(y[0, :50]).max() < 25  # starts from the first sample's level instead of ringing at ~50000


def test_ring_buffer_keeps_the_latest_samples_in_order():
    rb = RingBuffer(2, 5)
    rb.append(np.arange(6).reshape(2, 3).astype(float))
    rb.append(np.arange(10, 14).reshape(1, 4).repeat(2, axis=0).astype(float))
    assert rb.count == 7 and rb.filled == 5
    assert rb.latest(5)[0].tolist() == [2.0, 10.0, 11.0, 12.0, 13.0]
    rb.append(np.arange(100, 108).reshape(1, 8).repeat(2, axis=0).astype(float))  # larger than the buffer
    assert rb.latest(5)[0].tolist() == [103.0, 104.0, 105.0, 106.0, 107.0]


# ------------------------------------------------------------------ CCA features
def test_reference_signals_contain_sin_and_cos_at_each_harmonic():
    y = reference_signals(10.0, FS, 500, n_harmonics=2)
    assert y.shape == (500, 4)
    t = np.arange(500) / FS
    assert np.allclose(y[:, 0], np.sin(2 * np.pi * 10 * t)) and np.allclose(y[:, 3], np.cos(2 * np.pi * 20 * t))


def test_cca_is_near_one_at_the_true_frequency_and_low_elsewhere_for_any_phase():
    feats = CCAFeatures(FS)
    targets = {"a": 8.0, "b": 10.0, "c": 12.0, "d": 15.0}
    for phase in (0.0, 1.1, 2.5):
        x = np.stack([sine(12.0, 500, phase=phase + k) for k in range(4)]) + np.random.default_rng(1).normal(0, 0.05, (4, 500))
        r = feats.correlations(x, targets)
        assert r["c"] > 0.97 and max(r["a"], r["b"], r["d"]) < 0.4


def test_second_harmonic_content_is_captured_by_the_harmonic_references():
    x = np.stack([sine(20.0, 500, phase=k) for k in range(3)])  # energy only at 2 x 10 Hz
    assert CCAFeatures(FS, n_harmonics=2).correlations(x, {"t10": 10.0})["t10"] > 0.97
    assert CCAFeatures(FS, n_harmonics=1).correlations(x, {"t10": 10.0})["t10"] < 0.4


def test_matches_scikit_learn_cca_on_random_data():
    rng = np.random.default_rng(7)
    for _ in range(5):
        x, y = rng.normal(size=(400, 6)), rng.normal(size=(400, 4))
        y[:, 0] += 0.6 * x[:, 0]  # plant some real correlation
        mine = max_canonical_correlation(x, y)
        u, v = CCA(n_components=1, max_iter=2000, tol=1e-10).fit(x, y).transform(x, y)
        assert abs(mine - np.corrcoef(u[:, 0], v[:, 0])[0, 1]) < 1e-3


def test_constant_or_duplicate_channels_do_not_invent_correlation():
    rng = np.random.default_rng(2)
    base = rng.normal(size=(500, 1))
    x = np.hstack([base, base, np.zeros((500, 1)), np.ones((500, 1))])  # duplicates and constants
    y = reference_signals(10.0, FS, 500)
    assert max_canonical_correlation(x, y) < 0.3
    assert max_canonical_correlation(np.zeros((500, 3)), y) == 0.0


def test_band_spectrum_peaks_at_the_injected_frequency():
    x = np.stack([sine(12.0, 250, phase=k) for k in range(3)])
    spec = band_spectrum(x, FS)
    assert max(spec, key=lambda p: p[1])[0] == 12.0


# ------------------------------------------------------------------ artifacts + quality
def test_artifact_detection_flags_blinks_flat_and_railed_channels():
    rng = np.random.default_rng(0)
    w = rng.normal(0, 5, (8, 500))
    assert detect_artifacts(w).window_ok
    w[0, 100:140] += 300  # blink-sized deflection
    w[1] = 0.0  # flat lead
    w[2] = 900.0 + rng.normal(0, 1, 500)  # railed
    rep = detect_artifacts(w)
    assert rep.bad_channels == {0: "amplitude", 1: "flat", 2: "railed"} and rep.window_ok  # 5 good channels remain


def test_window_is_rejected_when_too_few_good_channels_remain():
    w = np.random.default_rng(0).normal(0, 5, (8, 500))
    w[:6] += 400 * np.sin(np.linspace(0, 20, 500))
    rep = detect_artifacts(w, ArtifactConfig(min_good_channels=3))
    assert not rep.window_ok and rep.reason.startswith("artifact")


def test_non_finite_samples_are_artifacts():
    w = np.random.default_rng(0).normal(0, 5, (4, 500))
    w[2, 10] = np.nan
    assert detect_artifacts(w).bad_channels == {2: "non-finite"}


def test_signal_quality_scores_good_flat_and_mains_contaminated_channels():
    rng = np.random.default_rng(3)
    n = 500
    good = rng.normal(0, 8, n)
    flat = np.zeros(n)
    t = np.arange(n) / FS
    mains = rng.normal(0, 1, n) + 40 * np.sin(2 * np.pi * 50 * t)
    q = channel_quality(np.stack([good, flat, mains]), FS, ["Oz", "O1", "O2"], line_hz=50.0)
    assert q[0].label == "good" and q[1].label == "poor" and q[2].label == "poor"
    assert q[2].reason == "mains interference" and q[1].score == 0.0
