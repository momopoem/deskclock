from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

# brightness_controller only needs the logging helper from utils.common.
# Stub it so this pure-logic test does not require pygame.
common_stub = types.ModuleType("utils.common")
common_stub._log_brt_event = lambda _message: None
previous_common = sys.modules.get("utils.common")
sys.modules["utils.common"] = common_stub

from config import (
    BH1750_WAKE_LX,
    DIM_AFTER_SEC,
    LIGHT_OFF_TIMEOUT_SEC,
    PIR_DIM_TO,
    PIR_NO_MOTION_SEC,
)
from services.brightness_controller import compute_desired_brightness

# Do not leak the stub into subsequently collected tests.
if previous_common is None:
    sys.modules.pop("utils.common", None)
else:
    sys.modules["utils.common"] = previous_common
utils_package = sys.modules.get("utils")
if utils_package is not None and getattr(utils_package, "common", None) is common_stub:
    delattr(utils_package, "common")


class BrightnessTimeoutTests(unittest.TestCase):
    def test_configured_no_motion_timeouts(self) -> None:
        self.assertEqual(PIR_NO_MOTION_SEC, 3 * 60)
        self.assertEqual(DIM_AFTER_SEC, 3 * 60)
        self.assertEqual(LIGHT_OFF_TIMEOUT_SEC, 5 * 60)

    def test_steady_bright_room_does_not_defeat_pir_timeout(self) -> None:
        shared = {
            "activity_mono": -100.0,
            "pir_mono": -1000.0,
            "lux": BH1750_WAKE_LX + 5.0,
            "lux_mono": 1.0,
            "_lux_state": "light",
        }

        self.assertEqual(compute_desired_brightness(1.0, shared), 1.0)
        first_wake = shared["activity_mono"]

        after_timeout = PIR_NO_MOTION_SEC + 1.0
        shared["lux_mono"] = after_timeout
        self.assertEqual(
            compute_desired_brightness(after_timeout, shared),
            PIR_DIM_TO,
        )
        self.assertEqual(shared["activity_mono"], first_wake)

    def test_lux_wake_rearms_after_returning_below_light_threshold(self) -> None:
        shared = {
            "activity_mono": -100.0,
            "pir_mono": -1000.0,
            "lux": BH1750_WAKE_LX + 5.0,
            "lux_mono": 1.0,
            "_lux_state": "light",
        }

        compute_desired_brightness(1.0, shared)
        shared["lux"] = 0.0
        shared["lux_mono"] = 10.0
        compute_desired_brightness(10.0, shared)

        shared["lux"] = BH1750_WAKE_LX + 5.0
        shared["lux_mono"] = 20.0
        self.assertEqual(compute_desired_brightness(20.0, shared), 1.0)
        self.assertEqual(shared["activity_mono"], 20.0)


if __name__ == "__main__":
    unittest.main()
