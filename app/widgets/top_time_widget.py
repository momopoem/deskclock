# -*- coding: utf-8 -*-
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from datetime import datetime
import pygame

def is_night_time(now) -> bool:
    """Return True if the given local datetime is considered night-time.

    This is used only for weather icon styling (sun/moon).
    v1 compatibility: simple hour-based rule (18:00-06:00).
    """
    try:
        h = int(getattr(now, 'hour', 0))
    except Exception:
        h = 0
    return (h >= 18) or (h < 6)

NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

import os

# -----------------------------------------------------------------------------
# Weather icon rendering (Weather Icons font + pseudo-color)
# -----------------------------------------------------------------------------
# v1.2.8 系（単一ソース）互換：
# - weathericons/weathericons-regular-webfont.ttf の glyph を使用
# - 天気種別ごとに擬似カラー（黄色/青/灰など）を適用（無効化も可能）

# If True, color is overridden per weather kind (pseudo-color).
WEATHER_ICON_USE_PSEUDO_COLOR = True

# Prefer Weather Icons TTF. If the font is missing, code falls back to line icons.
WEATHER_ICON_USE_TTF = True

# Weather Icons font path (relative to app root)
_THIS_DIR = os.path.dirname(__file__)
WEATHER_ICON_TTF_PATH = os.path.expanduser("~/deskclock/fonts/weathericons/weathericons-regular-webfont.ttf")

# Weather kind -> pseudo-color
WEATHER_KIND_COLOR = {
    "sun":       (255, 200, 0),
    "sun_cloud": (255, 200, 0),
    "cloud":     (200, 200, 200),
    "fog":       (180, 180, 180),
    "rain":      (80, 170, 255),
    "snow":      (210, 240, 255),
    "thunder":   (255, 220, 0),
    "unknown":   None,  # fallback to UI color
}

# Weather Icons (TTF) glyph mapping.
# NOTE: These codepoints match common "Weather Icons" distributions.
# If your glyphs differ, confirm via weathericons.css and adjust here.
WEATHER_KIND_GLYPH = {
    "sun":       "\uf00d",  # wi-day-sunny
    "sun_cloud": "\uf002",  # wi-day-cloudy
    "cloud":     "\uf013",  # wi-cloudy
    "fog":       "\uf014",  # wi-fog
    "rain":      "\uf019",  # wi-rain
    "snow":      "\uf01b",  # wi-snow
    "thunder":   "\uf01e",  # wi-thunderstorm
    "unknown":   "\uf07b",  # wi-na
}

# internal cache for pygame Font objects (size-dependent)
_WEATHER_ICON_FONT_CACHE: dict[tuple[str, int], pygame.font.Font] = {}


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x

def _apply_brightness(color, brightness: float):
    """Multiply RGB by brightness (0..1) with perceptual gamma correction."""
    b = _clamp01(brightness)
    # Gamma-correct so perceived fade is closer to linear.
    try:
        gamma = float(BRIGHTNESS_GAMMA)
    except Exception:
        gamma = 1.0
    if gamma > 0.0 and abs(gamma - 1.0) > 1e-6:
        b = b ** gamma
    r, g, bb = color
    return (int(r * b), int(g * b), int(bb * b))

def weather_code_to_icon(code):
    """Map Open-Meteo weather_code (WMO) to a small set of icon kinds."""
    if code is None:
        return "unknown"
    if code == 0:
        return "sun"
    if code in (1, 2):
        return "sun_cloud"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "rain"
    if 61 <= code <= 67:
        return "rain"
    if 71 <= code <= 77:
        return "snow"
    if 80 <= code <= 82:
        return "rain"
    if code in (95, 96, 99):
        return "thunder"
    return "unknown"

