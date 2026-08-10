from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from services.light_controller import (
    arm_light_off,
    light_off_due,
    switchbot_command_succeeded,
)


class LightControllerTests(unittest.TestCase):
    def test_three_minutes_dim_then_two_minutes_more_means_five_minute_off(self) -> None:
        deadline = arm_light_off(1000.0, 5 * 60)
        self.assertEqual(deadline, 1300.0)
        self.assertFalse(
            light_off_due(
                now_mono=1299.9,
                deadline_mono=deadline,
                last_cmd_mono=1000.0,
                cooldown_sec=3.0,
            )
        )
        self.assertTrue(
            light_off_due(
                now_mono=1300.0,
                deadline_mono=deadline,
                last_cmd_mono=1000.0,
                cooldown_sec=3.0,
            )
        )

    def test_off_is_due_even_when_best_effort_state_does_not_know_light_is_on(self) -> None:
        self.assertTrue(
            light_off_due(
                now_mono=300.0,
                deadline_mono=300.0,
                last_cmd_mono=0.0,
                cooldown_sec=3.0,
            )
        )

    def test_motion_rearms_full_deadline(self) -> None:
        self.assertEqual(arm_light_off(120.0, 300.0), 420.0)

    def test_switchbot_status_code_must_indicate_success(self) -> None:
        self.assertTrue(switchbot_command_succeeded({"statusCode": 100}))
        self.assertTrue(switchbot_command_succeeded({"ok": True}))
        self.assertFalse(switchbot_command_succeeded({"statusCode": 190}))
        self.assertFalse(switchbot_command_succeeded({"ok": False}))
        self.assertFalse(switchbot_command_succeeded(None))


if __name__ == "__main__":
    unittest.main()
