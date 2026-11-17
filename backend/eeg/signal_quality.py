"""Per-channel signal-quality score (0-1). A heuristic from amplitude and mains interference, NOT electrode impedance."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChannelQuality:
    channel: str
    score: float
    label: str  # good | fair | poor
    reason: str


def _label(score: float) -> str:
    return "good" if score >= 0.75 else "fair" if score >= 0.4 else "poor"


def channel_quality(raw_window: np.ndarray, fs: float, names: list[str], line_hz: float = 50.0) -> list[ChannelQuality]:
    """`raw_window` is unfiltered (mean is removed here) so that mains pickup stays visible."""
    out: list[ChannelQuality] = []
    n = raw_window.shape[1]
    freqs = np.fft.rfftfreq(n, 1 / fs)
    broad = (freqs >= 1) & (freqs <= 45)
    line = np.abs(freqs - line_hz) <= 1.0
    for name, ch in zip(names, raw_window):
        x = ch - ch.mean()
        std = float(x.std())
        if not np.all(np.isfinite(x)) or std < 0.5:
            out.append(ChannelQuality(name, 0.0, "poor", "flat or invalid"))
            continue
        amp = 1.0 if 2.0 <= std <= 60.0 else max(0.0, 1.0 - (std - 60.0) / 90.0) if std > 60 else std / 2.0
        spec = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
        line_ratio = float(spec[line].sum() / max(spec[broad].sum() + spec[line].sum(), 1e-12))
        line_score = float(np.clip(1.0 - line_ratio / 0.5, 0.0, 1.0))  # half the power at the mains line = unusable
        score = min(amp, line_score)
        reason = "ok" if score >= 0.75 else "amplitude out of range" if amp < line_score else "mains interference"
        out.append(ChannelQuality(name, round(score, 3), _label(score), reason))
    return out
