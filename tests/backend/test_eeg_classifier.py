"""SSVEP classifier tests against injected, known-frequency signals."""
import numpy as np
import pytest

from backend.eeg.preprocessing import filter_window
from backend.eeg.simulator import SignalModel, SSVEPGenerator, SSVEPSimulator
from backend.eeg.ssvep_classifier import DEFAULT_TARGETS, Classification, ClassifierConfig, CommandDebouncer, SSVEPClassifier

FS = 250.0
N = 500


def window(target_hz, seed=0, model=None, n=N):
    sim = SSVEPSimulator(FS, model=model, seed=seed, realtime=False)
    sim.target_hz = target_hz
    return filter_window(sim.read_n(n + 250)[:, 250:], FS)


STRONG = SignalModel(ssvep_uv=8.0)


def cls(best="up", accepted=True, conf=0.9):
    return Classification(best, conf, 0.3, {}, accepted, "ok" if accepted else "low confidence")


@pytest.mark.parametrize("tid,hz", list(DEFAULT_TARGETS.items()))
def test_each_default_target_is_recovered_from_injected_ground_truth(tid, hz):
    clf = SSVEPClassifier(FS)
    results = [clf.classify(window(hz, seed=s, model=STRONG)) for s in range(8)]
    assert all(r.best == tid and r.accepted for r in results)
    assert all(r.confidence > 0.65 for r in results)


def test_noise_only_windows_are_rejected_not_forced_into_a_command():
    clf = SSVEPClassifier(FS)
    results = [clf.classify(window(None, seed=100 + s)) for s in range(60)]
    assert sum(r.accepted for r in results) <= 2  # null false-accept rate measured at about 0.5% for 2 s windows
    assert all(r.reason in ("low confidence", "ambiguous", "ok") for r in results)


def test_weak_signal_is_rejected_as_low_confidence():
    clf = SSVEPClassifier(FS, ClassifierConfig(min_confidence=0.95))
    r = clf.classify(window(12.0, model=SignalModel(ssvep_uv=3.0)))
    assert not r.accepted and r.reason == "low confidence" and r.best == "left"


def test_confidence_threshold_is_configurable():
    w = window(12.0, model=SignalModel(ssvep_uv=3.0))
    assert not SSVEPClassifier(FS, ClassifierConfig(min_confidence=0.99)).classify(w).accepted
    assert SSVEPClassifier(FS, ClassifierConfig(min_confidence=0.2, min_margin=0.0)).classify(w).accepted


def test_two_nearly_identical_targets_make_the_window_ambiguous():
    cfg = ClassifierConfig(targets={"a": 10.0, "b": 10.2, "c": 15.0}, min_confidence=0.2)
    r = SSVEPClassifier(FS, cfg).classify(window(10.1, model=STRONG))
    assert not r.accepted and r.reason == "ambiguous" and r.margin < cfg.min_margin


def test_artifact_windows_are_rejected_before_any_scoring():
    w = window(12.0, model=STRONG)
    w[:, 200:240] += 400.0  # blink on every channel
    r = SSVEPClassifier(FS).classify(w)
    assert not r.accepted and r.best is None and r.reason.startswith("artifact")


def test_a_single_bad_channel_is_excluded_and_the_target_is_still_found():
    w = window(12.0, model=STRONG)
    w[0] = 0.0  # one lead falls off
    r = SSVEPClassifier(FS).classify(w)
    assert r.accepted and r.best == "left"


def test_classification_is_deterministic():
    clf = SSVEPClassifier(FS)
    w = window(8.0, seed=5, model=STRONG)
    assert clf.classify(w) == clf.classify(w)


def test_ten_hz_alpha_is_the_documented_confound_for_the_10_hz_target():
    """With strong alpha, 'down' (10 Hz) wins even when the user attends 15 Hz: the failure mode is real and measurable."""
    clf = SSVEPClassifier(FS, ClassifierConfig(min_confidence=0.0, min_margin=0.0))
    heavy = SignalModel(alpha_uv=8.0, ssvep_uv=3.0)
    picks = [clf.classify(window(15.0, seed=s, model=heavy)).best for s in range(20)]
    assert picks.count("down") > 10
    light = SignalModel(alpha_uv=0.5, ssvep_uv=3.0)
    light_right = [clf.classify(window(15.0, seed=s, model=light)).best for s in range(20)].count("right")
    assert light_right > 14 and light_right > picks.count("right") + 8  # same signal, far better once alpha is small


def test_simulator_phase_is_continuous_across_chunks():
    a = SSVEPGenerator(FS, seed=1)
    b = SSVEPGenerator(FS, seed=1)
    whole = a.next(1000, 12.0)
    parts = np.concatenate([b.next(333, 12.0), b.next(333, 12.0), b.next(334, 12.0)], axis=1)
    # Same seed, same phases: the deterministic (non-noise) 12 Hz component matches exactly when noise is removed.
    clean = SignalModel(noise_uv=0.0, alpha_uv=0.0, line_uv=0.0)
    a, b = SSVEPGenerator(FS, model=clean, seed=1), SSVEPGenerator(FS, model=clean, seed=1)
    assert np.allclose(a.next(1000, 12.0), np.concatenate([b.next(333, 12.0), b.next(333, 12.0), b.next(334, 12.0)], axis=1))
    assert whole.shape == parts.shape


# ------------------------------------------------------------------ debouncing
def test_command_needs_n_consecutive_consistent_accepted_windows():
    d = CommandDebouncer(consistent_n=3)
    assert [d.update(cls("up")) for _ in range(3)] == [None, None, "up"]


def test_a_rejected_window_breaks_the_streak():
    d = CommandDebouncer(consistent_n=3)
    out = [d.update(c) for c in (cls("up"), cls("up"), cls(None, False), cls("up"), cls("up"))]
    assert out == [None] * 5  # the streak restarted after the rejection


def test_switching_targets_restarts_the_count():
    d = CommandDebouncer(consistent_n=3)
    out = [d.update(cls(t)) for t in ("up", "up", "down", "down", "up", "up", "up")]
    assert out == [None, None, None, None, None, None, "up"]


def test_movement_targets_repeat_every_n_windows_while_attention_is_held():
    d = CommandDebouncer(consistent_n=3)
    out = [d.update(cls("left")) for _ in range(9)]
    assert out == [None, None, "left", None, None, "left", None, None, "left"]


def test_select_fires_once_and_rearms_only_after_the_streak_breaks():
    d = CommandDebouncer(consistent_n=2)
    out = [d.update(cls("select")) for _ in range(6)]
    assert out == [None, "select", None, None, None, None]
    d.update(cls(None, False))
    assert [d.update(cls("select")) for _ in range(2)] == [None, "select"]


def test_n_equal_one_fires_immediately_and_invalid_n_is_rejected():
    assert CommandDebouncer(consistent_n=1).update(cls("up")) == "up"
    with pytest.raises(ValueError):
        CommandDebouncer(consistent_n=0)
