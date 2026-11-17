"""EEG hardware acquisition. Nothing here filters or classifies: it only delivers (channels, samples) in microvolts.

BrainFlow covers three cases through one class, distinguished by the board id and labelled honestly:
  SYNTHETIC_BOARD     -> SYNTHETIC_EEG  (fixed sine tones at 5k Hz per channel; no known SSVEP ground truth)
  PLAYBACK_FILE_BOARD -> RECORDED_EEG   (replays a BrainFlow-format file at its recorded pace)
  any real board      -> REAL_EEG       (UNTESTED here: no headset was available)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import numpy as np

from backend.api.schemas import DataSource


class EEGSource(Protocol):
    source: DataSource
    fs: float
    channel_names: list[str]

    def open(self) -> None: ...
    def start(self) -> None: ...
    def read(self) -> np.ndarray: ...  # (channels, n_new_samples); may be empty
    def stop(self) -> None: ...
    def close(self) -> None: ...
    def info(self) -> dict[str, Any]: ...


class BrainFlowSource:
    def __init__(self, board_id: int, source: DataSource, params: Any = None, layout_board_id: int | None = None) -> None:
        """`layout_board_id`: for the playback board, the board whose channel layout the file uses."""
        self.board_id, self.source, self._params = board_id, source, params
        self.layout_id = board_id if layout_board_id is None else layout_board_id
        self.fs = 0.0
        self.channel_names: list[str] = []
        self._board: Any = None
        self._rows: list[int] = []

    def open(self) -> None:
        from brainflow.board_shim import BoardShim, BrainFlowInputParams

        BoardShim.disable_board_logger()
        self._board = BoardShim(self.board_id, self._params or BrainFlowInputParams())
        self._board.prepare_session()  # raises BrainFlowError if the device is absent
        self.fs = float(BoardShim.get_sampling_rate(self.layout_id))
        self._rows = list(BoardShim.get_eeg_channels(self.layout_id))
        try:
            names = list(BoardShim.get_eeg_names(self.layout_id))
        except Exception:
            names = []
        self.channel_names = names if len(names) == len(self._rows) else [f"Ch{i + 1}" for i in range(len(self._rows))]

    def start(self) -> None:
        self._board.start_stream(45000)

    def read(self) -> np.ndarray:
        data = self._board.get_board_data()
        return np.asarray(data[self._rows, :], dtype=np.float64) if data.shape[1] else np.empty((len(self._rows), 0))

    def stop(self) -> None:
        if self._board is not None:
            try:
                self._board.stop_stream()
            except Exception:
                pass

    def close(self) -> None:
        if self._board is not None:
            try:
                self._board.release_session()
            finally:
                self._board = None

    def info(self) -> dict[str, Any]:
        return {"board_id": self.board_id, "fs": self.fs, "channels": self.channel_names, "source": self.source.value}


def synthetic_board_source() -> BrainFlowSource:
    from brainflow.board_shim import BoardIds

    return BrainFlowSource(BoardIds.SYNTHETIC_BOARD.value, DataSource.SYNTHETIC_EEG)


def playback_source(file: str | Path, master_board_id: int | None = None) -> BrainFlowSource:
    from brainflow.board_shim import BoardIds, BrainFlowInputParams

    master = BoardIds.SYNTHETIC_BOARD.value if master_board_id is None else master_board_id
    params = BrainFlowInputParams()
    params.file, params.master_board = str(file), master
    return BrainFlowSource(BoardIds.PLAYBACK_FILE_BOARD.value, DataSource.RECORDED_EEG, params, layout_board_id=master)


def real_board_source(board_id: int, serial_port: str = "", ip_address: str = "") -> BrainFlowSource:
    """A physical headset through BrainFlow. Never exercised in this project's tests (no hardware)."""
    from brainflow.board_shim import BrainFlowInputParams

    params = BrainFlowInputParams()
    params.serial_port, params.ip_address = serial_port, ip_address
    return BrainFlowSource(board_id, DataSource.REAL_EEG, params)


def write_brainflow_file(path: str | Path, eeg: np.ndarray, start_time_s: float = 0.0,
                         master_board_id: int | None = None) -> None:
    """Write (channels, n) microvolt data in the BrainFlow file format the playback board reads."""
    from brainflow.board_shim import BoardIds, BoardShim
    from brainflow.data_filter import DataFilter

    master = BoardIds.SYNTHETIC_BOARD.value if master_board_id is None else master_board_id
    rows, fs = BoardShim.get_num_rows(master), BoardShim.get_sampling_rate(master)
    eeg_rows = BoardShim.get_eeg_channels(master)
    if eeg.shape[0] != len(eeg_rows):
        raise ValueError(f"layout has {len(eeg_rows)} EEG channels, data has {eeg.shape[0]}")
    n = eeg.shape[1]
    data = np.zeros((rows, n))
    data[eeg_rows, :] = eeg
    data[BoardShim.get_timestamp_channel(master)] = start_time_s + np.arange(n) / fs
    data[BoardShim.get_package_num_channel(master)] = np.arange(n) % 256
    DataFilter.write_file(data, str(path), "w")
