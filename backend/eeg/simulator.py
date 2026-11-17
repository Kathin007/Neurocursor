"""Injectable synthetic EEG with a KNOWN SSVEP target frequency: ground truth for testing the classifier.

Model per channel: gain * [sin(2 pi f t) + r * sin(2 pi 2f t)] (the SSVEP and its 2nd harmonic) + a 10 Hz alpha rhythm
(which overlaps the 10 Hz target, as real alpha does; its amplitude is the main confound) + coloured noise + a little mains interference.
This is a simulation, not a claim about real EEG: results on it say nothing about real-world accuracy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import lfilter

from backend.api.schemas import DataSource

DEFAULT_CHANNELS = ("O1", "Oz", "O2", "PO3", "POz", "PO4", "Pz", "Cz")
DEFAULT_GAINS = (1.0, 1.0, 1.0, 0.7, 0.8, 0.7, 0.35, 0.1)  # occipital sites carry most of the SSVEP


@dataclass(frozen=True)
class SignalModel:
    ssvep_uv: float = 3.0
    harmonic_ratio: float = 0.5
    noise_uv: float = 10.0
    alpha_uv: float = 1.0  # suppressed-alpha scenario; at 4 uV the 10 Hz rhythm swamps the 10 Hz target (see evaluation)
    alpha_hz: float = 10.0
    line_hz: float = 50.0
    line_uv: float = 1.0


class SSVEPGenerator:
    """Deterministic for a given seed; phase is continuous across successive `next()` calls."""

    def __init__(self, fs: float = 250.0, gains: tuple[float, ...] = DEFAULT_GAINS, model: SignalModel | None = None,
                 seed: int = 0) -> None:
        self.fs, self.gains, self.model = fs, np.asarray(gains, dtype=np.float64), model or SignalModel()
        self.rng = np.random.default_rng(seed)
        c = len(gains)
        self._phase = self.rng.uniform(0, 2 * np.pi, size=(c, 3))  # ssvep, alpha, line
        self._ar_state = np.zeros((c, 1))
        self._n0 = 0

    def next(self, n: int, target_hz: float | None) -> np.ndarray:
        m = self.model
        t = (self._n0 + np.arange(n)) / self.fs
        self._n0 += n
        c = len(self.gains)
        out = np.zeros((c, n))
        if target_hz:
            for k in range(c):
                ph = self._phase[k, 0]
                out[k] += self.gains[k] * m.ssvep_uv * (
                    np.sin(2 * np.pi * target_hz * t + ph) + m.harmonic_ratio * np.sin(2 * np.pi * 2 * target_hz * t + 2 * ph)
                )
        slow = 0.6 + 0.4 * np.sin(2 * np.pi * 0.1 * t)
        for k in range(c):
            out[k] += m.alpha_uv * slow * np.sin(2 * np.pi * m.alpha_hz * t + self._phase[k, 1])
            out[k] += m.line_uv * np.sin(2 * np.pi * m.line_hz * t + self._phase[k, 2])
        white = self.rng.normal(0.0, 0.7 * m.noise_uv, size=(c, n))
        red_in = self.rng.normal(0.0, 0.7 * m.noise_uv * np.sqrt(1 - 0.9**2), size=(c, n))
        red, self._ar_state = lfilter([1.0], [1.0, -0.9], red_in, axis=1, zi=self._ar_state * 0.9)
        return out + white + red


class SSVEPSimulator:
    """An EEGSource backed by SSVEPGenerator. `target_hz` is the ground truth the 'user' is attending to."""

    source = DataSource.SYNTHETIC_EEG

    def __init__(self, fs: float = 250.0, channel_names: tuple[str, ...] = DEFAULT_CHANNELS, model: SignalModel | None = None,
                 seed: int = 0, realtime: bool = True) -> None:
        self.fs = fs
        self.channel_names = list(channel_names)
        self.target_hz: float | None = None
        self.realtime = realtime
        self._gen = SSVEPGenerator(fs, DEFAULT_GAINS[: len(channel_names)], model, seed)
        self._last = 0.0
        self._started = False
        self.disconnected = False  # test hook: the "headset" stops delivering data

    def open(self) -> None:
        pass

    def start(self) -> None:
        self._started, self._last = True, time.perf_counter()

    def read(self) -> np.ndarray:
        if not self._started or self.disconnected or not self.realtime:
            return np.empty((len(self.channel_names), 0))
        now = time.perf_counter()
        n = int((now - self._last) * self.fs)
        if n <= 0:
            return np.empty((len(self.channel_names), 0))
        self._last += n / self.fs
        return self._gen.next(n, self.target_hz)

    def read_n(self, n: int) -> np.ndarray:
        """Deterministic, clock-free generation (tests and offline evaluation)."""
        return self._gen.next(n, self.target_hz)

    def stop(self) -> None:
        self._started = False

    def close(self) -> None:
        pass

    def info(self) -> dict[str, Any]:
        return {"fs": self.fs, "channels": self.channel_names, "source": self.source.value, "injected_target_hz": self.target_hz}
