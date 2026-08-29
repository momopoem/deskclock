#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.

"""

Code map:
- Product metadata / version logging
- Configuration constants
- Utility helpers (formatting, geometry, IO)
- SensorManager + worker threads
- BrightnessController
- UI rendering + event loop (main)

Desk Side Clock
================

Product Name : Desk Side Clock
Release Type : Product Version
Version      : v2.3.2
Status       : Release

Notes:
- Outside temperature value (7-seg) is shifted left by 15px (final spec)
- Added BME280 pressure and SCD40 CO2 support with persistent air-value touch toggles
- ENS160 temperature/humidity compensation is sourced from BME280
- Startup splash shows version for 3 seconds (robust) and then forces one-shot flip
- Outdoor data can be sourced from SwitchBot Cloud API via env vars (preferred) or Open-Meteo fallback
"""

from __future__ import annotations

# -------------------------
# Imports
#   - Standard library
#   - Third-party
# -------------------------
import os
import json
import time
import threading
from dataclasses import dataclass, replace
from typing import Callable, Optional, Any
from datetime import datetime
import random
import subprocess
import hmac
import hashlib
import base64
from pathlib import Path

import requests
import pygame

# --- Split UI modules (v1.3.0 display split 1-3) ---
from renderer.clock_renderer import ClockRenderer, RenderCtx, TopLineCtx, BottomInfoCtx
from renderer.theme_engine import get_theme_spec, next_theme_name

from config import *
from config import __product__, __version__, __status__
from utils.common import (
    _log_brt_event,
    _log_dpm_event,
    _log_light_event,
    _log_version_to_clocklog,
    apply_dim,
    blit_hstack_baseline,
    digit_top_y,
    fmt_temp_hum,
    load_font,
    load_ui_state,
    make_blank_slot,
    next_valid_source,
    outdoor_source_valid,
    indoor_source_valid,
    pick_info_font_path,
    random_bright_color,
    render_run,
    save_ui_state,
    show_startup_version,
    strip_leading_zero_2digit,
    total_width,
    weekday_ja,
    _is_fresh,
)
from services.ntp_monitor import ntp_monitor_update
from services.sensor_service import (
    _bh1750_read_lux,
    _sht20_read_temp_hum_via_i2c,
    _aht21_read_temp_hum_via_i2c,
    fetch_aht21_loop,
    fetch_bh1750_loop,
    fetch_bme280_loop,
    fetch_ens160_loop,
    fetch_pir_loop,
    fetch_sht20_loop,
    fetch_scd40_loop,
    read_sht20_indoor,
)
from services.weather_service import (
    draw_weather_icon,
    make_switchbot_headers,
    weather_code_to_icon,
)
from services.brightness_controller import _apply_brightness
from services.light_controller import (
    arm_light_off,
    light_is_confirmed,
    light_off_due,
    lux_sample_is_fresh,
    switchbot_command_payload,
    switchbot_command_succeeded,
)
from state import ClockState
from bootstrap import build_ui_dependencies, build_service_dependencies

_log_version_to_clocklog()





# -----------------------------------------------------------------------------
# Display Power Manager (v2 skeleton)
#   - Fully compatible with v1.1.2 rules/thresholds/conditions
#   - Side-effect free: returns HDMI command intention ("ON"/"OFF"/None)
# -----------------------------------------------------------------------------

@dataclass
class DimState:
    """Logical display state (v1.1.2 compatible)."""
    disp_state: str = "ON"            # "ON" | "DIM" | "OFF"
    is_dark: bool = False             # hysteresis flag
    dim_enter_mono: float | None = None


@dataclass
class HdmiState:
    """Physical HDMI power state (v1.1.2 compatible)."""
    hdmi_is_off: bool = False         # True when we believe HDMI is OFF (commanded)


@dataclass(frozen=True)
class DisplayPowerDecision:
    """Decision returned by DisplayPowerStateMachine.step().

    It contains snapshots of logical (DimState) and physical (HdmiState) states
    plus the HDMI command intention and a human-readable reason string.
    """
    prev_state: str
    prev_hdmi_is_off: bool
    dim: DimState
    hdmi: HdmiState
    hdmi_cmd: str | None = None   # "ON" | "OFF" | None
    reason: str = ""


class DisplayPowerStateMachine:
    """Display power state machine (ON/DIM/OFF), v1.1.2 compatible.

    This is a v2 skeleton: internal state is stored in dataclasses (DimState/HdmiState)
    while preserving v1.1.2 constants, thresholds, and condition ordering.

    Rules (must match v1.1.2):
      - Recent motion (t_no_motion <= PIR_WAKE_OVERRIDE_SEC) forces ON.
      - If not dark (hysteresis on BH1750 lux), keep ON.
      - If dark:
          - If not already OFF and inactivity >= DIM_AFTER_SEC -> DIM
          - In DIM:
              - When brightness reaches ~0% -> OFF immediately
              - Else OFF after OFF_AFTER_DIM_SEC since entering DIM
      - HDMI commands are emitted only on transitions and are guarded (idempotent).
    """

    def __init__(self) -> None:
        self.dim: DimState = DimState()
        self.hdmi: HdmiState = HdmiState()
        # Transition hook (called only when logical state changes or HDMI cmd emitted)
        self._on_transition: Optional[Callable[..., None]] = self._default_on_transition

    
    def set_on_transition(self, cb: Optional[Callable[..., None]]) -> None:
        """Set a transition hook.

        The hook is called as: cb(decision, **context)
        where context may include: t_no_motion, brightness_target, brightness_cur, is_dark.
        Pass None to disable.
        """
        self._on_transition = cb

    def _default_on_transition(self, decision: "DisplayPowerDecision", **ctx) -> None:
        """Default transition hook: log to ~/deskclock/log/clock.log (fail-safe)."""
        try:
            prev = decision.prev_state
            cur = decision.dim.disp_state
            prev_hdmi = "OFF" if decision.prev_hdmi_is_off else "ON"
            cur_hdmi = "OFF" if decision.hdmi.hdmi_is_off else "ON"
            cmd = decision.hdmi_cmd or "-"
            reason = decision.reason or "-"
            dark = ctx.get("is_dark", decision.dim.is_dark)
            tnm = ctx.get("t_no_motion", None)
            btgt = ctx.get("brightness_target", None)
            bcur = ctx.get("brightness_cur", None)
            parts = [f"[DPM] {prev}->{cur}", f"hdmi:{prev_hdmi}->{cur_hdmi}", f"cmd={cmd}", f"reason={reason}", f"dark={dark}"]
            if isinstance(tnm, (int, float)):
                parts.append(f"t_no_motion={tnm:.1f}")
            if isinstance(bcur, (int, float)) and isinstance(btgt, (int, float)):
                parts.append(f"bcur={bcur:.4f} btgt={btgt:.4f}")
            _log_dpm_event(" ".join(parts))
        except Exception:
            pass

