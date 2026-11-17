"""Raw EEG chunks -> filtered sliding windows -> artifact check -> CCA classification -> debounce -> cursor command.

Pure of threads and hardware (time is the stream's own sample clock), so it runs identically live and in simulation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from backend.api.schemas import UnifiedCommand
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import EngineResult
from backend.control.neural_commands import NeuralCommandMapper
from backend.eeg.feature_extraction import band_spectrum
from backend.eeg.preprocessing import FilterConfig, RingBuffer, StreamingFilter
from backend.eeg.signal_quality import ChannelQuality, channel_quality
from backend.eeg.ssvep_classifier import Classification, ClassifierConfig, CommandDebouncer, SSVEPClassifier

PREFERRED_SSVEP_CHANNELS = ("O1", "Oz", "O2", "POz", "PO3", "PO4", "PO7", "PO8", "Pz", "P3", "P4", "P7", "P8")
WARMUP_S = 0.5  # filter settling before the first window is trusted


@dataclass(frozen=True)
class EEGConfig:
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    window_s: float = 2.0
    hop_s: float = 0.25
    consistent_n: int = 3
    repeat: frozenset[str] = frozenset({"up", "down", "left", "right"})
    step: float = 0.05
    quality_every_s: float = 1.0
    spectrum_every_s: float = 0.5


@dataclass
class StepOutput:
    t_s: float  # stream time at the end of the window (seconds since the first sample)
    classification: Classification
    streak: int
    fired: str | None = None
    command: UnifiedCommand | None = None
    routed: EngineResult | None = None
    proc_ms: float = 0.0
    quality: list[ChannelQuality] | None = None
    spectrum: list[tuple[float, float]] | None = None


def select_ssvep_channels(names: list[str]) -> list[int]:
    """Occipital/parietal sites if the montage has at least three of them, otherwise every channel."""
    idx = [i for i, n in enumerate(names) if n in PREFERRED_SSVEP_CHANNELS]
    return idx if len(idx) >= 3 else list(range(len(names)))


class EEGPipeline:
    def __init__(self, fs: float, channel_names: list[str], cfg: EEGConfig | None = None,
                 router: CommandRouter | None = None, mapper: NeuralCommandMapper | None = None,
                 t0_ms: float | None = None) -> None:
        self.fs, self.names, self.cfg = fs, list(channel_names), cfg or EEGConfig()
        self.router, self.mapper = router, mapper
        self.ssvep_idx = select_ssvep_channels(self.names)
        self.window_n, self.hop_n = int(self.cfg.window_s * fs), max(1, int(self.cfg.hop_s * fs))
        self.filter = StreamingFilter(fs, len(self.names), self.cfg.filter)
        self.filtered = RingBuffer(len(self.names), self.window_n)
        self.raw = RingBuffer(len(self.names), self.window_n)
        self.classifier = SSVEPClassifier(fs, self.cfg.classifier)
        self.debouncer = CommandDebouncer(self.cfg.consistent_n, self.cfg.repeat)
        self.t0_ms = time.time() * 1000.0 if t0_ms is None else t0_ms
        self._since_hop = 0
        self._next_quality = self._next_spectrum = 0.0

    @property
    def samples(self) -> int:
        return self.filtered.count

    def reset(self) -> None:
        self.filter.reset()
        self.debouncer.reset()
        self.filtered, self.raw = RingBuffer(len(self.names), self.window_n), RingBuffer(len(self.names), self.window_n)
        self._since_hop, self._next_quality, self._next_spectrum = 0, 0.0, 0.0

    def push(self, chunk: np.ndarray) -> list[StepOutput]:
        """Feed raw (channels, n) samples in microvolts; returns one StepOutput per completed hop."""
        outputs: list[StepOutput] = []
        for start in range(0, chunk.shape[1], self.hop_n):
            sub = chunk[:, start:start + self.hop_n]
            self.raw.append(sub)
            self.filtered.append(self.filter.process(sub))
            self._since_hop += sub.shape[1]
            if self._since_hop >= self.hop_n and self.filtered.count >= self.window_n + int(WARMUP_S * self.fs):
                self._since_hop -= self.hop_n
                outputs.append(self._step())
        return outputs

    def _step(self) -> StepOutput:
        t0 = time.perf_counter()
        t_s = self.filtered.count / self.fs
        window = self.filtered.latest(self.window_n)[self.ssvep_idx]
        c = self.classifier.classify(window)
        fired = self.debouncer.update(c)
        out = StepOutput(t_s, c, self.debouncer.streak, fired)
        if fired and self.mapper is not None:
            t_ms = self.t0_ms + t_s * 1000.0
            out.command = self.mapper.to_command(fired, c.confidence, t_ms)
            if out.command is not None and self.router is not None:
                out.routed = self.router.route(out.command)
        if t_s >= self._next_quality:
            self._next_quality = t_s + self.cfg.quality_every_s
            out.quality = channel_quality(self.raw.latest(self.window_n), self.fs, self.names, self.cfg.filter.notch_hz or 50.0)
        if t_s >= self._next_spectrum:
            self._next_spectrum = t_s + self.cfg.spectrum_every_s
            out.spectrum = band_spectrum(window[:, -int(self.fs):], self.fs)
        out.proc_ms = (time.perf_counter() - t0) * 1000.0
        return out