def draw_weather_icon_line(screen, rect, kind: str, color, stroke: int = 2):
    """Legacy: draw a simple line icon inside rect using pygame primitives."""
    if rect.width <= 0 or rect.height <= 0:
        return

    x, y, w, h = rect
    pad = 1
    x0, y0 = x + pad, y + pad
    x1, y1 = x + w - pad, y + h - pad
    ww = max(1, x1 - x0)
    hh = max(1, y1 - y0)
    cx = x0 + ww // 2
    cy = y0 + hh // 2

    def line(a, b):
        pygame.draw.line(screen, color, a, b, stroke)

    def circle(center, r):
        pygame.draw.circle(screen, color, center, r, stroke)

    # Size basis
    r = max(2, min(ww, hh) // 4)

    if kind == "sun":
        circle((cx, cy), r)
        ray = r + max(2, r // 2)
        for dx, dy in ((1,0),(0,1),(-1,0),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
            line((cx + (r+1)*dx, cy + (r+1)*dy), (cx + ray*dx, cy + ray*dy))
        return

    def cloud_base(base_y: int):
        c1 = (cx - r, base_y - r)
        c2 = (cx, base_y - r - max(1, r // 2))
        c3 = (cx + r, base_y - r)
        circle(c1, r)
        circle(c2, r)
        circle(c3, r)
        line((x0 + r, base_y), (x1 - r, base_y))

    if kind in ("cloud", "rain", "snow", "thunder", "fog", "sun_cloud"):
        base_y = cy + r

        if kind == "sun_cloud":
            # small sun behind cloud (top-left)
            sun_cx = cx - r
            sun_cy = cy - r
            sun_r = max(2, r - 1)
            circle((sun_cx, sun_cy), sun_r)
            ray = sun_r + max(2, sun_r // 2)
            for dx, dy in ((1,0),(0,1),(-1,0),(0,-1)):
                line((sun_cx + (sun_r+1)*dx, sun_cy + (sun_r+1)*dy), (sun_cx + ray*dx, sun_cy + ray*dy))

        cloud_base(base_y)

        if kind == "rain":
            for dx in (-r, 0, r):
                line((cx + dx, base_y + 2), (cx + dx - 2, min(y1, base_y + r + 6)))
            return

        if kind == "snow":
            sx = cx
            sy = min(y1 - 3, base_y + r + 2)
            l = max(3, r)
            line((sx - l, sy), (sx + l, sy))
            line((sx, sy - l), (sx, sy + l))
            line((sx - l, sy - l), (sx + l, sy + l))
            line((sx - l, sy + l), (sx + l, sy - l))
            return

        if kind == "thunder":
            pts = [(cx, base_y + 1), (cx - r // 2, base_y + r), (cx + r // 3, base_y + r), (cx - r // 3, min(y1, base_y + r * 2))]
            pygame.draw.lines(screen, color, False, pts, stroke)
            return

        if kind == "fog":
            yy = base_y + 2
            line((x0, yy), (x1, yy))
            line((x0 + 2, min(y1, yy + r)), (x1 - 2, min(y1, yy + r)))
            return

        # cloud only
        return

    # unknown
    circle((cx, cy - 1), r)
    line((cx, cy + r), (cx, min(y1, cy + r + 3)))

def draw_weather_icon(screen, rect, kind: str, color, stroke: int = 2, brightness: float = 1.0, is_night: bool = False):
    """Draw weather icon using Weather Icons TTF + pseudo-color (fallback to line icon)."""
    if rect.width <= 0 or rect.height <= 0:
        return

    # Decide base color (pseudo-color per kind, or UI color)
    icon_base = color
    if WEATHER_ICON_USE_PSEUDO_COLOR:
        c = WEATHER_KIND_COLOR.get(kind) if 'WEATHER_KIND_COLOR' in globals() else None
        if c:
            icon_base = c

    # Apply the same dimming policy as text to prevent burn-in.
    # - Night dimming disabled (time-based)
    # - Then dynamic brightness (PIR/BH1750)
    icon_color = _apply_brightness(icon_base, brightness)

    # Try TTF icon first
    if not WEATHER_ICON_USE_TTF:
        # Force line-icon renderer (preferred for this build)
        draw_weather_icon_line(screen, rect, kind, icon_color, stroke=stroke)
        return

    # Try TTF icon first
    try:
        ttf_path = WEATHER_ICON_TTF_PATH
        glyph = WEATHER_KIND_GLYPH.get(kind) or WEATHER_KIND_GLYPH.get("unknown")
        if ttf_path and os.path.exists(ttf_path) and glyph:
            # Size: almost fill rect height, but keep a tiny breathing room
            font_px = max(8, int(rect.height * 0.95))
            key = (ttf_path, font_px)
            f = _WEATHER_ICON_FONT_CACHE.get(key)
            if f is None:
                f = pygame.font.Font(ttf_path, font_px)
                _WEATHER_ICON_FONT_CACHE[key] = f

            surf = f.render(glyph, True, icon_color)
            x = rect.left + (rect.width - surf.get_width()) // 2
            y = rect.top + (rect.height - surf.get_height()) // 2
            screen.blit(surf, (x, y))
            return
    except Exception:
        # Fall back below
        pass

    # Fallback: the legacy line icon so the clock never "loses" the icon.
    draw_weather_icon_line(screen, rect, kind, icon_color, stroke=stroke)

# 7セグ扱い（桁揃え安定のためスペースも7セグ扱い）



# -----------------------------------------------------------------------------
# Internet reachability
# -----------------------------------------------------------------------------

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

def load_ui_state():
    """Load persisted UI toggles. Returns defaults if missing/corrupt."""
    default = {
        "indoor_mode": "SHT20",
        "outdoor_mode": "SWITCHBOT",
        "time_mode_24h": False,
        "ui_color": [255, 255, 255],
    }
    try:
        if not os.path.exists(STATE_PATH):
            return default
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        # sanitize
        im = data.get("indoor_mode", default["indoor_mode"])
        om = data.get("outdoor_mode", default["outdoor_mode"])
        tm = bool(data.get("time_mode_24h", default["time_mode_24h"]))
        if im not in INDOOR_SOURCES:
            im = default["indoor_mode"]
        if om not in OUTDOOR_SOURCES:
            om = default["outdoor_mode"]
        # ui_color
        c = data.get("ui_color", default["ui_color"])
        if (isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c)):
            cc = [int(max(0, min(255, int(x)))) for x in c]
        else:
            cc = default["ui_color"]
        return {"indoor_mode": im, "outdoor_mode": om, "time_mode_24h": tm, "ui_color": cc}
    except Exception:
        return default

def save_ui_state(indoor_mode: str, outdoor_mode: str, time_mode_24h: bool, ui_color):
    """Atomically save UI toggles."""
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
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp, STATE_PATH)
    except Exception:
        # persistence must never crash the clock
        pass



# -----------------------------------------------------------------------------
# Source selection
# -----------------------------------------------------------------------------

def _is_fresh(ts, max_age_sec: float) -> bool:
    if not ts:
        return False
    return (time.time() - ts) <= max_age_sec

def indoor_source_valid(src: str, weather: dict, use_switchbot_in: bool, sht20_refresh_sec: int, last_sht20_ok_ts: float):
    if src == "SHT20":
        ts = weather.get("sht20_ts", last_sht20_ok_ts or 0.0)
        return _is_fresh(ts, max_age_sec=max(10.0, sht20_refresh_sec * 6.0))
    if src == "AHT21":
        ts = weather.get("aht21_ts", 0.0)
        # Similar freshness policy to SHT20: allow a few intervals of slack
        return _is_fresh(ts, max_age_sec=max(10.0, AHT21_REFRESH_SEC * 6.0))
    if src == "SWITCHBOT":
        if not use_switchbot_in:
            return False
        if weather.get("in_temp_c") is None or weather.get("in_hum_pct") is None:
            return False
        return _is_fresh(weather.get("in_ts"), max_age_sec=SWITCHBOT_REFRESH_SEC * 3.0) or (weather.get("in_err", "") == "")
    return False

def outdoor_source_valid(src: str, weather: dict, use_switchbot: bool):
    if src == "SWITCHBOT":
        if not use_switchbot:
            return False
        if weather.get("out_temp_c") is None or weather.get("out_hum_pct") is None:
            return False
        return _is_fresh(weather.get("weather_ts"), max_age_sec=SWITCHBOT_REFRESH_SEC * 3.0) or (weather.get("weather_err", "") == "")
    if src == "Internet":
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


# -------------------------
# Main entrypoint
# -------------------------



# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Phase 3 (v2 skeleton): ThreadScheduler
#   - Centralizes background worker thread startup
#   - Does NOT change worker loop logic (full behavioral compatibility)
# -----------------------------------------------------------------------------

@dataclass
class ScheduledThread:
    name: str
    target: Callable
    args: tuple
    thread: threading.Thread | None = None


class ThreadScheduler:
    """Minimal scheduler/manager for background worker threads (Phase 3 skeleton).

    We keep existing `fetch_*_loop` functions intact (they already implement sleep + stop_event).
    This class just centralizes startup and provides a single place for future restart policies.
    """

    def __init__(self, *, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self._threads: list[ScheduledThread] = []

    def add(self, name: str, target: Callable, *args) -> None:
        self._threads.append(ScheduledThread(name=name, target=target, args=args))

    def start_all(self) -> None:
        for st in self._threads:
            if st.thread and st.thread.is_alive():
                continue
            t = threading.Thread(target=st.target, args=st.args, daemon=True, name=st.name)
            st.thread = t
            t.start()

    def list_alive(self) -> list[str]:
        return [st.name for st in self._threads if st.thread and st.thread.is_alive()]



# -----------------------------------------------------------------------------
# Phase 4 (v2 skeleton): Renderer split (UI split)
#   - Keep rendering behavior identical
#   - Move frame rendering (including touch-rect calc and flip) into Renderer
# -----------------------------------------------------------------------------


def _inflate_rect(rect: pygame.Rect, dx: int, dy: int) -> pygame.Rect:
    return pygame.Rect(rect.left - dx, rect.top - dy, rect.width + dx * 2, rect.height + dy * 2)


@dataclass(frozen=True)

class TimeWidgetResult:
    top_width: int
    time_rect_canvas: pygame.Rect
    weather_rect_canvas: pygame.Rect | None = None



def make_blank_slot(width, height):
    return pygame.Surface((width, height), pygame.SRCALPHA)

def _make_lcd_shadow_color(color):
    try:
        r, g, b = [int(v) for v in color[:3]]
    except Exception:
        r, g, b = (24, 41, 74)
    return (max(0, min(255, int(r * 0.55))), max(0, min(255, int(g * 0.55))), max(0, min(255, int(b * 0.55))))

def _make_lcd_ghost_color(bg_color, fg_color):
    try:
        br, bg, bb = [int(v) for v in bg_color[:3]]
        fr, fg, fb = [int(v) for v in fg_color[:3]]
    except Exception:
        br, bg, bb = (186, 205, 176)
        fr, fg, fb = (24, 41, 74)
    mix = (
        int(br + (fr - br) * 0.22),
        int(bg + (fg - bg) * 0.22),
        int(bb + (fb - bb) * 0.22),
    )
    return (*mix, 88)

def _render_lcd_ghost(font: pygame.font.Font, text: str, bg_color, fg_color) -> pygame.Surface:
    ghost = _make_lcd_ghost_color(bg_color, fg_color)
    surf = font.render(text, True, ghost[:3])
    out = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    out.blit(surf, (0, 0))
    try:
        out.set_alpha(ghost[3])
    except Exception:
        pass
    return out


def _draw_lcd_icon_with_shadow(screen, rect, kind: str, main_color, brightness: float, now, stroke: int = 2):
    shadow = _make_lcd_shadow_color(main_color)
    shadow_rect = pygame.Rect(rect.left + 2, rect.top + 2, rect.width, rect.height)
    draw_weather_icon(screen, shadow_rect, kind, shadow, stroke=stroke, brightness=brightness, is_night=is_night_time(now))
    draw_weather_icon(screen, rect, kind, main_color, stroke=stroke, brightness=brightness, is_night=is_night_time(now))

class TimeWidget:
    """Top line widget: AM/PM + HH:MM + SS + optional weather icon."""

    def render(
        self,
        *,
        canvas: pygame.Surface,
        w: int,
        h: int,
        color,
        font_ampm: pygame.font.Font,
        font_7seg_main: pygame.font.Font,
        font_7seg_sec: pygame.font.Font,
        AMPM_SLOT_W: int,
        GAP_AMPM: int,
        DIGIT_W: int,
        DIGIT_H: int,
        font_main_size: int,
        ampm: str,
        hour_tens_char: str,
        hour_ones_char: str,
        colon_min: str,
        ss: str,
        weather: dict,
        brightness_cur: float,
        now,
        WEATHER_ICON_ENABLE: bool,
        WEATHER_ICON_SCALE: float,
        WEATHER_ICON_MARGIN_Y: int,
        WEATHER_ICON_STROKE: int,
        WEATHER_ICON_RAISE_PX: int,
        theme_name: str = "default",
        theme_spec=None,
    ) -> TimeWidgetResult:
        lcd_mode = (theme_name == "lcd")
        lcd_bg = getattr(theme_spec, "bg_color", (186, 205, 176)) if theme_spec is not None else (186, 205, 176)
        surf_ampm = font_ampm.render(ampm, True, color) if ampm else make_blank_slot(AMPM_SLOT_W, font_ampm.get_height())

        if hour_tens_char:
            surf_h_tens = font_7seg_main.render(hour_tens_char, True, color)
        else:
            surf_h_tens = make_blank_slot(DIGIT_W, DIGIT_H)

        surf_h_ones = font_7seg_main.render(hour_ones_char, True, color)
        surf_colon_min = font_7seg_main.render(colon_min, True, color)
        surf_sec = font_7seg_sec.render(ss, True, color)

        time_w = surf_h_tens.get_width() + surf_h_ones.get_width() + surf_colon_min.get_width()
        top_width = surf_ampm.get_width() + GAP_AMPM + time_w + surf_sec.get_width()

        x_top = (w - top_width) // 2

        main_h = max(surf_h_tens.get_height(), surf_h_ones.get_height(), surf_colon_min.get_height())
        # This is the anchor for the complete normal display: the bottom rows
        # are positioned from time_rect_canvas.  Move the shared anchor slightly
        # upward so the visible content has balanced top/bottom margins.
        y_top = (h - main_h) // 2 - int(font_main_size * 0.43)

        y_ampm = y_top + main_h - surf_ampm.get_height()
        if lcd_mode and ampm:
            sh = _make_lcd_shadow_color(color)
            canvas.blit(font_ampm.render(ampm, True, sh), (x_top + 2, y_ampm + 2))
        canvas.blit(surf_ampm, (x_top, y_ampm))
        x_cur = x_top + surf_ampm.get_width() + GAP_AMPM

        if lcd_mode:
            ghost_h_tens = "1" if ampm else "8"
            ghost_main = _render_lcd_ghost(font_7seg_main, f"{ghost_h_tens}8:88", lcd_bg, color)
            canvas.blit(ghost_main, (x_cur, y_top))
        canvas.blit(surf_h_tens, (x_cur, y_top))
        x_cur += surf_h_tens.get_width()
        canvas.blit(surf_h_ones, (x_cur, y_top))
        x_cur += surf_h_ones.get_width()
        canvas.blit(surf_colon_min, (x_cur, y_top))

        x_sec = x_top + surf_ampm.get_width() + GAP_AMPM + time_w
        y_sec = y_top + main_h - surf_sec.get_height()
        if lcd_mode:
            ghost_sec = _render_lcd_ghost(font_7seg_sec, "88", lcd_bg, color)
            canvas.blit(ghost_sec, (x_sec, y_sec))
        canvas.blit(surf_sec, (x_sec, y_sec))

        weather_rect_canvas = None
        if WEATHER_ICON_ENABLE:
            wcode = weather.get("weather_code", None)
            kind = weather_code_to_icon(wcode)
            if kind != "unknown":
                base_h = max(8, int(surf_sec.get_height() * 0.60))
                icon_h = int(base_h * WEATHER_ICON_SCALE)
                avail_h = max(6, (y_sec - y_top) - WEATHER_ICON_MARGIN_Y)
                icon_h = min(icon_h, avail_h)
                icon_rect = pygame.Rect(x_sec, y_top - WEATHER_ICON_RAISE_PX, surf_sec.get_width(), icon_h)
                if lcd_mode:
                    _draw_lcd_icon_with_shadow(canvas, icon_rect, kind, color, brightness_cur, now, stroke=WEATHER_ICON_STROKE)
                else:
                    draw_weather_icon(canvas, icon_rect, kind, color, WEATHER_ICON_STROKE, brightness=brightness_cur, is_night=is_night_time(now))
                weather_rect_canvas = icon_rect.copy()

        time_hour_w = AMPM_SLOT_W + GAP_AMPM + (surf_h_tens.get_width() + surf_h_ones.get_width())
        time_rect_canvas = pygame.Rect(x_top, y_top, time_hour_w, main_h)

        return TimeWidgetResult(top_width=int(top_width), time_rect_canvas=time_rect_canvas, weather_rect_canvas=weather_rect_canvas)

