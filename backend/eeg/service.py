"""Runs the EEG pipeline on a worker thread and publishes telemetry. Acquisition never blocks the event loop."""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Any

import numpy as np

from backend.api.schemas import DataSource, Mode, TelemetryEvent, log_event, now_ms
from backend.api.telemetry import TelemetryHub
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import SimulatedCursor
from backend.control.neural_commands import NeuralCommandMapper
from backend.control.safety_manager import SafetyManager
from backend.eeg.device_manager import DeviceError, DeviceManager
from backend.eeg.pipeline import EEGConfig, EEGPipeline, StepOutput
from backend.eeg.simulator import SSVEPSimulator

NO_DATA_TIMEOUT_S = 3.0
DISPLAY_EVERY_S = 0.1


class EEGService:
    def __init__(self, hub: TelemetryHub, router: CommandRouter, cursor: SimulatedCursor, safety: SafetyManager,
                 devices: DeviceManager | None = None) -> None:
        self.hub, self.router, self.cursor, self.safety = hub, router, cursor, safety
        self.devices = devices or DeviceManager()
        self.state = "IDLE"  # IDLE | CONNECTED | RUNNING | ERROR
        self.last_error: str | None = None
        self.cfg = EEGConfig()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pipeline: EEGPipeline | None = None
        self._source_label = DataSource.SYNTHETIC_EEG
        self._quality: list[dict[str, Any]] | None = None
        self._latencies: deque[float] = deque(maxlen=300)
        self._last_class: dict[str, Any] | None = None
        self._windows = self._commands = 0

    # ------------------------------------------------------------------ lifecycle
    async def connect(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.state in ("CONNECTED", "RUNNING"):
            raise DeviceError(409, "a device is already connected; disconnect first")
        self._loop = asyncio.get_running_loop()
        info = await asyncio.to_thread(self.devices.connect, kind, params)
        self._source_label = self.devices.source.source  # type: ignore[union-attr]
        self.state, self.last_error = "CONNECTED", None
        self._emit(log_event(f"EEG device connected: {kind} ({info['n_channels']} channels, {info['fs']:.0f} Hz)"))
        self._device_status("connected")
        return self.status()

    async def disconnect(self) -> dict[str, Any]:
        await self.stop()
        await asyncio.to_thread(self.devices.disconnect)
        self.state = "IDLE"
        self._device_status("disconnected")
        return self.status()

    async def start(self, cfg: EEGConfig) -> dict[str, Any]:
        if self.state == "RUNNING":
            raise DeviceError(409, "EEG already running")
        src = self.devices.source
        if src is None or self.state not in ("CONNECTED",):
            raise DeviceError(409, "connect an EEG device first")
        self.cfg = cfg
        mapper = NeuralCommandMapper(self._cursor_norm, cfg.step)
        self._pipeline = EEGPipeline(src.fs, src.channel_names, cfg, self.router, mapper)
        self.safety.mode_floors[Mode.NEURAL] = cfg.classifier.min_confidence  # neural click floor = classifier threshold
        self.router.active_mode = Mode.NEURAL
        self._latencies.clear()
        self._windows = self._commands = 0
        await asyncio.to_thread(src.start)
        self.state, self.last_error = "RUNNING", None
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="eeg-worker", daemon=True)
        self._thread.start()
        self._emit(log_event("EEG streaming started; NEURAL is the active control mode"))
        self._device_status("streaming")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            await asyncio.to_thread(thread.join, 5.0)
        if self.devices.source is not None and self.state == "RUNNING":
            await asyncio.to_thread(self.devices.source.stop)
            self.state = "CONNECTED"
            self._device_status("connected")
        self._pipeline = None
        return self.status()

    def _cursor_norm(self) -> tuple[float, float]:
        (x, y), (w, h) = self.cursor.position, self.cursor.screen_size
        return x / max(w - 1, 1), y / max(h - 1, 1)

    def set_synthetic_target(self, hz: float | None) -> bool:
        """Change the ground-truth target of the injected simulator. False for any other source."""
        src = self.devices.source
        if isinstance(src, SSVEPSimulator):
            src.target_hz = hz
            return True
        return False

    # ------------------------------------------------------------------ worker thread
    def _worker(self) -> None:
        src, pipe = self.devices.source, self._pipeline
        assert src is not None and pipe is not None
        last_data, last_display = time.perf_counter(), 0.0
        try:
            while not self._stop.is_set():
                chunk = src.read()
                now = time.perf_counter()
                if chunk.shape[1] == 0:
                    if now - last_data > NO_DATA_TIMEOUT_S:
                        raise RuntimeError("EEG device stopped delivering data (disconnected?)")
                    time.sleep(0.01)
                    continue
                last_data = now
                for out in pipe.push(chunk):
                    self._publish_step(out)
                if now - last_display >= DISPLAY_EVERY_S:
                    last_display = now
                    self._publish_display(pipe)
        except Exception as e:  # device lost or processing crashed: fail safe by pausing control
            self.last_error, self.state = str(e), "ERROR"
            self.safety.pause()
            self._emit(log_event(f"EEG error: {e}; control paused", level="error"))
            self._device_status("error")

    def _publish_step(self, out: StepOutput) -> None:
        c = out.classification
        self._windows += 1
        latency = now_ms() - (self._pipeline.t0_ms + out.t_s * 1000.0) if self._pipeline else 0.0
        self._latencies.append(latency)
        payload = {
            "predicted": c.best, "hz": self.cfg.classifier.targets.get(c.best) if c.best else None,
            "confidence": round(c.confidence, 3), "margin": round(c.margin, 3), "accepted": c.accepted, "reason": c.reason,
            "correlations": {k: round(v, 3) for k, v in c.correlations.items()}, "streak": out.streak, "fired": out.fired,
            "window_s": self.cfg.window_s, "proc_ms": round(out.proc_ms, 2), "latency_ms": round(latency, 1),
        }
        self._last_class = payload
        self._emit(TelemetryEvent(type="classification_update", source=self._source_label, payload=payload))
        if out.quality is not None:
            self._quality = [{"channel": q.channel, "score": q.score, "label": q.label, "reason": q.reason} for q in out.quality]
        if out.fired and out.command is not None and out.routed is not None:
            self._commands += 1
            self._emit(TelemetryEvent(type="interaction_event", source=self._source_label, payload={
                "kind": out.command.action.value, "trigger": "SSVEP", "target": out.fired, "accepted": out.routed.accepted,
                "reason": out.routed.reason, "confidence": round(c.confidence, 3),
            }))
            if out.routed.accepted:
                x, y = self._cursor_norm()
                self._emit(TelemetryEvent(type="cursor_update", source=self._source_label, payload={
                    "x": x, "y": y, "px": list(self.cursor.position), "backend": self.cursor.name,
                    "control_state": self.safety.state.value,
                }))

    def _publish_display(self, pipe: EEGPipeline) -> None:
        k = min(int(DISPLAY_EVERY_S * pipe.fs * 1.5), pipe.filtered.filled)
        if k == 0:
            return
        latest = pipe.filtered.latest(k)
        self._emit(TelemetryEvent(type="eeg_update", source=self._source_label, payload={
            "fs": pipe.fs, "channels": pipe.names, "unit": "uV", "filtered": True,
            "samples": np.round(latest, 2).tolist(), "total_samples": pipe.samples, "quality": self._quality,
        }))

    def _emit(self, event: TelemetryEvent) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.hub.publish, event)

    def _device_status(self, state: str) -> None:
        self._emit(TelemetryEvent(type="device_status", source=self._source_label, payload={
            "device": "eeg", "state": state, "error": self.last_error, **self.devices.info(),
        }))

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        lat = list(self._latencies)
        return {
            "state": self.state, "last_error": self.last_error, "device": self.devices.info(),
            "source": self._source_label.value if self.devices.connected else None,
            "injected_target_hz": getattr(self.devices.source, "target_hz", None) if isinstance(self.devices.source, SSVEPSimulator) else None,
            "windows_classified": self._windows, "commands_fired": self._commands,
            "latency_ms_median": round(float(np.median(lat)), 1) if lat else None,
            "signal_quality": self._quality, "last_classification": self._last_class,
            "control_state": self.safety.state.value, "active_mode": self.router.active_mode.value,
            "cursor_backend": self.cursor.name,
            "motor_imagery": "NOT_IMPLEMENTED (documented stub)",
            "config": {
                "targets": self.cfg.classifier.targets, "window_s": self.cfg.window_s, "hop_s": self.cfg.hop_s,
                "consistent_n": self.cfg.consistent_n, "min_confidence": self.cfg.classifier.min_confidence,
                "min_margin": self.cfg.classifier.min_margin, "n_harmonics": self.cfg.classifier.n_harmonics,
                "notch_hz": self.cfg.filter.notch_hz, "step": self.cfg.step,
            },
        }
