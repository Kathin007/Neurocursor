"""The real BrainFlow code paths: its synthetic board, and its playback board replaying a known-frequency recording."""
import time

import numpy as np
import pytest

from backend.api.schemas import DataSource, Mode
from backend.control.command_router import CommandRouter
from backend.control.cursor_engine import CursorEngine, SimulatedCursor
from backend.control.neural_commands import NeuralCommandMapper
from backend.control.safety_manager import SafetyManager
from backend.eeg.acquisition import playback_source, synthetic_board_source, write_brainflow_file
from backend.eeg.pipeline import EEGConfig, EEGPipeline
from backend.eeg.simulator import SignalModel, SSVEPGenerator


def read_for(src, seconds):
    chunks, end = [], time.time() + seconds
    while time.time() < end:
        c = src.read()
        if c.shape[1]:
            chunks.append(c)
        time.sleep(0.02)
    return np.concatenate(chunks, axis=1) if chunks else np.empty((len(src.channel_names), 0))


def test_brainflow_synthetic_board_is_detected_labelled_and_streams():
    src = synthetic_board_source()
    src.open()
    try:
        assert src.source == DataSource.SYNTHETIC_EEG
        assert src.fs == 250.0 and len(src.channel_names) == 16
        assert src.channel_names[:5] == ["Fz", "C3", "Cz", "C4", "Pz"]
        src.start()
        data = read_for(src, 2.2)
        src.stop()
    finally:
        src.close()
    assert data.shape[0] == 16 and 400 < data.shape[1] < 700  # about 250 Hz for about 2 s


def test_brainflow_synthetic_board_emits_fixed_tones_at_5k_hz_so_it_has_no_ssvep_ground_truth():
    """Why the ground-truth tests use the injectable simulator instead: this board's tones land on the 10/15 Hz targets."""
    src = synthetic_board_source()
    src.open()
    try:
        src.start()
        data = read_for(src, 4.2)
    finally:
        src.stop()
        src.close()
    fs = 250.0
    for k in range(3):  # channel k+1 carries a tone at 5*(k+1) Hz
        x = data[k] - data[k].mean()
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        peak = np.fft.rfftfreq(len(x), 1 / fs)[spec.argmax()]
        assert abs(peak - 5 * (k + 1)) < 0.5


def test_playback_board_replays_a_known_frequency_recording_into_the_classifier(tmp_path):
    """RECORDED_EEG with ground truth: write a 12 Hz recording in BrainFlow's file format, replay it, classify it."""
    path = tmp_path / "known_12hz.csv"
    gains = [1.0 if n in ("Pz", "PO7", "Oz", "PO8") else 0.1 for n in
             ["Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8", "F5", "F7", "F3", "F1", "F2", "F4", "F6", "F8"]]
    eeg = SSVEPGenerator(250.0, tuple(gains), SignalModel(ssvep_uv=8.0), seed=3).next(250 * 8, 12.0)
    write_brainflow_file(path, eeg, start_time_s=time.time())

    src = playback_source(path)
    src.open()
    assert src.source == DataSource.RECORDED_EEG and src.fs == 250.0 and len(src.channel_names) == 16
    src.start()
    safety = SafetyManager()
    cursor = SimulatedCursor((1000, 1000))
    cursor.position = (500, 500)
    router = CommandRouter(CursorEngine(cursor, safety), Mode.NEURAL)
    pipe = EEGPipeline(src.fs, src.channel_names, EEGConfig(), router,
                       NeuralCommandMapper(lambda: (cursor.position[0] / 999, cursor.position[1] / 999)))
    steps, end = [], time.time() + 7.0
    try:
        while time.time() < end:
            chunk = src.read()
            if chunk.shape[1]:
                steps += pipe.push(chunk)
            time.sleep(0.02)
    finally:
        src.stop()
        src.close()
    assert pipe.ssvep_idx == [4, 5, 6, 7]  # Pz, PO7, Oz, PO8 picked out of 16 channels
    preds = [s.classification.best for s in steps if s.classification.accepted]
    assert preds and preds.count("left") / len(preds) > 0.9
    assert cursor.position[0] < 500  # "left" commands moved the simulated cursor left


def test_write_file_rejects_a_channel_count_that_does_not_match_the_board_layout(tmp_path):
    with pytest.raises(ValueError):
        write_brainflow_file(tmp_path / "x.csv", np.zeros((8, 100)))
