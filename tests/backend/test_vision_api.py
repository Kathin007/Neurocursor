"""The whole backend over HTTP + WebSocket with a fake camera and scripted detector (all labelled DEMO_DATA)."""
import json
import threading
import time
import urllib.request

import numpy as np
import pytest
from websockets.sync.client import connect

from backend.main import create_app
from backend.vision.calibration import CALIBRATION_POINTS
from backend.vision.face_landmarks import ModelMissing
from tests.backend.server_util import FakeCamera, ScriptedDetector, run_server, wait_for
from tests.backend.synthetic_face import gaze_to_ratios


class Rig:
    def __init__(self, db_path, camera=None, detector=None):
        self.camera = camera or FakeCamera()
        self.detector = detector or ScriptedDetector()
        self.app = create_app(db_path=db_path, camera_factory=lambda i: self.camera, detector_factory=lambda: self.detector)

    def look(self, x, y, ear=0.3):
        self.detector.look(*gaze_to_ratios(x, y), ear=ear)

    def cursor_px(self):
        return np.array(self.app.state.cursor.position, dtype=float)


def target_px(x, y, screen=(1920, 1080)):
    return np.array([x * (screen[0] - 1), y * (screen[1] - 1)])


class Collector:
    """Collects raw WebSocket text in a background thread."""

    def __init__(self, base):
        self.raw: list[str] = []
        self._cm = connect(f"ws://{base}/ws/telemetry")
        self._ws = self._cm.__enter__()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            for msg in self._ws:
                self.raw.append(msg)
        except Exception:
            pass

    @property
    def events(self):
        return [json.loads(m) for m in list(self.raw)]

    def of(self, type_):
        return [e for e in self.events if e["type"] == type_]

    def send(self, obj):
        self._ws.send(json.dumps(obj))

    def close(self):
        self._cm.__exit__(None, None, None)


def calibrate(srv, rig):
    assert srv.call("POST", "/api/vision/calibrate", {"step": "start", "screen_w": 1920, "screen_h": 1080})[0] == 200
    for i, (x, y) in enumerate(CALIBRATION_POINTS):
        rig.look(x, y)
        time.sleep(0.1)
        code, body = srv.call("POST", "/api/vision/calibrate", {"step": "capture", "point_index": i, "n_samples": 10})
        assert code == 200 and body["samples"] == 10, body
    code, fit = srv.call("POST", "/api/vision/calibrate", {"step": "finish"})
    assert code == 200
    return fit


def test_full_flow_start_calibrate_save_control_events_preview_stop(tmp_path):
    rig = Rig(tmp_path / "db.sqlite")
    with run_server(rig.app) as srv:
        rig.look(0.5, 0.5)
        ws = Collector(srv.base)

        code, st = srv.call("POST", "/api/vision/start")
        assert code == 200 and st["state"] == "RUNNING"
        assert st["source"] == "DEMO_DATA" and st["calibration"]["calibrated"] is False
        assert srv.call("GET", "/api/system/status")[1]["subsystems"]["vision"] == "RUNNING"

        # Calibrate through the API, held-out error is reported, then saved.
        fit = calibrate(srv, rig)
        assert fit["n_points"] == 9 and fit["held_out_error_px"] < 5 and fit["saved"] is False
        code, saved = srv.call("POST", "/api/vision/calibrate", {"step": "save", "name": "api-test"})
        assert code == 200 and saved["saved"] and saved["profile"]["data_source"] == "DEMO_DATA"

        # Gaze moves the (simulated) cursor.
        rig.look(0.3, 0.6)
        assert wait_for(lambda: np.linalg.norm(rig.cursor_px() - target_px(0.3, 0.6)) < 25, 6)
        stt = srv.call("GET", "/api/vision/status")[1]
        assert stt["tracking"]["fps"] > 5 and stt["tracking"]["latency_ms_median"] is not None
        assert stt["cursor_backend"] == "SimulatedCursor"

        # Live config over the WebSocket: invalid values are refused, valid ones applied.
        ws.send({"type": "set_vision_config", "config": {"dwell_enabled": False, "smoothing_alpha": 5}})
        assert wait_for(lambda: any(e["payload"].get("message") == "invalid vision config" for e in ws.of("system_log")))
        ws.send({"type": "set_vision_config", "config": {"dwell_enabled": False}})
        assert wait_for(lambda: any(e["payload"].get("message") == "vision config applied" for e in ws.of("system_log")))

        # Blink click shows up as an accepted interaction_event and a simulated click.
        rig.look(0.3, 0.6, ear=0.08)
        time.sleep(0.2)
        rig.look(0.3, 0.6, ear=0.3)
        assert wait_for(lambda: any(e["payload"]["accepted"] for e in ws.of("interaction_event")), 4)
        assert len(rig.app.state.cursor.clicks()) >= 1

        # MJPEG preview is a separate endpoint and yields JPEG data.
        with urllib.request.urlopen(f"http://{srv.base}/api/vision/preview.mjpg", timeout=10) as r:
            assert r.headers["Content-Type"].startswith("multipart/x-mixed-replace")
            chunk = r.read(20000)
        assert b"\xff\xd8" in chunk and b"image/jpeg" in chunk

        # Pause blocks the cursor; resume restores it.
        assert srv.call("POST", "/api/control/pause")[1]["control_state"] == "PAUSED"
        time.sleep(0.2)
        n = len(rig.app.state.cursor.events)
        rig.look(0.8, 0.2)
        time.sleep(0.8)
        assert len(rig.app.state.cursor.events) == n
        assert srv.call("POST", "/api/control/resume")[1]["control_state"] == "ACTIVE"
        assert wait_for(lambda: np.linalg.norm(rig.cursor_px() - target_px(0.8, 0.2)) < 25, 6)

        # Telemetry content: labelled sources, timestamps, measured latency, and no camera frames anywhere.
        types = {e["type"] for e in ws.events}
        assert {"gaze_update", "cursor_update", "interaction_event", "device_status", "system_log"} <= types
        for e in ws.events:
            assert e["timestamp"] > 0
            if e["type"] in ("gaze_update", "cursor_update", "interaction_event", "device_status"):
                assert e["source"] == "DEMO_DATA"  # a fake camera is never labelled REAL_WEBCAM
        assert all(e["payload"]["latency_ms"] >= 0 for e in ws.of("gaze_update"))
        blob = "".join(ws.raw)
        assert "data:image" not in blob and "\\xff\\xd8" not in blob
        assert max(len(m) for m in ws.raw) < 4000  # nothing frame-sized ever travels on the socket
        ws.close()

        code, st = srv.call("POST", "/api/vision/stop")
        assert st["state"] == "IDLE" and rig.camera.closed


