"""Round-trip tests against a real uvicorn server (REST + /ws/telemetry), no httpx needed."""
import json
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn
from websockets.sync.client import connect

from backend.main import create_app


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(db_path=tmp_path_factory.mktemp("db") / "t.sqlite"), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"
    yield f"127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def _status(base: str) -> dict:
    with urllib.request.urlopen(f"http://{base}/api/system/status", timeout=5) as r:
        return json.load(r)


def test_system_status_reports_nothing_as_connected(base):
    s = _status(base)
    assert s["app"] == "neurocursor"
    assert s["timestamp"] > 0
    # Nothing is opened until asked: vision and EEG idle, cursor simulated.
    assert s["subsystems"] == {"vision": "IDLE", "eeg": "IDLE", "cursor": "SimulatedCursor"}


def test_websocket_ping_pong_round_trip(base):
    with connect(f"ws://{base}/ws/telemetry") as ws:
        hello = json.loads(ws.recv(timeout=5))
        assert hello["type"] == "system_log" and hello["payload"]["message"] == "telemetry connected"
        assert hello["timestamp"] > 0
        ws.send(json.dumps({"type": "ping", "id": 7}))
        pong = json.loads(ws.recv(timeout=5))
        assert pong["type"] == "system_log"
        assert pong["payload"]["message"] == "pong"
        assert pong["payload"]["ping_id"] == 7
        assert pong["payload"]["server_timestamp"] > 0


def test_websocket_bad_input_warns_but_stays_open(base):
    with connect(f"ws://{base}/ws/telemetry") as ws:
        ws.recv(timeout=5)
        ws.send("not json")
        warn = json.loads(ws.recv(timeout=5))
        assert warn["payload"]["level"] == "warning"
        ws.send(json.dumps({"type": "ping", "id": 1}))
        assert json.loads(ws.recv(timeout=5))["payload"]["ping_id"] == 1


def test_client_count_tracks_connections(base):
    with connect(f"ws://{base}/ws/telemetry") as ws:
        ws.recv(timeout=5)
        assert _status(base)["telemetry"]["clients"] >= 1
    deadline = time.time() + 5
    while _status(base)["telemetry"]["clients"] != 0 and time.time() < deadline:
        time.sleep(0.05)
    assert _status(base)["telemetry"]["clients"] == 0
