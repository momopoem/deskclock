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


def switchbot_command_payload(command: str) -> dict[str, str]:
    """Build the exact SwitchBot Cloud API command payload."""
    return {
        "command": str(command),
        "parameter": "default",
        "commandType": "command",
    }


def lux_sample_is_fresh(*, now_mono: float, lux_mono: float, stale_sec: float) -> bool:
    """Whether a BH1750 sample is recent enough for light verification."""
    return (
        float(lux_mono) > 0.0
        and 0.0 <= (float(now_mono) - float(lux_mono)) <= float(stale_sec)
    )


def light_is_confirmed(
    *,
    baseline_lux: float | None,
    current_lux: float | None,
    light_on_lx: float,
    min_rise_lx: float,
) -> bool:
    """Confirm actual illumination using absolute lux or a rise from baseline."""
    if current_lux is None:
        return False
    current = max(0.0, float(current_lux))
    if current >= float(light_on_lx):
        return True
    if baseline_lux is None:
        return False
    baseline = max(0.0, float(baseline_lux))
    return (current - baseline) >= float(min_rise_lx)
