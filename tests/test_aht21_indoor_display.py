import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

import config
from utils.common import indoor_source_valid, next_valid_source


def test_aht21_is_a_persistable_indoor_display_source():
    assert config.INDOOR_SOURCES == ["SHT20", "AHT21", "SWITCHBOT", "BME280"]


def test_indoor_cycle_selects_a_fresh_aht21_value():
    state = {"aht21_ts": time.time()}
    assert indoor_source_valid("AHT21", state, False, 5, 0.0)
    assert next_valid_source(
        "SHT20", config.INDOOR_SOURCES,
        lambda source: source == "AHT21",
    ) == "AHT21"


def test_indoor_cycle_skips_stale_aht21_value():
    state = {"aht21_ts": 0.0}
    assert not indoor_source_valid("AHT21", state, False, 5, 0.0)