# ---- Backward-compatible attributes (read/write) ----
    @property
    def disp_state(self) -> str:
        return self.dim.disp_state

    @disp_state.setter
    def disp_state(self, v: str) -> None:
        self.dim.disp_state = v

    @property
    def hdmi_is_off(self) -> bool:
        return self.hdmi.hdmi_is_off

    @hdmi_is_off.setter
    def hdmi_is_off(self, v: bool) -> None:
        self.hdmi.hdmi_is_off = v

    @property
    def is_dark(self) -> bool:
        return self.dim.is_dark

    @is_dark.setter
    def is_dark(self, v: bool) -> None:
        self.dim.is_dark = v

    @property
    def dim_enter_mono(self) -> float | None:
        return self.dim.dim_enter_mono

    @dim_enter_mono.setter
    def dim_enter_mono(self, v: float | None) -> None:
        self.dim.dim_enter_mono = v

    # ---- Core logic ----
    def update_dark(self, lux_f: float | None) -> None:
        """Update hysteresis dark flag from lux (v1.1.2 compatible)."""
        if lux_f is None:
            return
        if self.dim.is_dark:
            if lux_f >= LUX_BRIGHT:
                self.dim.is_dark = False
        else:
            if lux_f <= LUX_DARK:
                self.dim.is_dark = True

    @staticmethod
    def _t_no_motion(now_mono: float, pir_mono) -> float:
        if isinstance(pir_mono, (int, float)):
            try:
                return max(0.0, float(now_mono) - float(pir_mono))
            except Exception:
                return 1e9
        return 1e9

    def step(
        self,
        *,
        now_mono: float,
        pir_mono,
        brightness_target: float,
        brightness_cur: float,
    ) -> DisplayPowerDecision:
        """Evaluate next state and return a Decision snapshot (v1.1.2 compatible).

        Args:
          now_mono: current monotonic time
          pir_mono: state['pir_mono'] (monotonic timestamp of last motion)
          brightness_target: current target brightness (0..1)
          brightness_cur: current brightness (0..1)

        Returns:
          DisplayPowerDecision(dim=..., hdmi=..., hdmi_cmd=..., reason=...)
        """
        t_no_motion = self._t_no_motion(now_mono, pir_mono)
        prev_state = self.dim.disp_state
        prev_hdmi_is_off = self.hdmi.hdmi_is_off

        # Decide next state (exactly as v1.1.2), and attach a reason for debugging.
        reason = ""
        if t_no_motion <= PIR_WAKE_OVERRIDE_SEC:
            next_state = "ON"
            reason = "wake_override"
        else:
            if not self.dim.is_dark:
                next_state = "ON"
                reason = "not_dark"
            else:
                if (self.dim.disp_state != "OFF") and (t_no_motion >= DIM_AFTER_SEC):
                    next_state = "DIM"
                    reason = "idle_to_dim"
                else:
                    next_state = self.dim.disp_state
                    reason = "keep_state"

                # record DIM enter time
                if next_state == "DIM":
                    if self.dim.disp_state != "DIM" or self.dim.dim_enter_mono is None:
                        self.dim.dim_enter_mono = float(now_mono)
                else:
                    self.dim.dim_enter_mono = None

                # If target brightness has reached 0% in DIM, go OFF immediately
                if next_state == "DIM" and (brightness_target <= 1e-6) and (brightness_cur <= 1e-3):
                    next_state = "OFF"
                    reason = "brightness_zero_off"

                # Otherwise: DIM continues -> OFF after a grace period
                if (next_state == "DIM") and (self.dim.dim_enter_mono is not None):
                    if (float(now_mono) - float(self.dim.dim_enter_mono)) >= OFF_AFTER_DIM_SEC:
                        next_state = "OFF"
                        reason = "dim_timeout_off"

        # Commit
        self.dim.disp_state = next_state

        # Emit HDMI command only on transitions (guarded, v1.1.2 compatible)
        hdmi_cmd: str | None = None
        if self.dim.disp_state == "OFF" and not self.hdmi.hdmi_is_off:
            self.hdmi.hdmi_is_off = True
            hdmi_cmd = "OFF"
        elif self.dim.disp_state != "OFF" and self.hdmi.hdmi_is_off:
            self.hdmi.hdmi_is_off = False
            hdmi_cmd = "ON"

        # Return snapshots (callers should treat these as read-only views)
        decision = DisplayPowerDecision(
            prev_state=prev_state,
            prev_hdmi_is_off=bool(prev_hdmi_is_off),
            dim=replace(self.dim),
            hdmi=replace(self.hdmi),
            hdmi_cmd=hdmi_cmd,
            reason=reason,
        )

        # Fire transition hook only when there is something to track
        if self._on_transition is not None and (decision.prev_state != decision.dim.disp_state or decision.hdmi_cmd is not None or decision.prev_hdmi_is_off != decision.hdmi.hdmi_is_off):
            try:
                self._on_transition(
                    decision,
                    t_no_motion=t_no_motion,
                    brightness_target=brightness_target,
                    brightness_cur=brightness_cur,
                    is_dark=decision.dim.is_dark,
                )
            except Exception:
                pass

        return decision

LIGHT_OFF_TIMEOUT_SEC = 300  # 3 minutes to dim + 2 minutes -> light OFF

PIR_NO_MOTION_SEC = 3 * 60          # 3 minutes
PIR_DIM_TO = 0.20                   # 20%                   # 30%
PIR_FADE_SEC = 10.0                 # fade duration (sec)
PIR_WAKE_OVERRIDE_SEC = 2.0         # motion wakes screen immediately even if lux is low

# SR501 debug indicator (v1.0.0)
DEBUG_SR501 = False  # debug indicator removed
SR501_DOT_RADIUS = 7        # dot radius (px)
SR501_DOT_MARGIN = 10       # margin from bottom-right (px)

# --- BH1750 (Lux) ---
BH1750_ENABLE = True
BH1750_I2C_BUS = int(os.environ.get("BH1750_I2C_BUS", "1"))
BH1750_ADDR = int(os.environ.get("BH1750_ADDR", "0x23"), 16)  # 0x23 or 0x5C

