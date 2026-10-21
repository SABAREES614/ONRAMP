"""Tests for ROI assumptions, per-run and accumulated savings."""

import importlib
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def db(monkeypatch):
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setenv("ONRAMP_DB", str(tmp / "roi.db"))
    import onramp_neuro_san.config as config
    importlib.reload(config)
    import onramp_neuro_san.db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db(seed=False)
    return dbmod


def test_roi_defaults(db):
    s = db.get_roi_settings()
    assert s["hourly_rate_usd"] == 20.0
    assert s["human_baseline_minutes"] == 240.0


def test_roi_settings_persist(db):
    db.set_roi_settings(hourly_rate_usd=100, human_baseline_minutes=120)
    s = db.get_roi_settings()
    assert s["hourly_rate_usd"] == 100.0
    assert s["human_baseline_minutes"] == 120.0


def test_roi_for_run_math(db):
    db.set_roi_settings(hourly_rate_usd=60, human_baseline_minutes=120)
    # 30s AI run vs 120 min human baseline at $60/hr.
    roi = db.roi_for_run(30_000)
    assert roi["ai_seconds"] == 30.0
    assert roi["saved_minutes"] == pytest.approx(119.5, abs=0.01)
    # 119.5 min * $60/60 = $119.50
    assert roi["cost_saved_usd"] == pytest.approx(119.5, abs=0.01)


def test_roi_summary_accumulates(db):
    db.set_roi_settings(hourly_rate_usd=60, human_baseline_minutes=120)
    # Create a case + two successful runs of 30s each.
    case = db.create_case({"client_name": "ROI Co"})
    for _ in range(2):
        db.add_agent_run(case["id"], {"agent_name": "a", "status": "success",
                                      "duration_ms": 30_000})
    # An error run should NOT count.
    db.add_agent_run(case["id"], {"agent_name": "a", "status": "error",
                                  "duration_ms": None})
    s = db.roi_summary()
    assert s["runs"] == 2
    # 2 * 119.5 min saved = 239 min; * $60/60 = $239
    assert s["saved_minutes_total"] == pytest.approx(239.0, abs=0.1)
    assert s["cost_saved_total_usd"] == pytest.approx(239.0, abs=0.1)
    assert s["human_cost_total_usd"] == pytest.approx(240.0, abs=0.1)  # 2*120min*$1/min
