"""CCA features for SSVEP: canonical correlation between EEG and sine/cosine references at f and its harmonics."""
from __future__ import annotations

import numpy as np


def reference_signals(freq: float, fs: float, n: int, n_harmonics: int = 2) -> np.ndarray:
    """(n, 2 * n_harmonics): sin and cos at freq, 2*freq, ... Phase-free, so any stimulus phase is captured."""
    t = np.arange(n) / fs
    cols = []
    for h in range(1, n_harmonics + 1):
        cols += [np.sin(2 * np.pi * h * freq * t), np.cos(2 * np.pi * h * freq * t)]
    return np.stack(cols, axis=1)


def _orthonormal_basis(a: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    a = a - a.mean(axis=0, keepdims=True)
    u, s, _ = np.linalg.svd(a, full_matrices=False)
    return u[:, s > tol * max(s[0], 1e-300)]  # drops (near-)constant or collinear columns instead of inventing correlation


def max_canonical_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Largest canonical correlation between column spaces of x (n, p) and y (n, q), via orthonormal bases + SVD."""
    ux, uy = _orthonormal_basis(x), _orthonormal_basis(y)
    if ux.shape[1] == 0 or uy.shape[1] == 0:
        return 0.0
    return float(min(1.0, np.linalg.svd(ux.T @ uy, compute_uv=False)[0]))


class CCAFeatures:
    """Caches the reference matrices per (window length, frequency)."""

    def __init__(self, fs: float, n_harmonics: int = 2) -> None:
        self.fs, self.n_harmonics = fs, n_harmonics
        self._cache: dict[tuple[int, float], np.ndarray] = {}

    def correlations(self, window: np.ndarray, freqs: dict[str, float]) -> dict[str, float]:
        """`window` is (channels, n). Returns target id -> max canonical correlation."""
        n = window.shape[1]
        x = window.T
        out: dict[str, float] = {}
        for tid, f in freqs.items():
            y = self._cache.get((n, f))
            if y is None:
                y = self._cache[(n, f)] = reference_signals(f, self.fs, n, self.n_harmonics)
            out[tid] = max_canonical_correlation(x, y)
        return out


def band_spectrum(window: np.ndarray, fs: float, lo: float = 1.0, hi: float = 30.0, step: float = 0.5) -> list[tuple[float, float]]:
    """Mean power spectrum across channels (Hann window, direct DFT at `step` Hz), for display."""
    x = window - window.mean(axis=1, keepdims=True)
    n = x.shape[1]
    w = np.hanning(n)
    t = np.arange(n) / fs
    out = []
    for f in np.arange(lo, hi + 1e-9, step):
        c, s = np.cos(2 * np.pi * f * t) * w, np.sin(2 * np.pi * f * t) * w
        p = ((x @ c) ** 2 + (x @ s) ** 2) / (n * n)
        out.append((round(float(f), 2), float(p.mean())))
    return out
