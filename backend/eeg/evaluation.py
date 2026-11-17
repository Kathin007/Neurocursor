"""Measurement of the SSVEP classifier on KNOWN-frequency synthetic EEG. Two separate numbers:

  offline_accuracy  : single windows, no debouncing: "does CCA pick the right frequency?"
  online_session    : the full live pipeline (filter, windows, rejection, debounce, router) over a scripted session:
                      "does the controller issue the right command, how fast, and how often does it fire by mistake?"

Both run on the simulator, so they characterise the algorithm under stated assumptions, not real users or headsets.
Run `python -m backend.eeg.evaluation` to print them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.api.schemas import Mode
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.neural_commands import NeuralCommandMapper
from backend.control.safety_manager import SafetyManager
from backend.eeg.pipeline import EEGConfig, EEGPipeline
from backend.eeg.preprocessing import FilterConfig, filter_window
from backend.eeg.simulator import DEFAULT_CHANNELS, SignalModel, SSVEPSimulator
from backend.eeg.ssvep_classifier import ClassifierConfig, SSVEPClassifier

FS = 250.0
SETTLE = 250  # samples generated before each offline window so the (zero-phase) edge effects fall outside it


def offline_accuracy(cfg: ClassifierConfig | None = None, window_s: float = 2.0, trials_per_target: int = 100,
                     model: SignalModel | None = None, seed: int = 0) -> dict[str, Any]:
    cfg = cfg or ClassifierConfig()
    clf = SSVEPClassifier(FS, cfg)
    n = int(window_s * FS)
    ids = list(cfg.targets)
    confusion = np.zeros((len(ids), len(ids)), dtype=int)
    accepted = accepted_correct = 0
    for i, tid in enumerate(ids):
        for k in range(trials_per_target):
            sim = SSVEPSimulator(FS, model=model, seed=seed + 7919 * i + k, realtime=False)
            sim.target_hz = cfg.targets[tid]
            c = clf.classify(filter_window(sim.read_n(n + SETTLE)[:, SETTLE:], FS))
            assert c.best is not None
            confusion[i, ids.index(c.best)] += 1
            if c.accepted:
                accepted += 1
                accepted_correct += c.best == tid
    total = len(ids) * trials_per_target
    null_accepted = 0
    for k in range(trials_per_target * 2):  # noise-only windows: what fraction would be accepted as a command?
        sim = SSVEPSimulator(FS, model=model, seed=seed + 104729 + k, realtime=False)
        null_accepted += clf.classify(filter_window(sim.read_n(n + SETTLE)[:, SETTLE:], FS)).accepted
    return {
        "window_s": window_s, "trials": total,
        "accuracy_argmax": round(float(np.trace(confusion) / total), 3),
        "accepted_rate": round(accepted / total, 3),
        "accuracy_among_accepted": round(accepted_correct / accepted, 3) if accepted else None,
        "noise_only_false_accept_rate": round(null_accepted / (trials_per_target * 2), 4),
        "per_target_accuracy": {t: round(float(confusion[i, i] / trials_per_target), 3) for i, t in enumerate(ids)},
        "confusion_rows_true_cols_pred": confusion.tolist(),
    }


@dataclass(frozen=True)
class Segment:
    target: str | None  # None = rest (attending to nothing)
    seconds: float


def default_schedule() -> list[Segment]:
    plan = ["up", None, "right", None, "select", None, "left", None, "down", None, "up", None, "right", None, "left", None]
    return [Segment(t, 6.0 if t else 5.0) for t in plan]


def online_session(schedule: list[Segment] | None = None, cfg: EEGConfig | None = None, model: SignalModel | None = None,
                   seed: int = 0, chunk_s: float = 0.1) -> dict[str, Any]:
    """Full pipeline in simulated time. Commands are routed into a SimulatedCursor through the real router."""
    schedule = schedule or default_schedule()
    cfg = cfg or EEGConfig()
    safety = SafetyManager()
    safety.mode_floors[Mode.NEURAL] = cfg.classifier.min_confidence
    cursor = SimulatedCursor()
    router = CommandRouter(CursorEngine(cursor, safety), Mode.NEURAL)
    mapper = NeuralCommandMapper(lambda: (cursor.position[0] / (cursor.screen_size[0] - 1), cursor.position[1] / (cursor.screen_size[1] - 1)), cfg.step)
    pipe = EEGPipeline(FS, list(DEFAULT_CHANNELS), cfg, router, mapper, t0_ms=0.0)
    sim = SSVEPSimulator(FS, model=model, seed=seed, realtime=False)

    # Warm the filter/window with rest so the session starts from a settled state.
    pipe.push(sim.read_n(int((cfg.window_s + 1.0) * FS)))
    t_base = pipe.samples / FS

    per_target: dict[str, dict[str, Any]] = {}
    rest_seconds, false_activations, proc = 0.0, 0, []
    rest_fired: list[str] = []
    rest_offsets: list[float] = []  # seconds after the attended target ended
    segments_correct = segments_total = 0
    first_times: list[float] = []
    wrong_commands = right_commands = 0
    for seg in schedule:
        sim.target_hz = cfg.classifier.targets[seg.target] if seg.target else None
        seg_start = pipe.samples / FS
        fired: list[tuple[float, str]] = []
        for _ in range(int(seg.seconds / chunk_s)):
            for out in pipe.push(sim.read_n(int(chunk_s * FS))):
                proc.append(out.proc_ms)
                if out.fired:
                    fired.append((out.t_s - seg_start, out.fired))
        if seg.target is None:
            rest_seconds += seg.seconds
            false_activations += len(fired)
            rest_fired += [f for _, f in fired]
            rest_offsets += [t for t, _ in fired]
            continue
        segments_total += 1
        ok = next(((t, f) for t, f in fired if f == seg.target), None)
        wrong = [f for _, f in fired if f != seg.target]
        right_commands += sum(1 for _, f in fired if f == seg.target)
        wrong_commands += len(wrong)
        if ok:
            segments_correct += 1
            first_times.append(ok[0])
        d = per_target.setdefault(seg.target, {"segments": 0, "correct": 0})
        d["segments"] += 1
        d["correct"] += bool(ok)
    return {
        "scripted_segments": segments_total, "rest_seconds": rest_seconds,
        "segment_success_rate": round(segments_correct / segments_total, 3) if segments_total else None,
        "time_to_first_correct_command_s_median": round(float(np.median(first_times)), 2) if first_times else None,
        "time_to_first_correct_command_s_p90": round(float(np.percentile(first_times, 90)), 2) if first_times else None,
        "correct_commands": right_commands, "wrong_target_commands": wrong_commands,
        "false_activations_at_rest": false_activations,
        "false_activations_per_minute_at_rest": round(60.0 * false_activations / rest_seconds, 2) if rest_seconds else None,
        "per_target": per_target, "rest_fired": rest_fired, "first_times_s": first_times, "rest_offsets_s": rest_offsets,
        "segments_correct": segments_correct,
        "pipeline_step_ms_median": round(float(np.median(proc)), 2), "pipeline_step_ms_p95": round(float(np.percentile(proc, 95)), 2),
        "cursor_clicks": len(cursor.clicks()),
    }


def online_pooled(seeds: range = range(10), **kwargs: Any) -> dict[str, Any]:
    """The online session repeated over several seeds and pooled: a single 8-segment session is far too noisy to quote."""
    runs = [online_session(seed=s, **kwargs) for s in seeds]
    segs = sum(r["scripted_segments"] for r in runs)
    correct = sum(r["segments_correct"] for r in runs)
    firsts = [t for r in runs for t in r["first_times_s"]]
    rest = sum(r["rest_seconds"] for r in runs)
    false = sum(r["false_activations_at_rest"] for r in runs)
    window = (kwargs.get("cfg") or EEGConfig()).window_s
    carry = sum(1 for r in runs for t in r["rest_offsets_s"] if t <= window + 0.5)  # window still holds the old target
    per_run = [r["segment_success_rate"] for r in runs]
    return {
        "sessions": len(runs), "segments": segs, "segments_correct": correct,
        "segment_success_rate": round(correct / segs, 3),
        "segment_success_rate_per_session_min_max": [min(per_run), max(per_run)],
        "time_to_first_correct_s_median": round(float(np.median(firsts)), 2),
        "time_to_first_correct_s_p90": round(float(np.percentile(firsts, 90)), 2),
        "wrong_target_commands": sum(r["wrong_target_commands"] for r in runs),
        "false_activations_at_rest": false, "of_which_carry_over_within_window_after_target_ended": carry,
        "spurious_false_activations": false - carry, "rest_minutes": round(rest / 60, 1),
        "false_activations_per_minute_at_rest": round(60.0 * false / rest, 3),
        "spurious_per_minute_at_rest": round(60.0 * (false - carry) / rest, 3),
        "pipeline_step_ms_median": round(float(np.median([r["pipeline_step_ms_median"] for r in runs])), 2),
    }


def alpha_sensitivity(alphas: tuple[float, ...] = (0.0, 1.0, 2.0, 4.0), trials_per_target: int = 40) -> dict[float, float]:
    """Offline argmax accuracy as 10 Hz alpha grows: the dominant confound for a 10 Hz target."""
    return {a: offline_accuracy(trials_per_target=trials_per_target, model=SignalModel(alpha_uv=a))["accuracy_argmax"] for a in alphas}


def main() -> None:
    t0 = time.time()
    cfg = ClassifierConfig()
    print(f"SIMULATOR ONLY (SYNTHETIC_EEG, known targets). Defaults: ssvep 3 uV, noise 10 uV, alpha 1 uV, {FS:.0f} Hz, 8 ch")
    print(f"thresholds: confidence >= {cfg.min_confidence}, margin >= {cfg.min_margin}\n")
    for w in (1.0, 2.0, 3.0):
        r = offline_accuracy(window_s=w)
        print(f"OFFLINE window {w:.0f}s: argmax accuracy {r['accuracy_argmax']:.1%} | accepted {r['accepted_rate']:.1%} | "
              f"accuracy among accepted {r['accuracy_among_accepted']} | noise-only false-accept {r['noise_only_false_accept_rate']:.2%}")
    print("OFFLINE accuracy vs alpha amplitude (uV):", alpha_sensitivity())
    print("\nONLINE (full pipeline, 3 consecutive windows, 6 s attention per target, pooled over 10 seeds):")
    for k, v in online_pooled().items():
        print(f"  {k}: {v}")
    print(f"\n[{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
