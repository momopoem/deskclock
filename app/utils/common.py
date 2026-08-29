# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import pygame

from config import (
    APP_VERSION,
    INFO_FONT_CANDIDATES,
    INDOOR_SOURCES,
    OUTDOOR_SOURCES,
    STATE_DIR,
    STATE_PATH,
    SWITCHBOT_REFRESH_SEC,
    WEATHER_REFRESH_SEC,
    BME280_VALUE_STALE_SEC,
)


def _log_version_to_clocklog() -> None:
    try:
        p = Path.home() / "deskclock" / "log" / "clock.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"DeskSide Clock Version: {APP_VERSION}\n")
    except Exception:
        pass


def _log_dpm_event(message: str) -> None:
    try:
        p = Path.home() / "deskclock" / "log" / "clock.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [DPM] {message}\n")
    except Exception:
        pass


def _log_brt_event(message: str) -> None:
    try:
        p = Path.home() / "deskclock" / "log" / "clock.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [BRT] {message}\n")
    except Exception:
        pass


def _log_light_event(message: str) -> None:
    try:
        p = Path.home() / "deskclock" / "log" / "clock.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [LGT] {message}\n")
    except Exception:
        pass


def show_startup_version(screen, sw, sh, product_name: str, version: str):
    screen.fill((0, 0, 0))
    w, h = sw, sh
    title_font = pygame.font.SysFont(None, int(h * 0.10))
    ver_font = pygame.font.SysFont(None, int(h * 0.06))
    title_surf = title_font.render(product_name, True, (255, 255, 255))
    ver_surf = ver_font.render(f"Version {version}", True, (255, 255, 255))
    title_x = (w - title_surf.get_width()) // 2
    title_y = (h // 2) - title_surf.get_height()
    ver_x = (w - ver_surf.get_width()) // 2
    ver_y = (h // 2) + int(ver_surf.get_height() * 0.3)
    screen.blit(title_surf, (title_x, title_y))
    screen.blit(ver_surf, (ver_x, ver_y))
    pygame.display.flip()
    clock = pygame.time.Clock()
    start_ms = pygame.time.get_ticks()
    while (pygame.time.get_ticks() - start_ms) < 3000:
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return
            if e.type == pygame.QUIT:
                return
        pygame.event.pump()
        clock.tick(30)
    pygame.event.clear()


def apply_dim(color, ratio: float):
    r, g, b = color
    return (int(r * ratio), int(g * ratio), int(b * ratio))


def pick_info_font_path():
    for p in INFO_FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


_FONT_CACHE = {}


def load_font(path, size):
    try:
        size = int(size)
    except Exception:
        size = 16
    key = (path or "", size)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    font = None
    if path:
        try:
            if os.path.exists(path):
                font = pygame.font.Font(path, size)
        except Exception:
            font = None
    if font is None:
        font = pygame.font.Font(None, size)
    _FONT_CACHE[key] = font
    return font


def weekday_ja(dt):
    return ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]


def is_7seg_char(ch: str) -> bool:
    return ch.isdigit() or ch in " -.:"


def fmt_temp_field(temp):
    if temp is None:
        return " --.-"
    return f"{temp:5.1f}"


def fmt_hum_field(hum):
    if hum is None:
        return "--"
    return f"{int(round(hum)):d}"


def fmt_temp_hum(temp, hum):
    t = fmt_temp_field(temp)
    hstr = fmt_hum_field(hum)
    return f"{t}°C {hstr}%"


def _measure_7seg_width(font_7seg, sample: str = "0") -> int:
    try:
        return int(font_7seg.render(sample, True, (255, 255, 255)).get_width())
    except Exception:
        return 0


def _dot_x_from_temp_field(font_7seg, temp_field: str) -> int:
    idx = (temp_field or "").find(".")
    if idx < 0:
        return -1
    return idx * _measure_7seg_width(font_7seg)


def render_run(font_7seg, font_txt, s, color, digit_w_7seg=None):
    parts = []
    buf = ""
    mode_is_7 = None

    def flush():
        nonlocal buf, mode_is_7
        if not buf:
            return
        if mode_is_7 and (digit_w_7seg is not None):
            ascent = font_7seg.get_ascent()
            h = font_7seg.get_height()
            run = ""
            for ch in buf:
                if ch == " ":
                    if run:
                        surf_run = font_7seg.render(run, True, color)
                        parts.append((surf_run, ascent, True))
                        run = ""
                    parts.append((make_blank_slot(digit_w_7seg, h), ascent, True))
                else:
                    run += ch
            if run:
                surf_run = font_7seg.render(run, True, color)
                parts.append((surf_run, ascent, True))
        else:
            f = font_7seg if mode_is_7 else font_txt
            surf = f.render(buf, True, color)
            parts.append((surf, f.get_ascent(), mode_is_7))
        buf = ""

    for ch in s:
        is7 = is_7seg_char(ch)
        if mode_is_7 is None:
            mode_is_7 = is7
            buf = ch
        elif is7 == mode_is_7:
            buf += ch
        else:
            flush()
            mode_is_7 = is7
            buf = ch
    flush()
    return parts


def total_width(parts):
    return sum(s.get_width() for s, _, _ in parts)


def blit_hstack_baseline(screen, parts, x, baseline_y, raise_txt_px):
    cx = x
    for surf, ascent, is_7seg in parts:
        y = baseline_y - ascent
        if not is_7seg:
            y -= raise_txt_px
        screen.blit(surf, (cx, y))
        cx += surf.get_width()
    return cx


def digit_top_y(parts, baseline_y):
    tops = []
    for surf, ascent, is_7seg in parts:
        if is_7seg:
            tops.append(baseline_y - ascent)
    return min(tops) if tops else None


def make_blank_slot(width, height):
    return pygame.Surface((width, height), pygame.SRCALPHA)


def strip_leading_zero_2digit(n: int) -> str:
    s = f"{n:02d}"
    return (" " + s[1]) if s[0] == "0" else s


def random_bright_color():
    while True:
        r = random.randint(40, 255)
        g = random.randint(40, 255)
        b = random.randint(40, 255)
        if (r + g + b) >= 240:
            return (r, g, b)


def load_ui_state():
    default = {
        "indoor_mode": "SHT20",
        "outdoor_mode": "SWITCHBOT",
        "time_mode_24h": False,
        "ui_color": [255, 255, 255],
        "theme": "default",
        "air_left_mode": "ECO2",
        "air_right_mode": "TVOC",
    }
    try:
        if not os.path.exists(STATE_PATH):
            return default
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        im = data.get("indoor_mode", default["indoor_mode"])
        om = data.get("outdoor_mode", default["outdoor_mode"])
        if om == "Internet":
            om = "OPEN_METEO"
        tm = bool(data.get("time_mode_24h", default["time_mode_24h"]))
        if im not in INDOOR_SOURCES:
            im = default["indoor_mode"]
        if om not in OUTDOOR_SOURCES:
            om = default["outdoor_mode"]
        c = data.get("ui_color", default["ui_color"])
        if (isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c)):
            cc = [int(max(0, min(255, int(x)))) for x in c]
        else:
            cc = default["ui_color"]
        theme = str(data.get("theme", default["theme"]) or default["theme"])
        air_left_mode = str(data.get("air_left_mode", default["air_left_mode"]))
        if air_left_mode not in ("ECO2", "PRESSURE"):
            air_left_mode = default["air_left_mode"]
        air_right_mode = str(data.get("air_right_mode", default["air_right_mode"]))
        if air_right_mode not in ("TVOC", "CO2"):
            air_right_mode = default["air_right_mode"]
        return {
            "indoor_mode": im,
            "outdoor_mode": om,
            "time_mode_24h": tm,
            "ui_color": cc,
            "theme": theme,
            "air_left_mode": air_left_mode,
            "air_right_mode": air_right_mode,
        }
    except Exception:
        return default