BH1750_LIGHT_ON_LX = 5.0            # >= 5 lx => light ON
BH1750_WAKE_LX = 10.0               # >= 10 lx => wake to 100%
BH1750_DARK_LX = 2.0                # 0..2 lx => dark (lights off)
BH1750_POLL_SEC = 1.0               # poll interval
BH1750_DIM_TO_DARK = 0.00           # 0% when very dark
BH1750_DIM_TO_LIGHTOFF = 0.20       # 20% when light is OFF
BH1750_FADE_SEC = 10.0              # fade duration (sec)

# If you want to hard-disable the feature at runtime:
#   export PIR_ENABLE=0 / BH1750_ENABLE=0
if os.environ.get("PIR_ENABLE") == "0":
    PIR_ENABLE = False
if os.environ.get("BH1750_ENABLE") == "0":
    BH1750_ENABLE = False

def _run_cmd_silent(cmd):
    """Run a command without raising, but log failures for diagnosis.

    We use sudo -n in HDMI_*_CMD to ensure we never hang on a password prompt.
    Log file: /tmp/deskclock-hdmi-pm.log
    """
    import subprocess
    import time

    log_path = "/tmp/deskclock-hdmi-pm.log"
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if p.returncode != 0:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{ts}] rc={p.returncode} cmd={cmd}\n")
                    if p.stdout:
                        f.write(f"  stdout: {p.stdout.strip()}\n")
                    if p.stderr:
                        f.write(f"  stderr: {p.stderr.strip()}\n")
            except Exception:
                pass
    except Exception as e:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] EXC cmd={cmd} err={e}\n")
        except Exception:
            pass



# -----------------------------------------------------------------------------
# Time helpers
# -----------------------------------------------------------------------------

def _time_in_window(hhmm, start_hhmm, end_hhmm):
    """Return True if hhmm is within [start, end) allowing wrap over midnight."""
    (h, m) = hhmm
    (sh, sm) = start_hhmm
    (eh, em) = end_hhmm
    t = h * 60 + m
    s = sh * 60 + sm
    e = eh * 60 + em
    if s <= e:
        return s <= t < e
    return t >= s or t < e

def _night_window(dt):
    return _time_in_window((dt.hour, dt.minute), OFF_NIGHT_START, OFF_NIGHT_END)

def is_night_time(now: datetime) -> bool:
    h = now.hour
    if NIGHT_START_HOUR < NIGHT_END_HOUR:
        return NIGHT_START_HOUR <= h < NIGHT_END_HOUR
    return (h >= NIGHT_START_HOUR) or (h < NIGHT_END_HOUR)



# =========================



# -----------------------------------------------------------------------------
# SwitchBot integration
# -----------------------------------------------------------------------------

# =========================
SWITCHBOT_LIGHT_TIMEOUT_SEC = 8
SWITCHBOT_LIGHT_COOLDOWN_SEC = 3.0   # prevent rapid repeated commands
LIGHT_ON_REPEAT_SEC = 3.0            # unconditional second turnOn while PIR remains active
LIGHT_ON_VERIFY_SEC = 3.0            # allow BH1750 to observe the result of each transmission
LIGHT_ON_MAX_ATTEMPTS = 3            # initial + unconditional repeat + failed-verification retry
LIGHT_ON_MIN_RISE_LX = 2.0           # relative rise can confirm light below the absolute threshold
LIGHT_ON_MOTION_HOLD_SEC = 30.0       # finish verification after a short PIR pulse/API latency

# When motion happens in a dark state, briefly turn on the light to improve face recognition
# and then decide whether to keep it on.
LIGHT_PROBE_SEC = 8.0

# If Hiroshi is recognized, keep the light on longer.
HIROSHI_LIGHT_GRACE_SEC = 1800.0  # 30 minutes

# If no motion for this long, turn the light off.
LIGHT_OFF_TIMEOUT_SEC = 300.0  # 3 minutes to dim + 2 minutes

def switchbot_send_command(session: requests.Session, token: str, secret: str, device_id: str, command: str) -> dict:
    """Send a device command via SwitchBot Cloud API.

    command: e.g. "turnOn" / "turnOff"
    Returns parsed json dict (may include statusCode/message/body)
    """
    url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/commands"
    headers = make_switchbot_headers(token, secret)
    payload = switchbot_command_payload(command)
    try:
        r = session.post(url, headers=headers, json=payload, timeout=SWITCHBOT_LIGHT_TIMEOUT_SEC)
        r.raise_for_status()
        return r.json() if r.content else {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"SwitchBot cmd {command}: {type(e).__name__}: {e}"}

def switchbot_light_on(token: str, secret: str, light_device_id: str) -> dict:
    _log_light_event(f"command=ON api_command=turnOn device={light_device_id} requested")
    with requests.Session() as s:
        res = switchbot_send_command(s, token, secret, light_device_id, "turnOn")
    if not switchbot_command_succeeded(res):
        _log_light_event(f"command=ON api_command=turnOn device={light_device_id} result=NG error={res.get('error', '')}")
    else:
        _log_light_event(f"command=ON api_command=turnOn device={light_device_id} result=OK")
    return res

def switchbot_light_off(token: str, secret: str, light_device_id: str) -> dict:
    _log_light_event(f"command=OFF device={light_device_id} requested")
    with requests.Session() as s:
        res = switchbot_send_command(s, token, secret, light_device_id, "turnOff")
    if not switchbot_command_succeeded(res):
        _log_light_event(f"command=OFF device={light_device_id} result=NG error={res.get('error', '')}")
    else:
        _log_light_event(f"command=OFF device={light_device_id} result=OK")
    return res


# =========================
# Face recognition (call external script using system python)
# =========================
FACE_RECOG_PY = "/usr/bin/python3"
FACE_RECOG_SCRIPT = os.path.expanduser("~/deskclock/face/recognize_once.py")
FACE_RECOG_TIMEOUT_SEC = 12

