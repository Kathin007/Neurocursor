"""Band-pass + notch filtering. Streaming (causal, stateful) for live use; zero-phase for offline windows."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, sosfilt_zi, sosfiltfilt, tf2sos


@dataclass(frozen=True)
class FilterConfig:
    low_hz: float = 5.0
    high_hz: float = 40.0
    order: int = 4
    notch_hz: float | None = 50.0  # mains frequency: 50 in most of the world, 60 in the Americas
    notch_q: float = 30.0


def design_sos(fs: float, cfg: FilterConfig) -> np.ndarray:
    if not 0 < cfg.low_hz < cfg.high_hz < fs / 2:
        raise ValueError(f"band {cfg.low_hz}-{cfg.high_hz} Hz invalid for fs={fs}")
    sos = butter(cfg.order, [cfg.low_hz, cfg.high_hz], btype="bandpass", fs=fs, output="sos")
    if cfg.notch_hz is not None:
        if not 0 < cfg.notch_hz < fs / 2:
            raise ValueError(f"notch {cfg.notch_hz} Hz invalid for fs={fs}")
        b, a = iirnotch(cfg.notch_hz, cfg.notch_q, fs=fs)
        sos = np.vstack([sos, tf2sos(b, a)])
    return sos


class StreamingFilter:
    """Causal filter with per-channel state carried across chunks (no edge artefacts at chunk boundaries)."""

    def __init__(self, fs: float, n_channels: int, cfg: FilterConfig | None = None) -> None:
        self.sos = design_sos(fs, cfg or FilterConfig())
        self.n_channels = n_channels
        self._zi: np.ndarray | None = None

    def reset(self) -> None:
        self._zi = None

    def process(self, chunk: np.ndarray) -> np.ndarray:
        if chunk.shape[1] == 0:
            return chunk
        if self._zi is None:  # start from the first sample's DC level: real EEG carries a large offset
            self._zi = sosfilt_zi(self.sos)[:, None, :] * chunk[None, :, 0:1]
        out, self._zi = sosfilt(self.sos, chunk, axis=1, zi=self._zi)
        return out


def filter_window(window: np.ndarray, fs: float, cfg: FilterConfig | None = None) -> np.ndarray:
    """Zero-phase filtering of a finished window (offline evaluation only: it is not causal)."""
    return sosfiltfilt(design_sos(fs, cfg or FilterConfig()), window, axis=1)


class RingBuffer:
    def __init__(self, n_channels: int, size: int) -> None:
        self.size = size
        self._buf = np.zeros((n_channels, size))
        self.count = 0  # total samples ever appended

    def append(self, chunk: np.ndarray) -> None:
        n = chunk.shape[1]
        if n >= self.size:
            self._buf[:] = chunk[:, -self.size:]
        elif n:
            self._buf = np.roll(self._buf, -n, axis=1)
            self._buf[:, -n:] = chunk
        self.count += n

    def latest(self, n: int) -> np.ndarray:
        return self._buf[:, -n:].copy()

    @property
    def filled(self) -> int:
        return min(self.count, self.size)
