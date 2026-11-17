import pytest
from pydantic import ValidationError

from backend.api.schemas import Action, DataSource, Mode, TelemetryEvent, UnifiedCommand


def test_data_source_labels_are_exactly_the_five_allowed():
    assert {s.value for s in DataSource} == {
        "REAL_WEBCAM", "REAL_EEG", "SYNTHETIC_EEG", "RECORDED_EEG", "DEMO_DATA",
    }


def test_unified_command_accepts_valid_and_stamps_timestamp():
    cmd = UnifiedCommand(mode=Mode.VISION, action=Action.MOVE, x=0.25, y=0.75, confidence=0.9)
    assert cmd.timestamp > 0


@pytest.mark.parametrize("field,value", [("x", 1.01), ("x", -0.1), ("y", 2), ("confidence", 1.5)])
def test_unified_command_rejects_out_of_range(field, value):
    data = dict(mode="NEURAL", action="CLICK", x=0.5, y=0.5, confidence=0.5)
    data[field] = value
    with pytest.raises(ValidationError):
        UnifiedCommand(**data)


def test_unified_command_rejects_unknown_action():
    with pytest.raises(ValidationError):
        UnifiedCommand(mode="VISION", action="TELEPORT", x=0, y=0, confidence=1)


def test_event_type_is_restricted_to_contract():
    with pytest.raises(ValidationError):
        TelemetryEvent(type="video_frame")


@pytest.mark.parametrize(
    "payload",
    [{"frame": b"\xff\xd8"}, {"nested": {"img": "data:image/jpeg;base64,AAAA"}}, {"l": [bytearray(4)]}],
)
def test_telemetry_event_rejects_frame_like_payloads(payload):
    with pytest.raises(ValidationError):
        TelemetryEvent(type="gaze_update", payload=payload)


def test_event_carries_timestamp():
    assert TelemetryEvent(type="system_log").timestamp > 0