def test_saved_calibration_is_reloaded_by_a_fresh_backend_process(tmp_path):
    db = tmp_path / "db.sqlite"
    first = Rig(db)
    with run_server(first.app) as srv:
        first.look(0.5, 0.5)
        srv.call("POST", "/api/vision/start")
        calibrate(srv, first)
        pid = srv.call("POST", "/api/vision/calibrate", {"step": "save", "name": "persist"})[1]["profile"]["id"]
        srv.call("POST", "/api/vision/stop")

    second = Rig(db)  # new app, new service, same database file
    with run_server(second.app) as srv:
        second.look(0.5, 0.5)
        st = srv.call("POST", "/api/vision/start")[1]  # no calibration performed in this process
        assert st["calibration"]["calibrated"] is True and st["calibration"]["profile"]["id"] == pid
        second.look(0.7, 0.35)
        assert wait_for(lambda: np.linalg.norm(second.cursor_px() - target_px(0.7, 0.35)) < 25, 6)
        srv.call("POST", "/api/vision/stop")


def test_camera_failure_pauses_control_and_reports_the_error(tmp_path):
    rig = Rig(tmp_path / "db.sqlite")
    with run_server(rig.app) as srv:
        rig.look(0.5, 0.5)
        ws = Collector(srv.base)
        srv.call("POST", "/api/vision/start")
        rig.camera.failing = True  # unplugged
        assert wait_for(lambda: srv.call("GET", "/api/vision/status")[1]["state"] == "ERROR", 8)
        st = srv.call("GET", "/api/vision/status")[1]
        assert st["control_state"] == "PAUSED" and "camera" in st["last_error"]
        assert wait_for(lambda: any(e["payload"]["state"] == "error" for e in ws.of("device_status")))
        ws.close()


def test_error_paths_return_clear_statuses(tmp_path):
    rig = Rig(tmp_path / "db.sqlite")
    with run_server(rig.app) as srv:
        assert srv.call("POST", "/api/vision/calibrate", {"step": "start"})[0] == 409  # not running
        assert srv.call("GET", "/api/vision/preview.mjpg")[0] == 409
        assert srv.call("POST", "/api/vision/calibrate", {"step": "bogus"})[0] == 422
        assert srv.call("POST", "/api/vision/calibrate", {"step": "capture", "point_index": 9})[0] == 422
        assert srv.call("POST", "/api/vision/start", {"profile_id": 12345})[0] == 404
        assert not rig.camera.opened or rig.camera.closed  # failed start released the camera

        rig.detector.lose_face()
        srv.call("POST", "/api/vision/start")
        rig.app.state.vision.capture_timeout_s = 0.5
        srv.call("POST", "/api/vision/calibrate", {"step": "start"})
        code, body = srv.call("POST", "/api/vision/calibrate", {"step": "capture", "point_index": 0, "n_samples": 5})
        assert code == 408 and "usable samples" in body["detail"]
        assert srv.call("POST", "/api/vision/calibrate", {"step": "finish"})[0] == 422  # too few points
        assert srv.call("POST", "/api/vision/start")[0] == 409  # already running
        srv.call("POST", "/api/vision/stop")


@pytest.mark.parametrize("factory_error", ["camera", "model"])
def test_start_reports_503_when_hardware_or_model_is_unavailable(tmp_path, factory_error):
    def bad_camera(i):
        raise RuntimeError("no device")

    def missing_model():
        raise ModelMissing("model not found")

    kwargs = {"camera_factory": bad_camera, "detector_factory": ScriptedDetector} if factory_error == "camera" \
        else {"camera_factory": lambda i: FakeCamera(), "detector_factory": missing_model}
    with run_server(create_app(db_path=tmp_path / "db.sqlite", **kwargs)) as srv:
        code, body = srv.call("POST", "/api/vision/start")
        assert code == 503 and ("camera unavailable" in body["detail"] or "landmarker unavailable" in body["detail"])
        assert srv.call("GET", "/api/vision/status")[1]["state"] == "IDLE"


def test_the_api_cannot_reach_the_os_cursor(tmp_path):
    app = create_app(db_path=tmp_path / "db.sqlite")
    assert app.state.cursor.name == "SimulatedCursor"
    paths = " ".join(app.openapi()["paths"])
    assert "os" not in {seg for p in app.openapi()["paths"] for seg in p.split("/")}  # no os-cursor route exists
    assert "opt" not in paths
