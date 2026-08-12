from __future__ import annotations

import json

from state import ClockState
from utils import common


def test_air_modes_round_trip(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(common, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(common, "STATE_PATH", str(state_path))

    common.save_ui_state(
        "SHT20", "Internet", True, (10, 20, 30), "default", "PRESSURE", "CO2"
    )
    loaded = common.load_ui_state()
    state = ClockState.from_ui_snapshot(loaded)
    assert state.air_left_mode == "PRESSURE"
    assert state.air_right_mode == "CO2"


def test_old_state_defaults_to_ens160_values(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"indoor_mode": "SHT20", "outdoor_mode": "SWITCHBOT"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(common, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(common, "STATE_PATH", str(state_path))
    loaded = common.load_ui_state()
    assert loaded["air_left_mode"] == "ECO2"
    assert loaded["air_right_mode"] == "TVOC"