def run_face_recognize_once() -> dict:
    """Run recognize_once.py and parse JSON output.

    Returns dict. Expected keys (best-effort): ok, found_face, is_authorized_user, confidence
    """
    import subprocess, json

    if not os.path.exists(FACE_RECOG_SCRIPT):
        return {"ok": False, "error": "recognize_script_missing", "path": FACE_RECOG_SCRIPT}

    try:
        p = subprocess.run(
            [FACE_RECOG_PY, FACE_RECOG_SCRIPT],
            capture_output=True,
            text=True,
            timeout=FACE_RECOG_TIMEOUT_SEC,
            check=False,
        )
        out = (p.stdout or "").strip()
        # Some OpenCV warnings may be printed to stdout; try to extract last JSON object.
        jtxt = out
        if "{" in out and "}" in out:
            jtxt = out[out.rfind("{"): out.rfind("}") + 1]
        data = json.loads(jtxt)
        if not isinstance(data, dict):
            return {"ok": False, "error": "bad_json_type", "raw": jtxt}
        return data
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def fetch_internet_loop(shared, stop_event):
    """Fetch 'Internet' temperature/humidity (and optionally weather_code) from Open-Meteo.

    Used as a selectable source for indoor/outdoor values. Writes to:
      - net_temp_c
      - net_hum_pct
      - net_weather_code
      - net_ts
      - net_err
    """
    url = (
        f"{OPEN_METEO_BASE_URL}?latitude={LAT}&longitude={LON}"
        f"&timezone={TIMEZONE}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
    )
    headers = {"User-Agent": "deskclock/1.0"}

    with requests.Session() as s:
        while not stop_event.is_set():
            try:
                j = _http_get_json(s, url, headers=headers, timeout=8)
                cur = (j or {}).get("current", {})
                shared["net_temp_c"] = float(cur["temperature_2m"])
                shared["net_hum_pct"] = int(round(cur["relative_humidity_2m"]))
                shared["net_weather_code"] = int(cur.get("weather_code")) if cur.get("weather_code") is not None else None
                shared["net_err"] = ""
                shared["net_ts"] = time.time()
            except Exception as e:
                shared["net_err"] = f"{type(e).__name__}: {e}"

            stop_event.wait(WEATHER_REFRESH_SEC)



# -----------------------------------------------------------------------------
# UI state persistence
# -----------------------------------------------------------------------------

    for step in range(1, len(order) + 1):
        cand = order[(start + step) % len(order)]
        if is_valid_fn(cand):
            return cand
    return current


# -------------------------
# Main entrypoint
# -------------------------



# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Phase 4 (v2 skeleton): Renderer split (UI split)
#   - Keep rendering behavior identical
#   - Move frame rendering (including touch-rect calc and flip) into Renderer
# -----------------------------------------------------------------------------


