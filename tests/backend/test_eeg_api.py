"""EEG over HTTP + WebSocket. The injected simulator is made strong (8 uV) so real-time tests stay fast and stable."""
import json
import threading
import time

import numpy as np
import pytest
from websockets.sync.client import connect

import backend.eeg.service as eeg_service
from backend.eeg.device_manager import default_factory
from backend.eeg.simulator import SignalModel, SSVEPSimulator
from backend.main import create_app
from tests.backend.server_util import run_server, wait_for


class Rig:
    def __init__(self, tmp_path):
        self.sims: list[SSVEPSimulator] = []

        def factory(kind, params):
            if kind == "injected_synthetic":
                sim = SSVEPSimulator(model=SignalModel(ssvep_uv=8.0), seed=int(params.get("seed", 0)))
                sim.target_hz = params.get("target_hz")
                self.sims.append(sim)
                return sim
            return default_factory(kind, params)

        self.app = create_app(db_path=tmp_path / "db.sqlite", eeg_factory=factory)

    def cursor(self):
        return np.array(self.app.state.cursor.position, dtype=float)


class Collector:
    def __init__(self, base):
        self.raw: list[str] = []
        self._cm = connect(f"ws://{base}/ws/telemetry")
        self._ws = self._cm.__enter__()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            for m in self._ws:
                self.raw.append(m)
        except Exception:
            pass

    @property
    def events(self):
        return [json.loads(m) for m in list(self.raw)]

    def of(self, t):
        return [e for e in self.events if e["type"] == t]

    def send(self, o):
        self._ws.send(json.dumps(o))

    def close(self):
        self._cm.__exit__(None, None, None)


def test_full_flow_connect_start_attend_target_command_pause_stop_disconnect(tmp_path):
    rig = Rig(tmp_path)
    with run_server(rig.app) as srv:
        ws = Collector(srv.base)
        code, st = srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})
        assert code == 200 and st["state"] == "CONNECTED" and st["source"] == "SYNTHETIC_EEG"
        assert st["device"]["n_channels"] == 8 and st["device"]["fs"] == 250.0 and st["device"]["channels"][1] == "Oz"
        assert srv.call("GET", "/api/system/status")[1]["subsystems"]["eeg"] == "CONNECTED"

        code, st = srv.call("POST", "/api/eeg/start", {})
        assert code == 200 and st["state"] == "RUNNING" and st["active_mode"] == "NEURAL"
        assert st["motor_imagery"].startswith("NOT_IMPLEMENTED")

        start_x = rig.cursor()[0]
        ws.send({"type": "set_synthetic_target", "hz": 15.0})  # the 'user' now attends "right"
        assert wait_for(lambda: any(e["payload"]["accepted"] and e["payload"]["target"] == "right"
                                    for e in ws.of("interaction_event")), 25)
        assert rig.cursor()[0] > start_x  # the SimulatedCursor moved right

        # Telemetry content.
        cu = ws.of("classification_update")[-1]["payload"]
        assert {"predicted", "confidence", "margin", "accepted", "reason", "correlations", "streak", "window_s", "latency_ms"} <= set(cu)
        eu = ws.of("eeg_update")[-1]["payload"]
        assert eu["filtered"] is True and eu["unit"] == "uV" and len(eu["samples"]) == 8 and eu["fs"] == 250.0
        assert any(e["payload"]["state"] == "streaming" for e in ws.of("device_status"))
        for e in ws.events:
            if e["type"] in ("eeg_update", "classification_update", "device_status", "interaction_event"):
                assert e["source"] == "SYNTHETIC_EEG" and e["timestamp"] > 0
        assert max(len(m) for m in ws.raw) < 20000

        # Status reflects measured values.
        st = srv.call("GET", "/api/eeg/status")[1]
        assert st["windows_classified"] >= 5 and st["commands_fired"] >= 1 and st["latency_ms_median"] is not None
        assert st["signal_quality"] and {q["label"] for q in st["signal_quality"]} <= {"good", "fair", "poor"}

        # Pause blocks the cursor even though attention continues.
        assert srv.call("POST", "/api/control/pause")[1]["control_state"] == "PAUSED"
        time.sleep(0.5)
        n = len(rig.app.state.cursor.events)
        time.sleep(3.0)
        assert len(rig.app.state.cursor.events) == n
        srv.call("POST", "/api/control/resume")

        assert srv.call("POST", "/api/eeg/stop")[1]["state"] == "CONNECTED"
        assert srv.call("POST", "/api/eeg/disconnect")[1]["state"] == "IDLE"
        assert srv.call("GET", "/api/eeg/status")[1]["device"]["connected"] is False
        ws.close()


