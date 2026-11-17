from backend.api.schemas import TelemetryEvent, log_event
from backend.api.telemetry import TelemetryHub


def _ev(i: int) -> TelemetryEvent:
    return log_event(f"e{i}", seq=i)


def test_slow_consumer_drops_oldest_and_never_blocks():
    hub = TelemetryHub(queue_size=3)
    client = hub.subscribe()
    for i in range(10):
        hub.publish(_ev(i))  # synchronous, must not block even though nobody is reading
    seqs = [client.queue.get_nowait().payload["seq"] for _ in range(client.queue.qsize())]
    assert seqs == [7, 8, 9]
    assert client.dropped == 7
    assert hub.dropped_events == 7


def test_fast_consumer_is_unaffected_by_slow_one():
    hub = TelemetryHub(queue_size=2)
    slow, fast = hub.subscribe(), hub.subscribe()
    for i in range(6):
        hub.publish(_ev(i))
        fast.queue.get_nowait()
    assert fast.dropped == 0
    assert slow.dropped == 4


def test_unsubscribe_keeps_drop_count_and_removes_client():
    hub = TelemetryHub(queue_size=1)
    client = hub.subscribe()
    hub.publish(_ev(0))
    hub.publish(_ev(1))
    hub.unsubscribe(client)
    assert hub.client_count == 0
    assert hub.dropped_events == 1