def main():
    pygame.init()

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)

    sw, sh = screen.get_size()

    renderer = ClockRenderer(screen=screen, sw=sw, sh=sh)

    # 起動時バージョン表示（3秒）
    show_startup_version(screen, sw, sh, __product__, __version__)

    # ★ splash → 本表示 切り替え用ワンショット flip（環境依存の固定化対策）
    screen.fill((0, 0, 0))
    pygame.display.flip()

    # Render/layout and service wiring are built through dedicated bootstrap helpers.
    ui = build_ui_dependencies(sw=sw, sh=sh)
    w, h = ui.w, ui.h
    canvas = ui.canvas
    font_main_size = ui.font_main_size
    font_sec_size = ui.font_sec_size
    font_ampm_size = ui.font_ampm_size
    base_info_size = ui.base_info_size
    TXT_RAISE_RATIO = ui.TXT_RAISE_RATIO
    TXT_SCALE_DATE_OUT = ui.TXT_SCALE_DATE_OUT
    EXTRA_GAP_BETWEEN_LINES = ui.EXTRA_GAP_BETWEEN_LINES
    EXTRA_GAP_BETWEEN_WEATHER_LINES = ui.EXTRA_GAP_BETWEEN_WEATHER_LINES
    LABEL_RATIO = ui.LABEL_RATIO
    LABEL_GAP_RATIO = ui.LABEL_GAP_RATIO
    IN_LABEL_LEFT_CHARS = ui.IN_LABEL_LEFT_CHARS
    IN_LABEL_DOWN_CHARS = ui.IN_LABEL_DOWN_CHARS
    OUT_ROW_SHIFT_DIGITS = ui.OUT_ROW_SHIFT_DIGITS
    OUT_VALUE_SHIFT_PX = ui.OUT_VALUE_SHIFT_PX
    DAY_ROOMTEMP_GAP_PX = ui.DAY_ROOMTEMP_GAP_PX
    WEEKDAY_SHIFT_PX = ui.WEEKDAY_SHIFT_PX
    UNIT_LABEL_PAD_PX = ui.UNIT_LABEL_PAD_PX
    WEEKDAY_ASCENT_ADJUST_PX = ui.WEEKDAY_ASCENT_ADJUST_PX
    OUTDOOR_ROW_SHIFT_DOWN_PX = ui.OUTDOOR_ROW_SHIFT_DOWN_PX
    font_7seg_main = ui.font_7seg_main
    font_7seg_sec = ui.font_7seg_sec
    info_font_path = ui.info_font_path
    font_ampm = ui.font_ampm
    AMPM_SLOT_W = ui.AMPM_SLOT_W
    DIGIT_W = ui.DIGIT_W
    DIGIT_H = ui.DIGIT_H
    GAP_AMPM = ui.GAP_AMPM
    LONG_PRESS_SEC = ui.LONG_PRESS_SEC
    pressing = False
    press_start = 0.0
    long_press_fired = False

    # ===== Touch toggle modes / runtime state =====
    _ui = load_ui_state()
    state = ClockState.from_ui_snapshot(_ui)
    CAL_ANIM_SEC = ui.CAL_ANIM_SEC
    CAL_POPUP_TIMEOUT_SEC = ui.CAL_POPUP_TIMEOUT_SEC

    # Display Power Manager state (v2 skeleton: StateMachine)
    dpm = DisplayPowerStateMachine()  # fully compatible with v1.1.2 rules
    disp_state = dpm.disp_state       # "ON" | "DIM" | "OFF" (for legacy references)

    # Light control (SwitchBot + face recognition)
    sb_token = os.environ.get("SWITCHBOT_TOKEN")
    sb_secret = os.environ.get("SWITCHBOT_SECRET")
    sb_light_id = os.environ.get("SWITCHBOT_lightDeviceId")

    state.light.enabled = bool(sb_token and sb_secret and sb_light_id)
    state.light.is_on = False  # our internal state (best-effort)
    state.light.last_cmd_mono = 0.0
    state.light.probe_until_mono = 0.0
    state.light.authorized_user_until_mono = 0.0
    state.light.deadline_mono = (
        arm_light_off(time.monotonic(), LIGHT_OFF_TIMEOUT_SEC)
        if state.light.enabled
        else 0.0
    )
    state.light.prev_pir_value = int(state.pir_value or 0)
    state.light.on_verify_active = False
    state.light.on_baseline_lux = None
    state.light.on_next_action_mono = 0.0
    state.light.on_next_action = ""
    state.light.on_attempts = 0
    state.light.on_failed_latched = False
    state.light.face_recognition_pending = False

    stop_event = threading.Event()
    service_deps = build_service_dependencies(state=state, stop_event=stop_event)
    sensor_manager = service_deps.sensor_manager
    sensor_flags = service_deps.sensor_flags
    use_switchbot = sensor_flags["use_switchbot"]
    use_switchbot_in = sensor_flags["use_switchbot_in"]

    # Start all registered background workers (Step 3: SensorManager)
    sensor_manager.start_all()

    clock = pygame.time.Clock()

    running = True
    # Dynamic brightness (Step 4: BrightnessController)
    brightness_ctrl = service_deps.brightness_ctrl
    brightness_cur = brightness_ctrl.brightness_cur
    brightness_target = brightness_ctrl.brightness_target

    while running:
        color_changed = False
        now_mono = time.monotonic()


        # Long-press: reset color to white (works for both mouse and touchscreen)
        if pressing and (not long_press_fired) and ((now_mono - press_start) >= LONG_PRESS_SEC):
            state.base_color = (255, 255, 255)
            color_changed = True
            long_press_fired = True


        def _event_pos_to_screen(ev):
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                return ev.pos
            if ev.type in (pygame.FINGERDOWN, pygame.FINGERUP):
                return (int(ev.x * sw), int(ev.y * sh))
            return None

        def _pt_in_rect(pt, r):
            if pt is None or r is None:
                return False
            return r.collidepoint(pt)

        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False

            if e.type == pygame.MOUSEBUTTONDOWN or e.type == pygame.FINGERDOWN:
                state.activity_mono = now_mono
                pressing = True
                press_start = now_mono
                long_press_fired = False

            if e.type == pygame.MOUSEBUTTONUP or e.type == pygame.FINGERUP:
                state.activity_mono = now_mono
                if pressing:
                    pressing = False
                    if not long_press_fired:
                        pt = _event_pos_to_screen(e)

                        # Calendar popup controls (no popup open/close animation)
                        if state.calendar.popup:
                            if _pt_in_rect(pt, state.touch_rects_screen.get("cal_prev")):
                                if state.calendar.month_offset > -3:
                                    state.calendar.month_offset -= 1
                                state.calendar.open_mono = now_mono
                                continue
                            if _pt_in_rect(pt, state.touch_rects_screen.get("cal_next")):
                                if state.calendar.month_offset < 3:
                                    state.calendar.month_offset += 1
                                state.calendar.open_mono = now_mono
                                continue
                            # any other tap closes the popup immediately
                            state.calendar.popup = False
                            state.calendar.anim_phase = "closed"
                            state.calendar.anim_t0 = 0.0
                            state.calendar.open_mono = 0.0
                            state.calendar.month_offset = 0
                            continue

                        # Weather icon tap -> cycle theme
                        if _pt_in_rect(pt, state.touch_rects_screen.get("weather")):
                            state.theme = next_theme_name(getattr(state, "theme", "default"))
                            state.save_ui_state(save_ui_state)
                            continue

                        # Date area tap -> open calendar popup immediately
                        if _pt_in_rect(pt, state.touch_rects_screen.get("date")):
                            state.calendar.month_offset = 0
                            state.calendar.popup = True
                            state.calendar.open_mono = now_mono
                            state.calendar.anim_phase = "open"
                            state.calendar.anim_t0 = 0.0
                            continue

                        # Air value blocks: independently toggle the selected source/value.
                        if _pt_in_rect(pt, state.touch_rects_screen.get("air_left")):
                            state.air_left_mode = "PRESSURE" if state.air_left_mode == "ECO2" else "ECO2"
                            state.save_ui_state(save_ui_state)
                            continue
                        if _pt_in_rect(pt, state.touch_rects_screen.get("air_right")):
                            state.air_right_mode = "CO2" if state.air_right_mode == "TVOC" else "TVOC"
                            state.save_ui_state(save_ui_state)
                            continue


                        # 1) Indoor touch -> cycle SHT20 → SWITCHBOT → BME280 (skip invalid)
                        if _pt_in_rect(pt, state.touch_rects_screen.get("indoor")):
                            state.indoor_mode = next_valid_source(
                                state.indoor_mode,
                                INDOOR_SOURCES,
                                lambda s: indoor_source_valid(s, state, use_switchbot_in, SHT20_REFRESH_SEC, state.sht20_ts),
                            )
                            state.save_ui_state(save_ui_state)

                        

                        # 2) Outdoor touch -> cycle SWITCHBOT → Internet (skip invalid)
                        elif _pt_in_rect(pt, state.touch_rects_screen.get("outdoor")):
                            state.outdoor_mode = next_valid_source(
                                state.outdoor_mode,
                                OUTDOOR_SOURCES,
                                lambda s: outdoor_source_valid(s, state, use_switchbot),
                            )
                            state.save_ui_state(save_ui_state)

                        

                        # 3) Time-hour area -> toggle 12h/24h
                        elif _pt_in_rect(pt, state.touch_rects_screen.get("time")):
                            state.time_mode_24h = (not state.time_mode_24h)
                            state.save_ui_state(save_ui_state)

                        

                        # 4) Other area -> old behavior (random color)
                        else:
                            state.base_color = random_bright_color()
                            color_changed = True


        if color_changed:
            state.save_ui_state(save_ui_state)

        ntp_synced, colon_visible = ntp_monitor_update(state.ntp_state, now_mono)
        state.ntp_synced = ntp_synced
        state.colon_visible = colon_visible
        now = datetime.now()
        # Background calendar prewarm/cache refresh (startup + every month rollover)
        try:
            renderer.warm_calendar_cache_step(now=now, w=w, h=h, info_font_path=info_font_path, budget_steps=2)
        except Exception:
            pass

        # --- Calendar popup auto close (10 minutes, immediate close) ---
        if state.calendar.popup and state.calendar.open_mono > 0.0:
            if (now_mono - state.calendar.open_mono) >= CAL_POPUP_TIMEOUT_SEC:
                state.calendar.popup = False
                state.calendar.anim_phase = "closed"
                state.calendar.anim_t0 = 0.0
                state.calendar.open_mono = 0.0
                state.calendar.month_offset = 0

        # --- Calendar popup visibility (animations disabled) ---
        calendar_anim = 1.0 if state.calendar.popup else 0.0
        state.calendar.anim_phase = "open" if state.calendar.popup else "closed"

        # --- Display Power Manager: evaluate ON/DIM/OFF ---
        if DISPLAY_PM_ENABLE:
            # Compute time since last motion
            pir_mono = state.pir_mono
            if isinstance(pir_mono, (int, float)):
                t_no_motion = max(0.0, now_mono - float(pir_mono))
            else:
                t_no_motion = 1e9

            # Lux (BH1750). Missing lux -> treat as bright (avoid OFF)
            lux = state.lux
            try:
                lux_f = float(lux) if lux is not None else None
            except Exception:
                lux_f = None

            # Dark hysteresis (v1.1.2 compatible)
            dpm.update_dark(lux_f)
            is_dark = dpm.is_dark

            night_ok = _night_window(now)

            # --- Light control (init in this scope; avoid NameError) ---
            sb_token = os.environ.get("SWITCHBOT_TOKEN")
            sb_secret = os.environ.get("SWITCHBOT_SECRET")
            sb_light_id = os.environ.get("SWITCHBOT_lightDeviceId")

            state.light.enabled = bool(sb_token and sb_secret and sb_light_id)

            # --- Light control trigger: when dark & DIM/OFF and PIR rising edge ---
            pir_v = int(state.pir_value or 0)
            pir_rise = (pir_v == 1 and state.light.prev_pir_value == 0)
            state.light.prev_pir_value = pir_v

            # --- Light control (SwitchBot + face recognition) ---
            # Independent from display PM:
            # - Any motion => light ON immediately and (re)arm a fixed 5-minute OFF timer.
            # - If no motion continues and the timer expires => light OFF.
            # - On PIR rising edge (and only when dark / DIM / OFF), we run face recognition once.
            #   Recognition does not extend the no-motion OFF timer.
            if state.light.enabled:
                if pir_rise:
                    # A new detection may retry a cycle that previously exhausted its attempts.
                    state.light.on_failed_latched = False

                light_cycle_motion_active = (
                    pir_v == 1
                    or (
                        state.light.on_verify_active
                        and t_no_motion <= LIGHT_ON_MOTION_HOLD_SEC
                    )
                )
                if light_cycle_motion_active:
                    # Start one verification cycle per continuous PIR detection.
                    if (
                        pir_v == 1
                        and not state.light.is_on
                        and not state.light.on_verify_active
                        and not state.light.on_failed_latched
                        and ((now_mono - state.light.last_cmd_mono) >= SWITCHBOT_LIGHT_COOLDOWN_SEC)
                    ):
                        r = switchbot_light_on(sb_token, sb_secret, sb_light_id)
                        state.light.last_cmd_mono = now_mono
                        state.light.on_verify_active = True
                        state.light.on_baseline_lux = lux_f
                        state.light.on_attempts = 1
                        state.light.on_next_action = "repeat"
                        state.light.on_next_action_mono = now_mono + LIGHT_ON_REPEAT_SEC
                        state.light.face_recognition_pending = bool(
                            pir_rise and (is_dark or disp_state in ("DIM", "OFF"))
                        )
                        _log_light_event(
                            f"verification=start baseline_lux={lux_f!r} attempts=1 "
                            f"api_ok={switchbot_command_succeeded(r)}"
                        )

                    if (
                        state.light.on_verify_active
                        and now_mono >= state.light.on_next_action_mono
                    ):
                        if state.light.on_next_action == "repeat":
                            # This is deliberately unconditional with respect to the estimated
                            # light state. Motion is still recent, so send the exact turnOn again.
                            r = switchbot_light_on(sb_token, sb_secret, sb_light_id)
                            state.light.last_cmd_mono = now_mono
                            state.light.on_attempts += 1
                            state.light.on_next_action = "verify"
                            state.light.on_next_action_mono = now_mono + LIGHT_ON_VERIFY_SEC
                            _log_light_event(
                                f"verification=repeat-turnOn attempts={state.light.on_attempts} "
                                f"api_ok={switchbot_command_succeeded(r)}"
                            )

                        elif state.light.on_next_action == "verify":
                            lux_fresh = lux_sample_is_fresh(
                                now_mono=now_mono,
                                lux_mono=state.lux_mono,
                                stale_sec=BH1750_STALE_SEC,
                            )
                            confirmed = lux_fresh and light_is_confirmed(
                                baseline_lux=state.light.on_baseline_lux,
                                current_lux=lux_f,
                                light_on_lx=BH1750_LIGHT_ON_LX,
                                min_rise_lx=LIGHT_ON_MIN_RISE_LX,
                            )
                            if confirmed:
                                state.light.is_on = True
                                state.light.on_verify_active = False
                                state.light.on_next_action = ""
                                _log_light_event(
                                    f"verification=confirmed lux={lux_f!r} "
                                    f"baseline_lux={state.light.on_baseline_lux!r} "
                                    f"attempts={state.light.on_attempts}"
                                )
                                # Face recognition can block for up to 12 seconds, so it runs
                                # only after retransmission and physical light verification finish.
                                if state.light.face_recognition_pending:
                                    state.light.face_recognition_pending = False
                                    fr = run_face_recognize_once()
                                    if isinstance(fr, dict) and fr.get("ok") and fr.get("is_authorized_user") is True:
                                        state.light.authorized_user_until_mono = now_mono + HIROSHI_LIGHT_GRACE_SEC
                            elif state.light.on_attempts < LIGHT_ON_MAX_ATTEMPTS:
                                r = switchbot_light_on(sb_token, sb_secret, sb_light_id)
                                state.light.last_cmd_mono = now_mono
                                state.light.on_attempts += 1
                                state.light.on_next_action_mono = now_mono + LIGHT_ON_VERIFY_SEC
                                _log_light_event(
                                    f"verification=retry-turnOn lux={lux_f!r} lux_fresh={lux_fresh} "
                                    f"attempts={state.light.on_attempts} "
                                    f"api_ok={switchbot_command_succeeded(r)}"
                                )
                            else:
                                _log_light_event(
                                    f"点灯確認失敗 lux={lux_f!r} lux_fresh={lux_fresh} "
                                    f"baseline_lux={state.light.on_baseline_lux!r} "
                                    f"attempts={state.light.on_attempts}"
                                )
                                state.light.is_on = False
                                state.light.on_verify_active = False
                                state.light.on_next_action = ""
                                state.light.on_failed_latched = True
                                state.light.face_recognition_pending = False

                    # Every detection restarts the fixed no-motion deadline.
                    # Identity recognition must not keep an empty room lit.
                    if pir_v == 1:
                        state.light.deadline_mono = arm_light_off(now_mono, LIGHT_OFF_TIMEOUT_SEC)

                else:
                    # No motion: if the timer has expired, turn OFF (best-effort)
                    if light_off_due(
                        now_mono=now_mono,
                        deadline_mono=state.light.deadline_mono,
                        last_cmd_mono=state.light.last_cmd_mono,
                        cooldown_sec=SWITCHBOT_LIGHT_COOLDOWN_SEC,
                    ):
                        r = switchbot_light_off(sb_token, sb_secret, sb_light_id)
                        state.light.last_cmd_mono = now_mono
                        if switchbot_command_succeeded(r):
                            state.light.is_on = False
                            state.light.on_verify_active = False
                            state.light.on_next_action = ""
                            state.light.on_attempts = 0
                            state.light.face_recognition_pending = False
                            state.light.deadline_mono = 0.0
                            state.light.authorized_user_until_mono = 0.0

            # StateMachine: decide next display state and HDMI command (fully compatible)
            decision = dpm.step(
                now_mono=now_mono,
                pir_mono=pir_mono,
                brightness_target=brightness_target,
                brightness_cur=brightness_cur,
            )
            hdmi_cmd = decision.hdmi_cmd
            disp_state = dpm.disp_state

            # Log display power state transitions for troubleshooting.
            # DPM transition logging is handled by DisplayPowerStateMachine._on_transition


            if hdmi_cmd == "OFF":
                _run_cmd_silent(HDMI_OFF_CMD)
            elif hdmi_cmd == "ON":
                _run_cmd_silent(HDMI_ON_CMD)

        # --- Brightness control (v2 skeleton: controller) ---
        br_decision = brightness_ctrl.update(
            now_mono=now_mono,
            shared=state,
            disp_state=disp_state,
        )
        brightness_cur = br_decision.state.brightness_cur
        brightness_target = br_decision.state.brightness_target
        state.brightness_cur = brightness_cur
        state.brightness_target = brightness_target
        desired = br_decision.desired

        theme_spec = get_theme_spec(getattr(state, "theme", "default"))
        fg_base = state.base_color if getattr(theme_spec, "use_base_color", False) else theme_spec.fg_color
        render_color = _apply_brightness(fg_base, brightness_cur)


        # Time display: always compute hour digits explicitly to avoid math/caching issues.
        if state.time_mode_24h:
            ampm = ""  # keep slot reserved in layout
            hour24 = now.hour  # 0-23
            if hour24 >= 10:
                hour_tens_char = str(hour24 // 10)
            else:
                hour_tens_char = None
            hour_ones_char = str(hour24 % 10)
        else:
            ampm = "午前" if now.hour < 12 else "午後"
            h12 = now.hour % 12 or 12
            if h12 >= 10:
                hour_tens_char = str(h12 // 10)
            else:
                hour_tens_char = None
            hour_ones_char = str(h12 % 10)

        # Colon indicator: hide ':' only when NTP is persistently unsynced.
        # Keep the same string length by using a leading space instead of ':'.
        colon_min = (":" if colon_visible else " ") + f"{now.minute:02d}"
        ss = f"{now.second:02d}"
        # Month/Day: reserve 2-digit width (space-padded) so 10-12 doesn't squeeze.
        # Keep the width for months 1-9 by using a leading space (" 2"), so 10-12 fit without shrinking layout.
        m_field = f"{now.month:2d}"
        d_field = f"{now.day:2d}"
        # Date display (digits in 7-seg, unit labels in normal font):
        #   YYYY年 M月 D日 <weekday>曜日
        # NOTE: Avoid excessive spaces here; too wide date text forces the whole bottom font size down.
        date_prefix_text = f"{now.year:04d}年{m_field}月{d_field}日"
        date_weekday_char = f"{weekday_ja(now)}"
        date_day_suffix = "曜日"
        date_text = date_prefix_text + date_weekday_char + date_day_suffix

        # --- Selectable sources (touch-toggle) ---
        # Outdoor
        if state.outdoor_mode == "SWITCHBOT":
            out_temp = state.out_temp_c
            out_hum = state.out_hum_pct
        else:
            out_temp = state.net_temp_c
            out_hum = state.net_hum_pct
        out_text = fmt_temp_hum(out_temp, out_hum)

        # Indoor (v0.9.8p1 FIX): keep SHT20 vs SwitchBot values separate so toggling actually changes numbers.
        if state.indoor_mode == "SHT20":
            in_temp = state.sht20_temp_c
            in_hum  = state.sht20_hum_pct
        elif state.indoor_mode == "AHT21":
            in_temp = state.aht21_temp_c
            in_hum  = state.aht21_hum_pct
        elif state.indoor_mode == "SWITCHBOT":
            in_temp = state.in_temp_c
            in_hum  = state.in_hum_pct
        elif state.indoor_mode == "BME280":
            in_temp = state.bme280_temp_c
            in_hum  = state.bme280_hum_pct
        else:
            # Fallback: whatever is available
            in_temp = state.in_temp_c
            in_hum  = state.in_hum_pct
        in_text = fmt_temp_hum(in_temp, in_hum)

        wcode = state.weather_code
        ens_ts = state.ens_ts
        ens_fresh = _is_fresh(ens_ts, max_age_sec=ENS160_VALUE_STALE_SEC)
        ens_aqi = state.ens_aqi if ens_fresh else None
        ens_tvoc = state.ens_tvoc_ppb if ens_fresh else None
        ens_eco2 = state.ens_eco2_ppm if ens_fresh else None

        bme280_fresh = _is_fresh(state.bme280_ts, max_age_sec=BME280_VALUE_STALE_SEC)
        scd40_fresh = _is_fresh(state.scd40_ts, max_age_sec=SCD40_VALUE_STALE_SEC)
        if state.air_left_mode == "PRESSURE":
            air_left_value = round(state.bme280_pressure_hpa) if bme280_fresh and state.bme280_pressure_hpa is not None else None
            air_left_unit = "hPa"
            air_left_source = "BME280"
        else:
            air_left_value = ens_eco2
            air_left_unit = "PPM"
            air_left_source = "ENS160"

        if state.air_right_mode == "CO2":
            air_right_value = state.scd40_co2_ppm if scd40_fresh else None
            air_right_unit = "PPM"
            air_right_source = "SCD40"
        else:
            air_right_value = ens_tvoc
            air_right_unit = "PPB"
            air_right_source = "ENS160"

        key = f"{int(state.calendar.popup)}{state.calendar.anim_phase}{int(calendar_anim*1000)}{ntp_synced}{int(state.time_mode_24h)}{ampm}{hour_tens_char}{hour_ones_char}{colon_min}{ss}{date_text}{out_text}{in_text}{wcode}{ens_aqi}{state.air_left_mode}{air_left_value}{state.air_right_mode}{air_right_value}{state.theme}{render_color}"
        if key != state.last_key or color_changed:
            # Build BottomInfoCtx safely (Phase5 ctor guard)
            bottom_kwargs = dict(
                info_font_path=info_font_path,
                base_info_size=base_info_size,
                TXT_SCALE_DATE_OUT=TXT_SCALE_DATE_OUT,
                TXT_RAISE_RATIO=TXT_RAISE_RATIO,
                LABEL_RATIO=LABEL_RATIO,
                LABEL_GAP_RATIO=LABEL_GAP_RATIO,
                EXTRA_GAP_BETWEEN_LINES=EXTRA_GAP_BETWEEN_LINES,
                EXTRA_GAP_BETWEEN_WEATHER_LINES=EXTRA_GAP_BETWEEN_WEATHER_LINES,
                IN_LABEL_LEFT_CHARS=IN_LABEL_LEFT_CHARS,
                IN_LABEL_DOWN_CHARS=IN_LABEL_DOWN_CHARS,
                OUT_ROW_SHIFT_DIGITS=OUT_ROW_SHIFT_DIGITS,
                OUT_VALUE_SHIFT_PX=OUT_VALUE_SHIFT_PX,
                DAY_ROOMTEMP_GAP_PX=DAY_ROOMTEMP_GAP_PX,
                WEEKDAY_SHIFT_PX=WEEKDAY_SHIFT_PX,
                UNIT_LABEL_PAD_PX=UNIT_LABEL_PAD_PX,
                WEEKDAY_ASCENT_ADJUST_PX=WEEKDAY_ASCENT_ADJUST_PX,
                OUTDOOR_ROW_SHIFT_DOWN_PX=OUTDOOR_ROW_SHIFT_DOWN_PX,
                date_text=date_text,
                date_weekday_char=date_weekday_char,
                date_day_suffix=date_day_suffix,
                m_field=m_field,
                d_field=d_field,
                in_text=in_text,
                out_text=out_text,
            )
            _bf = getattr(BottomInfoCtx, '__dataclass_fields__', {})
            if 'indoor_mode' in _bf: bottom_kwargs['indoor_mode'] = state.indoor_mode
            if 'outdoor_mode' in _bf: bottom_kwargs['outdoor_mode'] = state.outdoor_mode
            if 'ens_fresh' in _bf: bottom_kwargs['ens_fresh'] = ens_fresh
            if 'in_temp' in _bf: bottom_kwargs['in_temp'] = in_temp
            if 'in_hum' in _bf: bottom_kwargs['in_hum'] = in_hum
            if 'out_temp' in _bf: bottom_kwargs['out_temp'] = out_temp
            if 'out_hum' in _bf: bottom_kwargs['out_hum'] = out_hum
            if 'ens_aqi' in _bf: bottom_kwargs['ens_aqi'] = ens_aqi
            if 'ens_tvoc' in _bf: bottom_kwargs['ens_tvoc'] = ens_tvoc
            if 'ens_eco2' in _bf: bottom_kwargs['ens_eco2'] = ens_eco2
            if 'air_left_kind' in _bf: bottom_kwargs['air_left_kind'] = state.air_left_mode
            if 'air_left_value' in _bf: bottom_kwargs['air_left_value'] = air_left_value
            if 'air_left_unit' in _bf: bottom_kwargs['air_left_unit'] = air_left_unit
            if 'air_left_source' in _bf: bottom_kwargs['air_left_source'] = air_left_source
            if 'air_right_kind' in _bf: bottom_kwargs['air_right_kind'] = state.air_right_mode
            if 'air_right_value' in _bf: bottom_kwargs['air_right_value'] = air_right_value
            if 'air_right_unit' in _bf: bottom_kwargs['air_right_unit'] = air_right_unit
            if 'air_right_source' in _bf: bottom_kwargs['air_right_source'] = air_right_source
            bottom_ctx = BottomInfoCtx(**bottom_kwargs)

            renderer.render_and_update_touch_rects(
            ctx=RenderCtx(
            canvas=canvas,
            w=w,
            h=h,
            UI_SCALE=UI_SCALE,
            touch_rects_screen=state.touch_rects_screen,
            render_color=render_color,
            top=TopLineCtx(
            font_ampm=font_ampm,
            font_7seg_main=font_7seg_main,
            font_7seg_sec=font_7seg_sec,
            AMPM_SLOT_W=AMPM_SLOT_W,
            GAP_AMPM=GAP_AMPM,
            DIGIT_W=DIGIT_W,
            DIGIT_H=DIGIT_H,
            font_main_size=font_main_size,
            ampm=ampm,
            hour_tens_char=hour_tens_char,
            hour_ones_char=hour_ones_char,
            colon_min=colon_min,
            ss=ss,
            WEATHER_ICON_ENABLE=WEATHER_ICON_ENABLE,
            WEATHER_ICON_SCALE=WEATHER_ICON_SCALE,
            WEATHER_ICON_MARGIN_Y=WEATHER_ICON_MARGIN_Y,
            WEATHER_ICON_STROKE=WEATHER_ICON_STROKE,
            WEATHER_ICON_RAISE_PX=WEATHER_ICON_RAISE_PX,
            ),
                        bottom=bottom_ctx,
            weather=state,
            brightness_cur=brightness_cur,
            now=now,
            calendar_popup=state.calendar.popup,
            calendar_anim=calendar_anim,
            calendar_month_offset=state.calendar.month_offset,
            theme=state.theme,
            )
            )

            state.last_key = key

        clock.tick(30)

    stop_event.set()
    pygame.quit()

if __name__ == "__main__":
    main()
