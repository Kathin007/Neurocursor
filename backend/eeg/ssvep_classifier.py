"""SSVEP target classification by CCA, with confidence-based rejection and consecutive-window debouncing."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.eeg.artifact_detection import ArtifactConfig, detect_artifacts
from backend.eeg.feature_extraction import CCAFeatures

# Default targets from the brief. 'select' is configurable.
DEFAULT_TARGETS: dict[str, float] = {"up": 8.0, "down": 10.0, "left": 12.0, "right": 15.0, "select": 6.67}


@dataclass(frozen=True)
class ClassifierConfig:
    targets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    n_harmonics: int = 2
    # `confidence` is the winning CCA correlation (0-1), NOT a probability.
    # Defaults sit just above the noise-only 99th percentile (about 0.63) measured on the SIMULATOR with 5-40 Hz filtering
    # and 2 s windows (docs/PROGRESS.md). They MUST be re-tuned on real recordings.
    min_confidence: float = 0.65
    min_margin: float = 0.05  # winner must beat the runner-up by this much, else the window is "ambiguous"
    artifact: ArtifactConfig = field(default_factory=ArtifactConfig)


@dataclass(frozen=True)
class Classification:
    best: str | None  # None only when the window was rejected before scoring (artifact)
    confidence: float
    margin: float
    correlations: dict[str, float]
    accepted: bool
    reason: str  # ok | low confidence | ambiguous | artifact: ...


class SSVEPClassifier:
    def __init__(self, fs: float, cfg: ClassifierConfig | None = None) -> None:
        self.cfg = cfg or ClassifierConfig()
        self.fs = fs
        self._features = CCAFeatures(fs, self.cfg.n_harmonics)

    def classify(self, window: np.ndarray) -> Classification:
        """`window`: filtered (channels, n). Artifact-contaminated channels are excluded; too few left rejects the window."""
        report = detect_artifacts(window, self.cfg.artifact)
        if not report.window_ok:
            return Classification(None, 0.0, 0.0, {}, False, report.reason)
        good = [k for k in range(window.shape[0]) if k not in report.bad_channels]
        corr = self._features.correlations(window[good], self.cfg.targets)
        ranked = sorted(corr.items(), key=lambda kv: kv[1], reverse=True)
        (best, top), second = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0.0)
        margin = top - second
        if top < self.cfg.min_confidence:
            return Classification(best, top, margin, corr, False, "low confidence")
        if margin < self.cfg.min_margin:
            return Classification(best, top, margin, corr, False, "ambiguous")
        return Classification(best, top, margin, corr, True, "ok")


class CommandDebouncer:
    """A command fires only after `consistent_n` consecutive accepted windows agree on the same target.

    Any rejected window breaks the streak. Targets in `repeat` (movement) fire again after another `consistent_n`
    consistent windows while attention is held; others (select) fire once and re-arm only after the streak breaks.
    """

    def __init__(self, consistent_n: int = 3, repeat: frozenset[str] = frozenset({"up", "down", "left", "right"})) -> None:
        if consistent_n < 1:
            raise ValueError("consistent_n must be >= 1")
        self.consistent_n, self.repeat = consistent_n, repeat
        self.reset()

    def reset(self) -> None:
        self._last: str | None = None
        self._streak = 0
        self._spent = False  # a non-repeating target already fired in this streak

    @property
    def streak(self) -> int:
        return self._streak

    def update(self, c: Classification) -> str | None:
        if not c.accepted or c.best is None:
            self.reset()
            return None
        if c.best != self._last:
            self._last, self._streak, self._spent = c.best, 0, False
        self._streak += 1
        if self._streak < self.consistent_n or self._spent:
            return None
        if c.best in self.repeat:
            self._streak = 0
        else:
            self._spent = True
        return c.best
