"""Motor imagery: DOCUMENTED STUB. Nothing here works and no motor-imagery capability is claimed anywhere.

A real implementation would need labelled calibration trials per user (left/right-hand imagery), mu/beta (8-30 Hz)
band-power or CSP features over sensorimotor channels (C3, Cz, C4), and a validated classifier. None of that exists.
"""
from __future__ import annotations

import numpy as np

AVAILABLE = False


class MotorImageryClassifier:
    available = AVAILABLE

    def classify(self, window: np.ndarray) -> None:
        raise NotImplementedError("motor imagery is not implemented (documented stub)")
