# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations


def arm_light_off(now_mono: float, timeout_sec: float) -> float:
    """Return the absolute no-motion deadline for switching the light off."""
    return float(now_mono) + max(0.0, float(timeout_sec))


def light_off_due(
    *,
    now_mono: float,
    deadline_mono: float,
    last_cmd_mono: float,
    cooldown_sec: float,
) -> bool:
    """Whether an OFF command is due, independent of best-effort light state."""
    return (
        float(deadline_mono) > 0.0
        and float(now_mono) >= float(deadline_mono)
        and (float(now_mono) - float(last_cmd_mono)) >= float(cooldown_sec)
    )


def switchbot_command_succeeded(response: object) -> bool:
    """Interpret both local transport failures and SwitchBot API status codes."""
    if not isinstance(response, dict) or response.get("ok") is False:
        return False
    status_code = response.get("statusCode")
    return status_code is None or status_code == 100
