"""SQLite schema. M3 stores calibration profiles only: model parameters, never images or video."""

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS calibration_profiles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    created_at_ms    REAL    NOT NULL,
    data_source      TEXT    NOT NULL,
    screen_w         INTEGER NOT NULL,
    screen_h         INTEGER NOT NULL,
    held_out_error_px REAL   NOT NULL,
    model_json       TEXT    NOT NULL,
    report_json      TEXT    NOT NULL
);
"""
