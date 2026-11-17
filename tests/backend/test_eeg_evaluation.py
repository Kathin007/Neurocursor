"""Regression guards for the measurement code itself (the full measured numbers are in docs/PROGRESS.md)."""
from backend.eeg.evaluation import Segment, alpha_sensitivity, offline_accuracy, online_session
from backend.eeg.simulator import SignalModel


def test_offline_accuracy_is_reproducible_and_reports_separate_quantities():
    a = offline_accuracy(trials_per_target=20, seed=11)
    b = offline_accuracy(trials_per_target=20, seed=11)
    assert a == b  # deterministic given a seed
    assert {"accuracy_argmax", "accepted_rate", "accuracy_among_accepted", "noise_only_false_accept_rate"} <= set(a)
    assert a["trials"] == 100 and len(a["confusion_rows_true_cols_pred"]) == 5
    assert a["accuracy_argmax"] > 0.9  # measured about 0.98 at the default simulator SNR (2 s windows)
    assert a["noise_only_false_accept_rate"] < 0.05


def test_strong_alpha_destroys_accuracy_which_the_evaluation_exposes():
    acc = alpha_sensitivity(alphas=(0.0, 4.0), trials_per_target=15)
    assert acc[0.0] > 0.9 and acc[4.0] < 0.5


def test_a_one_second_window_cannot_use_the_two_second_thresholds():
    """Thresholds are window-length specific: at 1 s the noise-only statistic is higher and false accepts explode."""
    short = offline_accuracy(window_s=1.0, trials_per_target=10, seed=2)
    assert short["noise_only_false_accept_rate"] > 0.2


def test_online_session_reports_commands_latency_and_rest_behaviour_separately():
    sched = [Segment("right", 8.0), Segment(None, 6.0)]
    r = online_session(sched, model=SignalModel(ssvep_uv=8.0), seed=1)
    assert r["scripted_segments"] == 1 and r["segment_success_rate"] == 1.0
    assert r["time_to_first_correct_command_s_median"] is not None and r["wrong_target_commands"] == 0
    assert r["rest_seconds"] == 6.0 and "false_activations_per_minute_at_rest" in r
    assert r["pipeline_step_ms_median"] > 0
