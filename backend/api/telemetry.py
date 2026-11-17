"""Telemetry hub and /ws/telemetry endpoint.

Publishing never blocks: each client has a bounded queue and the oldest event is dropped
when a slow consumer falls behind, so acquisition loops are never stalled by the UI.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.schemas import TelemetryEvent, log_event, now_ms

DEFAULT_QUEUE_SIZE = 64


class Client:
    def __init__(self, size: int) -> None:
        self.queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=size)
        self.dropped = 0

    def offer(self, event: TelemetryEvent) -> None:
        """Enqueue without blocking; the oldest queued event is dropped if the queue is full."""
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(event)


ClientHandler = Callable[[dict[str, Any]], TelemetryEvent | None]


class TelemetryHub:
    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._clients: set[Client] = set()
        self._dropped_closed = 0
        self._handlers: dict[str, ClientHandler] = {}

    def register_handler(self, message_type: str, handler: ClientHandler) -> None:
        """Handle a client->server message type; the returned event (if any) is sent back to that client only."""
        self._handlers[message_type] = handler

    def handle(self, msg: dict[str, Any]) -> TelemetryEvent | None:
        handler = self._handlers.get(str(msg.get("type")))
        return handler(msg) if handler else log_event("unsupported client message", level="warning")

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def dropped_events(self) -> int:
        return self._dropped_closed + sum(c.dropped for c in self._clients)

    def subscribe(self) -> Client:
        client = Client(self._queue_size)
        self._clients.add(client)
        return client

    def unsubscribe(self, client: Client) -> None:
        if client in self._clients:
            self._clients.discard(client)
            self._dropped_closed += client.dropped

    def publish(self, event: TelemetryEvent) -> None:
        for client in tuple(self._clients):
            client.offer(event)


router = APIRouter()


def _handle_client_message(hub: TelemetryHub, client: Client, raw: str) -> None:
    try:
        msg: Any = json.loads(raw)
    except json.JSONDecodeError:
        client.offer(log_event("invalid JSON from client", level="warning"))
        return
    if not isinstance(msg, dict):
        client.offer(log_event("unsupported client message", level="warning"))
    elif msg.get("type") == "ping":
        # Reply only to the sender: this is the WebSocket round-trip check.
        client.offer(log_event("pong", ping_id=msg.get("id"), server_timestamp=now_ms()))
    else:
        reply = hub.handle(msg)
        if reply is not None:
            client.offer(reply)


async def _sender(ws: WebSocket, client: Client) -> None:
    while True:
        event = await client.queue.get()
        await ws.send_text(event.model_dump_json())


async def _receiver(ws: WebSocket, hub: TelemetryHub, client: Client) -> None:
    while True:
        _handle_client_message(hub, client, await ws.receive_text())


@router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket) -> None:
    hub: TelemetryHub = ws.app.state.hub
    await ws.accept()
    client = hub.subscribe()
    client.offer(log_event("telemetry connected"))
    tasks = [asyncio.create_task(_sender(ws, client)), asyncio.create_task(_receiver(ws, hub, client))]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        hub.unsubscribe(client)
    # A WebSocketDisconnect surfaced by a task is the normal close path; anything else is a bug.
    for t in tasks:
        if t.done() and not t.cancelled():
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
