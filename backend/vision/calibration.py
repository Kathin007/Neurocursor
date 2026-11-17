"""9-point gaze calibration: ridge / polynomial-ridge regression from gaze features to normalized screen coordinates.

Error is reported by leave-one-point-out cross-validation: each calibration point is held out in turn, the model is
fitted on the other points, and its prediction for the held-out point is compared with where the target really was.
This is deliberately pessimistic for corner points (they require extrapolation), and it is the number to quote.

Models persist as plain JSON parameters (no pickle), so a saved profile loads independent of library versions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import median_abs_deviation
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures

CALIBRATION_POINTS: tuple[tuple[float, float], ...] = (
    (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
    (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
    (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
)
MIN_POINTS = 5
MIN_SAMPLES_PER_POINT = 3


class CalibrationError(Exception):
    pass


@dataclass(frozen=True)
class CalibrationSample:
    point_id: int
    features: np.ndarray
    target: tuple[float, float]


class GazeModel:
    """features -> (x, y) normalized screen position. Pure numpy at predict time."""

    def __init__(self, degree: int, alpha: float, n_features: int, mean: np.ndarray, scale: np.ndarray,
                 coef: np.ndarray, intercept: np.ndarray) -> None:
        self.degree, self.alpha, self.n_features = degree, alpha, n_features
        self.mean, self.scale, self.coef, self.intercept = mean, scale, coef, intercept
        self._poly = PolynomialFeatures(degree=degree, include_bias=False).fit(np.zeros((1, n_features)))

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        terms = self._poly.transform(np.asarray(features, dtype=np.float64).reshape(1, -1))[0]
        out = ((terms - self.mean) / self.scale) @ self.coef + self.intercept
        return float(out[0]), float(out[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "degree": self.degree, "alpha": self.alpha, "n_features": self.n_features,
            "mean": self.mean.tolist(), "scale": self.scale.tolist(),
            "coef": self.coef.tolist(), "intercept": self.intercept.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GazeModel:
        return cls(int(d["degree"]), float(d["alpha"]), int(d["n_features"]), np.array(d["mean"]),
                   np.array(d["scale"]), np.array(d["coef"]), np.array(d["intercept"]))


def _fit(features: np.ndarray, targets: np.ndarray, degree: int, alpha: float) -> GazeModel:
    poly = PolynomialFeatures(degree=degree, include_bias=False)
    x = poly.fit_transform(features)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    ridge = Ridge(alpha=alpha).fit((x - mean) / scale, targets)
    return GazeModel(degree, alpha, features.shape[1], mean, scale, ridge.coef_.T, np.asarray(ridge.intercept_))


def reject_outliers(features: np.ndarray, threshold: float = 3.5) -> np.ndarray:
    """Boolean keep-mask: drops samples far from the per-point median (robust MAD z-score, floored for stability)."""
    if len(features) < 5:
        return np.ones(len(features), dtype=bool)
    med = np.median(features, axis=0)
    mad = median_abs_deviation(features, axis=0, scale="normal")
    mad = np.maximum(mad, 1e-3 + 0.01 * np.abs(med))
    return np.all(np.abs(features - med) / mad < threshold, axis=1)


def _errors_px(model: GazeModel, features: np.ndarray, targets: np.ndarray, screen: tuple[int, int]) -> np.ndarray:
    preds = np.array([model.predict(f) for f in features])
    return np.linalg.norm((preds - targets) * np.array(screen, dtype=np.float64), axis=1)


@dataclass
class CalibrationResult:
    model: GazeModel
    degree: int
    alpha: float
    held_out_error_px: float  # mean over points of the mean error on the held-out point
    worst_point_error_px: float
    per_point_error_px: dict[int, float]
    train_error_px: float
    n_samples: int
    n_points: int
    screen: tuple[int, int]
    search: list[dict[str, float]] = field(default_factory=list)  # every (degree, alpha) tried with its held-out error

    def summary(self) -> dict[str, Any]:
        return {
            "degree": self.degree, "alpha": self.alpha,
            "held_out_error_px": round(self.held_out_error_px, 2),
            "worst_point_error_px": round(self.worst_point_error_px, 2),
            "per_point_error_px": {str(k): round(v, 2) for k, v in self.per_point_error_px.items()},
            "train_error_px": round(self.train_error_px, 2),
            "n_samples": self.n_samples, "n_points": self.n_points, "screen": list(self.screen),
            "search": self.search,
        }


def _leave_one_point_out(groups: dict[int, tuple[np.ndarray, np.ndarray]], degree: int, alpha: float,
                         screen: tuple[int, int]) -> dict[int, float]:
    out: dict[int, float] = {}
    for held in groups:
        train_f = np.vstack([groups[p][0] for p in groups if p != held])
        train_t = np.vstack([groups[p][1] for p in groups if p != held])
        model = _fit(train_f, train_t, degree, alpha)
        out[held] = float(_errors_px(model, *groups[held], screen).mean())
    return out


def fit_calibration(samples: list[CalibrationSample], screen: tuple[int, int],
                    degrees: tuple[int, ...] = (1, 2), alphas: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0)) -> CalibrationResult:
    by_point: dict[int, list[CalibrationSample]] = {}
    for s in samples:
        if np.all(np.isfinite(s.features)):
            by_point.setdefault(s.point_id, []).append(s)

    groups: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for pid, group in by_point.items():
        f = np.vstack([s.features for s in group])
        keep = reject_outliers(f)
        if keep.sum() >= MIN_SAMPLES_PER_POINT:
            groups[pid] = (f[keep], np.tile(np.array(group[0].target, dtype=np.float64), (int(keep.sum()), 1)))
    if len(groups) < MIN_POINTS:
        raise CalibrationError(f"need at least {MIN_POINTS} calibration points with {MIN_SAMPLES_PER_POINT}+ usable samples, got {len(groups)}")

    search: list[dict[str, float]] = []
    best: tuple[float, int, float, dict[int, float]] | None = None
    for degree in degrees:
        for alpha in alphas:
            per_point = _leave_one_point_out(groups, degree, alpha, screen)
            mean_err = float(np.mean(list(per_point.values())))
            search.append({"degree": degree, "alpha": alpha, "held_out_error_px": round(mean_err, 2)})
            if best is None or mean_err < best[0]:
                best = (mean_err, degree, alpha, per_point)
    assert best is not None
    err, degree, alpha, per_point = best

    all_f = np.vstack([g[0] for g in groups.values()])
    all_t = np.vstack([g[1] for g in groups.values()])
    model = _fit(all_f, all_t, degree, alpha)
    return CalibrationResult(
        model=model, degree=degree, alpha=alpha, held_out_error_px=err,
        worst_point_error_px=max(per_point.values()), per_point_error_px=per_point,
        train_error_px=float(_errors_px(model, all_f, all_t, screen).mean()),
        n_samples=len(all_f), n_points=len(groups), screen=screen, search=search,
    )


class CalibrationCollector:
    """Accumulates samples while the user looks at each calibration point."""

    def __init__(self, screen: tuple[int, int]) -> None:
        self.screen = screen
        self._samples: list[CalibrationSample] = []

    def add(self, point_id: int, features: np.ndarray) -> None:
        if not 0 <= point_id < len(CALIBRATION_POINTS):
            raise CalibrationError(f"point_id {point_id} out of range")
        self._samples.append(CalibrationSample(point_id, features, CALIBRATION_POINTS[point_id]))

    def count(self, point_id: int) -> int:
        return sum(1 for s in self._samples if s.point_id == point_id)

    @property
    def samples(self) -> list[CalibrationSample]:
        return list(self._samples)

    def fit(self, **kwargs: Any) -> CalibrationResult:
        return fit_calibration(self._samples, self.screen, **kwargs)
