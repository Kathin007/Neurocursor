"""Helpers for tests that talk to a real uvicorn server over HTTP and WebSocket (no httpx)."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI

from backend.api.schemas import DataSource
from backend.vision.camera import Frame
from tests.backend.synthetic_face import BLANK, ScriptedDetector


class Server:
    def __init__(self, app: FastAPI, port: int, server: uvicorn.Server) -> None:
        self.app, self.port, self.server = app, port, server
        self.base = f"127.0.0.1:{port}"

    def call(self, method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 15.0) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://{self.base}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


@contextmanager
def run_server(app: FastAPI) -> Iterator[Server]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        yield Server(app, port, server)
    finally:
        server.should_exit = True
        thread.join(timeout=10)


class FakeCamera:
    """Delivers blank frames at ~30 fps. Labelled DEMO_DATA: it is never a real webcam."""

    source = DataSource.DEMO_DATA

    def __init__(self, fail_after: int | None = None) -> None:
        self.opened = self.closed = False
        self.failing = False
        self.reads = 0

    def open(self) -> None:
        self.opened = True

    def read(self) -> Frame | None:
        time.sleep(0.03)
        if self.failing:
            return None
        self.reads += 1
        return Frame(BLANK, time.time() * 1000.0)

    def close(self) -> None:
        self.closed = True

    def info(self) -> dict[str, object]:
        return {"index": 0, "width": BLANK.shape[1], "height": BLANK.shape[0], "reported_fps": 30.0}


def wait_for(cond, timeout: float = 5.0, step: float = 0.05) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


__all__ = ["FakeCamera", "ScriptedDetector", "Server", "run_server", "wait_for"]