def save_ui_state(
    indoor_mode: str,
    outdoor_mode: str,
    time_mode_24h: bool,
    ui_color,
    theme: str = "default",
    air_left_mode: str = "ECO2",
    air_right_mode: str = "TVOC",
):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "indoor_mode": indoor_mode,
                    "outdoor_mode": outdoor_mode,
                    "time_mode_24h": bool(time_mode_24h),
                    "ui_color": list(ui_color) if ui_color is not None else [255, 255, 255],
                    "theme": str(theme or "default"),
                    "air_left_mode": air_left_mode if air_left_mode in ("ECO2", "PRESSURE") else "ECO2",
                    "air_right_mode": air_right_mode if air_right_mode in ("TVOC", "CO2") else "TVOC",
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def _is_fresh(ts, max_age_sec: float) -> bool:
    if not ts:
        return False
    return (time.time() - ts) <= max_age_sec


def indoor_source_valid(src: str, weather: dict, use_switchbot_in: bool, sht20_refresh_sec: int, last_sht20_ok_ts: float):
    if src == "SHT20":
        ts = weather.get("sht20_ts", last_sht20_ok_ts or 0.0)
        return _is_fresh(ts, max_age_sec=max(10.0, sht20_refresh_sec * 6.0))
    if src == "SWITCHBOT":
        if not use_switchbot_in:
            return False
        if weather.get("in_temp_c") is None or weather.get("in_hum_pct") is None:
            return False
        return _is_fresh(weather.get("in_ts"), max_age_sec=SWITCHBOT_REFRESH_SEC * 3.0) or (weather.get("in_err", "") == "")
    if src == "BME280":
        if weather.get("bme280_temp_c") is None or weather.get("bme280_hum_pct") is None:
            return False
        return _is_fresh(weather.get("bme280_ts"), max_age_sec=BME280_VALUE_STALE_SEC)
    return False


def outdoor_source_valid(src: str, weather: dict, use_switchbot: bool):
    if src == "SWITCHBOT":
        if not use_switchbot:
            return False
        if weather.get("out_temp_c") is None or weather.get("out_hum_pct") is None:
            return False
        return _is_fresh(weather.get("weather_ts"), max_age_sec=SWITCHBOT_REFRESH_SEC * 3.0) or (weather.get("weather_err", "") == "")
    if src == "OPEN_METEO":
        if weather.get("net_temp_c") is None or weather.get("net_hum_pct") is None:
            return False
        return _is_fresh(weather.get("net_ts"), max_age_sec=WEATHER_REFRESH_SEC * 3.0) or (weather.get("net_err", "") == "")
    return False


def next_valid_source(current: str, order: list[str], is_valid_fn):
    if current not in order:
        current = order[0]
    start = order.index(current)
    for step in range(1, len(order) + 1):
        cand = order[(start + step) % len(order)]
        if is_valid_fn(cand):
            return cand
    return current
