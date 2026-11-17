import numpy as np

from backend.db.store import ProfileStore
from backend.vision.calibration import fit_calibration
from tests.backend.test_calibration import SCREEN, features_for, make_samples


def test_calibration_is_saved_and_reloaded_with_identical_predictions(tmp_path):
    path = tmp_path / "nc.sqlite"
    result = fit_calibration(make_samples(), SCREEN)
    pid = ProfileStore(path).save_profile("unit", result, "DEMO_DATA")

    reloaded = ProfileStore(path).load_profile(pid)  # a brand-new store object on the same file
    assert reloaded is not None
    assert reloaded.name == "unit" and reloaded.screen == SCREEN
    assert reloaded.data_source == "DEMO_DATA"
    assert abs(reloaded.held_out_error_px - result.held_out_error_px) < 1e-9
    assert reloaded.report["n_points"] == 9
    rng = np.random.default_rng(3)
    for _ in range(25):
        f = features_for(*rng.uniform(0, 1, 2), rng)
        assert reloaded.model.predict(f) == result.model.predict(f)


def test_load_without_id_returns_the_latest_and_lists_all(tmp_path):
    store = ProfileStore(tmp_path / "nc.sqlite")
    assert store.load_profile() is None and store.list_profiles() == []
    r = fit_calibration(make_samples(), SCREEN)
    first = store.save_profile("a", r, "DEMO_DATA")
    second = store.save_profile("b", r, "DEMO_DATA")
    assert store.load_profile().id == second
    assert [p["id"] for p in store.list_profiles()] == [second, first]
    assert store.load_profile(999) is None


def test_the_database_holds_no_image_or_raw_signal_columns(tmp_path):
    import sqlite3
    ProfileStore(tmp_path / "nc.sqlite")
    cols = {r[1] for r in sqlite3.connect(tmp_path / "nc.sqlite").execute("PRAGMA table_info(calibration_profiles)")}
    assert not any(k in c for c in cols for k in ("image", "frame", "video", "raw"))
