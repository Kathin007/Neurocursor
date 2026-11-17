"""SQLite access for calibration profiles. One short-lived connection per call keeps it thread-safe."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.db.schema import DDL
from backend.vision.calibration import CalibrationResult, GazeModel

DEFAULT_DB_PATH = Path("data") / "neurocursor.sqlite"


@dataclass(frozen=True)
class StoredProfile:
    id: int
    name: str
    created_at_ms: float
    data_source: str
    screen: tuple[int, int]
    held_out_error_px: float
    model: GazeModel
    report: dict[str, Any]

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "created_at_ms": self.created_at_ms, "data_source": self.data_source,
            "screen": list(self.screen), "held_out_error_px": round(self.held_out_error_px, 2),
        }


class ProfileStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        """Creates the file and schema on first use, so importing the app never touches the disk."""
        if not self._ready:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executescript(DDL)
            self._ready = True
        return sqlite3.connect(self.path)

    def save_profile(self, name: str, result: CalibrationResult, data_source: str) -> int:
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO calibration_profiles (name, created_at_ms, data_source, screen_w, screen_h,"
                " held_out_error_px, model_json, report_json) VALUES (?,?,?,?,?,?,?,?)",
                (name, time.time() * 1000.0, data_source, result.screen[0], result.screen[1],
                 result.held_out_error_px, json.dumps(result.model.to_dict()), json.dumps(result.summary())),
            )
            return int(cur.lastrowid or 0)

    @staticmethod
    def _row(row: tuple[Any, ...]) -> StoredProfile:
        return StoredProfile(
            id=row[0], name=row[1], created_at_ms=row[2], data_source=row[3], screen=(row[4], row[5]),
            held_out_error_px=row[6], model=GazeModel.from_dict(json.loads(row[7])), report=json.loads(row[8]),
        )

    _COLS = "id, name, created_at_ms, data_source, screen_w, screen_h, held_out_error_px, model_json, report_json"

    def load_profile(self, profile_id: int | None = None) -> StoredProfile | None:
        """The given profile, or the most recently saved one when no id is given."""
        with closing(self._connect()) as db:
            if profile_id is None:
                row = db.execute(f"SELECT {self._COLS} FROM calibration_profiles ORDER BY id DESC LIMIT 1").fetchone()
            else:
                row = db.execute(f"SELECT {self._COLS} FROM calibration_profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._row(row) if row else None

    def list_profiles(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            rows = db.execute(f"SELECT {self._COLS} FROM calibration_profiles ORDER BY id DESC").fetchall()
        return [self._row(r).info() for r in rows]
