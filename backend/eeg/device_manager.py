"""EEG device lifecycle: choose a source, open it, report detected channels, close it."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.eeg.acquisition import EEGSource, playback_source, real_board_source, synthetic_board_source
from backend.eeg.simulator import SignalModel, SSVEPSimulator

KINDS = ("injected_synthetic", "brainflow_synthetic", "playback", "brainflow_real")


class DeviceError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def default_factory(kind: str, p: dict[str, Any]) -> EEGSource:
    if kind == "injected_synthetic":  # SYNTHETIC_EEG with a settable ground-truth SSVEP target
        sim = SSVEPSimulator(model=SignalModel(), seed=int(p.get("seed", 0)))
        sim.target_hz = p.get("target_hz")
        return sim
    if kind == "brainflow_synthetic":  # BrainFlow's own board: fixed tones at 5k Hz, NO known SSVEP target
        return synthetic_board_source()
    if kind == "playback":  # RECORDED_EEG
        file = Path(str(p.get("file", "")))
        if not file.is_file():
            raise DeviceError(422, f"playback file not found: {file}")
        return playback_source(file, p.get("master_board_id"))
    if kind == "brainflow_real":  # REAL_EEG: never exercised without a headset
        if p.get("board_id") is None:
            raise DeviceError(422, "board_id required for a real headset")
        return real_board_source(int(p["board_id"]), str(p.get("serial_port", "")), str(p.get("ip_address", "")))
    raise DeviceError(422, f"unknown device kind {kind!r}; expected one of {KINDS}")


class DeviceManager:
    def __init__(self, factory: Callable[[str, dict[str, Any]], EEGSource] = default_factory) -> None:
        self._factory = factory
        self.source: EEGSource | None = None
        self.kind: str | None = None
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self.source is not None

    def connect(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        """Blocking (opens hardware): call from a worker thread."""
        if self.source is not None:
            raise DeviceError(409, "a device is already connected; disconnect first")
        src = self._factory(kind, params)
        try:
            src.open()
        except DeviceError:
            raise
        except Exception as e:
            self.last_error = str(e)
            raise DeviceError(503, f"device unavailable: {e}") from e
        self.source, self.kind, self.last_error = src, kind, None
        return self.info()

    def disconnect(self) -> None:
        src, self.source, self.kind = self.source, None, None
        if src is not None:
            src.stop()
            src.close()

    def info(self) -> dict[str, Any]:
        s = self.source
        if s is None:
            return {"connected": False, "kind": None, "source": None, "last_error": self.last_error}
        return {"connected": True, "kind": self.kind, "source": s.source.value, "fs": s.fs, "channels": list(s.channel_names),
                "n_channels": len(s.channel_names), "last_error": self.last_error}