def test_the_headset_going_silent_pauses_control_and_reports_the_error(tmp_path, monkeypatch):
    monkeypatch.setattr(eeg_service, "NO_DATA_TIMEOUT_S", 0.6)
    rig = Rig(tmp_path)
    with run_server(rig.app) as srv:
        ws = Collector(srv.base)
        srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})
        srv.call("POST", "/api/eeg/start", {})
        assert wait_for(lambda: srv.call("GET", "/api/eeg/status")[1]["windows_classified"] > 0, 10)
        rig.sims[0].disconnected = True  # unplugged
        assert wait_for(lambda: srv.call("GET", "/api/eeg/status")[1]["state"] == "ERROR", 8)
        st = srv.call("GET", "/api/eeg/status")[1]
        assert st["control_state"] == "PAUSED" and "disconnected" in st["last_error"]
        assert wait_for(lambda: any(e["payload"]["state"] == "error" for e in ws.of("device_status")))
        ws.close()


def test_error_paths_return_clear_statuses_and_nothing_is_started(tmp_path):
    rig = Rig(tmp_path)
    with run_server(rig.app) as srv:
        assert srv.call("POST", "/api/eeg/start", {})[0] == 409  # no device yet
        assert srv.call("POST", "/api/eeg/connect", {"kind": "bogus"})[0] == 422
        code, body = srv.call("POST", "/api/eeg/connect", {"kind": "playback", "file": str(tmp_path / "missing.csv")})
        assert code == 422 and "not found" in body["detail"]
        assert srv.call("POST", "/api/eeg/connect", {"kind": "brainflow_real"})[0] == 422  # board_id required
        assert srv.call("GET", "/api/eeg/status")[1]["state"] == "IDLE"

        assert srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})[0] == 200
        assert srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})[0] == 409  # already connected
        # Configuration is validated: harmonics must stay inside the pass-band, targets must be distinguishable.
        assert srv.call("POST", "/api/eeg/start", {"targets": {"up": 20.0}, "n_harmonics": 2})[0] == 422
        assert srv.call("POST", "/api/eeg/start", {"targets": {"up": 10.0, "down": 10.2}})[0] == 422
        assert srv.call("POST", "/api/eeg/start", {"targets": {"up": 4.0}})[0] == 422
        assert srv.call("POST", "/api/eeg/start", {"window_s": 0.2})[0] == 422
        assert srv.call("GET", "/api/eeg/status")[1]["state"] == "CONNECTED"
        srv.call("POST", "/api/eeg/disconnect")


def test_real_brainflow_synthetic_board_through_the_api_is_labelled_and_has_no_injection(tmp_path):
    with run_server(create_app(db_path=tmp_path / "db.sqlite")) as srv:  # default factory: the real BrainFlow code path
        ws = Collector(srv.base)
        code, st = srv.call("POST", "/api/eeg/connect", {"kind": "brainflow_synthetic"})
        assert code == 200 and st["source"] == "SYNTHETIC_EEG" and st["device"]["n_channels"] == 16
        assert st["injected_target_hz"] is None
        assert srv.call("POST", "/api/eeg/start", {})[1]["state"] == "RUNNING"
        assert wait_for(lambda: srv.call("GET", "/api/eeg/status")[1]["windows_classified"] >= 3, 15)
        ws.send({"type": "set_synthetic_target", "hz": 12})  # meaningless for this board: must say so
        assert wait_for(lambda: any("only applies" in str(e["payload"].get("message")) for e in ws.of("system_log")))
        assert all(e["source"] == "SYNTHETIC_EEG" for e in ws.of("classification_update"))
        srv.call("POST", "/api/eeg/stop")
        srv.call("POST", "/api/eeg/disconnect")
        ws.close()


def test_starting_eeg_hands_cursor_control_to_neural_and_vision_commands_are_then_rejected(tmp_path):
    rig = Rig(tmp_path)
    with run_server(rig.app) as srv:
        assert rig.app.state.vision.router.active_mode.value == "VISION"
        srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})
        srv.call("POST", "/api/eeg/start", {})
        assert rig.app.state.vision.router.active_mode.value == "NEURAL"
        from backend.api.schemas import Action, Mode, UnifiedCommand
        r = rig.app.state.vision.router.route(UnifiedCommand(mode=Mode.VISION, action=Action.MOVE, x=0.5, y=0.5, confidence=1.0))
        assert not r.accepted and "not active" in r.reason
        srv.call("POST", "/api/eeg/disconnect")


def test_the_eeg_service_stores_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rig = Rig(tmp_path)
    with run_server(rig.app) as srv:
        srv.call("POST", "/api/eeg/connect", {"kind": "injected_synthetic"})
        srv.call("POST", "/api/eeg/start", {})
        time.sleep(3.0)
        srv.call("POST", "/api/eeg/disconnect")
    assert [p.name for p in tmp_path.iterdir()] == []  # no recording, no data dir, no db file (db only on first profile save)
