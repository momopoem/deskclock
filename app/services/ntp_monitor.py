# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import subprocess

from config import NTP_CHECK_INTERVAL_SEC, NTP_DEGRADED_CHECK_SEC, NTP_RETRY_DELAY_SEC


def ntp_check_once() -> bool:
    try:
        out = subprocess.check_output(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip().lower()
        return out == "yes"
    except Exception:
        return False


def ntp_monitor_update(state: dict, now_mono: float):
    mode = state.get("mode", "ok")
    next_check = state.get("next_check_mono", 0.0)
    if "synced" not in state:
        state["synced"] = False
    if "colon_visible" not in state:
        state["colon_visible"] = True

    def schedule(delta_sec: float):
        state["next_check_mono"] = now_mono + float(delta_sec)

    if now_mono < float(next_check):
        return bool(state.get("synced", False)), bool(state.get("colon_visible", True))

    synced = ntp_check_once()
    state["synced"] = synced
    if mode == "ok":
        if synced:
            state["colon_visible"] = True
            schedule(NTP_CHECK_INTERVAL_SEC)
        else:
            state["mode"] = "wait_retry"
            state["colon_visible"] = True
            schedule(NTP_RETRY_DELAY_SEC)
    elif mode == "wait_retry":
        if synced:
            state["mode"] = "ok"
            state["colon_visible"] = True
            schedule(NTP_CHECK_INTERVAL_SEC)
        else:
            state["mode"] = "degraded"
            state["colon_visible"] = False
            schedule(NTP_DEGRADED_CHECK_SEC)
    else:
        if synced:
            state["mode"] = "ok"
            state["colon_visible"] = True
            schedule(NTP_CHECK_INTERVAL_SEC)
        else:
            state["colon_visible"] = False
            schedule(NTP_DEGRADED_CHECK_SEC)
    return bool(state.get("synced", False)), bool(state.get("colon_visible", True))
