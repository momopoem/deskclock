# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import pygame
import requests

from config import (
    LAT,
    LON,
    OPEN_METEO_BASE_URL,
    SWITCHBOT_REFRESH_SEC,
    TIMEZONE,
    WEATHER_ICON_TTF_PATH,
    WEATHER_ICON_USE_PSEUDO_COLOR,
    WEATHER_KIND_COLOR,
    WEATHER_KIND_GLYPH,
    WEATHER_REFRESH_SEC,
)

_WEATHER_ICON_FONT_CACHE = {}
OPEN_METEO_USER_AGENT = "DeskSideClock/2.3.2 (+https://github.com/momopoem/deskclock)"


def _open_meteo_url(query: str) -> str:
    """Build an Open-Meteo URL; paid/self-hosted endpoints can be configured."""
    return f"{OPEN_METEO_BASE_URL}?{query.lstrip('?')}"


def _http_get_json(session: requests.Session, url: str, *, headers=None, timeout=8):
    """HTTP GET -> JSON with guaranteed response close (prevents CLOSE_WAIT/FD leaks)."""
    r = session.get(url, headers=headers, timeout=timeout)
    try:
        r.raise_for_status()
        return r.json()
    finally:
        try:
            r.close()
        except Exception:
            pass

def make_switchbot_headers(token: str, secret: str):
    ts = str(int(time.time() * 1000))
    nonce = ""
    string_to_sign = f"{token}{ts}{nonce}"
    sign = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return {
        "Authorization": token,
        "t": ts,
        "nonce": nonce,
        "sign": sign,
        "Content-Type": "application/json",
    }




# =========================
# SwitchBot device commands (Light ON/OFF)

def fetch_switchbot_outdoor(shared, stop_event):
    token = os.environ.get("SWITCHBOT_TOKEN")
    secret = os.environ.get("SWITCHBOT_SECRET")
    device_id = os.environ.get("SWITCHBOT_outDeviceId") or os.environ.get("SWITCHBOT_deviceId")

    if not token or not secret or not device_id:
        shared["weather_err"] = "SwitchBot env vars missing (SWITCHBOT_TOKEN/SECRET/outDeviceId)"
        return

    url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"

    # Use a Session for connection reuse; always close responses to avoid CLOSE_WAIT.
    with requests.Session() as s:
        while not stop_event.is_set():
            try:
                headers = make_switchbot_headers(token, secret)
                j = _http_get_json(s, url, headers=headers, timeout=8)

                body = (j or {}).get("body", {})
                temp = body.get("temperature")
                hum = body.get("humidity")

                if temp is None or hum is None:
                    shared["weather_err"] = f"Invalid SwitchBot payload: {body}"
                else:
                    shared["out_temp_c"] = float(temp)
                    shared["out_hum_pct"] = int(round(hum))
                    shared["weather_err"] = ""
                    shared["weather_ts"] = time.time()
            except Exception as e:
                shared["weather_err"] = f"SwitchBot: {type(e).__name__}: {e}"

            stop_event.wait(SWITCHBOT_REFRESH_SEC)

def fetch_switchbot_indoor(shared, stop_event):
    """Fetch indoor temperature/humidity from SwitchBot Cloud API.

    Env:
      - SWITCHBOT_TOKEN
      - SWITCHBOT_SECRET
      - SWITCHBOT_inDeviceId  (new)
        (optional backward-compat: SWITCHBOT_inDeviceID / SWITCHBOT_inDeviceId are treated the same)
    """
    token = os.environ.get("SWITCHBOT_TOKEN")
    secret = os.environ.get("SWITCHBOT_SECRET")
    device_id = (
        os.environ.get("SWITCHBOT_inDeviceId")
        or os.environ.get("SWITCHBOT_inDeviceID")
        or os.environ.get("SWITCHBOT_inDeviceid")
    )

    if not token or not secret or not device_id:
        # keep placeholders if missing; do not overwrite outdoor error
        shared["in_err"] = "SwitchBot env vars missing (SWITCHBOT_TOKEN/SECRET/inDeviceId)"
        return

    url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"

    with requests.Session() as s:
        while not stop_event.is_set():
            try:
                headers = make_switchbot_headers(token, secret)
                j = _http_get_json(s, url, headers=headers, timeout=8)

                body = (j or {}).get("body", {})
                temp = body.get("temperature")
                hum = body.get("humidity")

                if temp is None or hum is None:
                    shared["in_err"] = f"Invalid SwitchBot payload: {body}"
                else:
                    shared["in_temp_c"] = float(temp)
                    shared["in_hum_pct"] = int(round(hum))
                    shared["in_source"] = "SWITCHBOT"
                    shared["in_err"] = ""
                    shared["in_ts"] = time.time()
            except Exception as e:
                shared["in_err"] = f"SwitchBot(in): {type(e).__name__}: {e}"

            stop_event.wait(SWITCHBOT_REFRESH_SEC)



# -----------------------------------------------------------------------------
# Weather (Open-Meteo etc.)
# -----------------------------------------------------------------------------

def fetch_weather_loop(shared, stop_event):
    url = _open_meteo_url(
        f"latitude={LAT}&longitude={LON}"
        f"&timezone={TIMEZONE}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
    )
    headers = {"User-Agent": OPEN_METEO_USER_AGENT}

    with requests.Session() as s:
        while not stop_event.is_set():
            try:
                j = _http_get_json(s, url, headers=headers, timeout=8)
                cur = (j or {}).get("current", {})
                shared["out_temp_c"] = float(cur["temperature_2m"])
                shared["out_hum_pct"] = int(round(cur["relative_humidity_2m"]))
                # weather_code is used for simple icon above seconds
                shared["weather_code"] = int(cur.get("weather_code")) if cur.get("weather_code") is not None else None
                shared["weather_err"] = ""
                shared["weather_ts"] = time.time()
            except Exception as e:
                shared["weather_err"] = f"{type(e).__name__}: {e}"

            stop_event.wait(WEATHER_REFRESH_SEC)



def fetch_internet_loop(shared, stop_event):
    """Fetch Open-Meteo temperature/humidity and optionally weather_code.

    Used as a selectable source for indoor/outdoor values. Writes to:
      - net_temp_c
      - net_hum_pct
      - net_weather_code
      - net_ts
      - net_err
    """
    url = _open_meteo_url(
        f"latitude={LAT}&longitude={LON}"
        f"&timezone={TIMEZONE}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
    )
    headers = {"User-Agent": OPEN_METEO_USER_AGENT}

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

def fetch_weathercode_only_loop(shared, stop_event, refresh_sec: int):
    """Fetch only weather_code from Open-Meteo.
    Used when outdoor temp/hum are sourced from SwitchBot, but we still want a simple weather icon.
    Refresh timing is aligned to outdoor refresh.

    Resource-safety: ensure responses are closed to avoid FD leaks.
    """
    url = _open_meteo_url(
        f"latitude={LAT}&longitude={LON}"
        f"&timezone={TIMEZONE}"
        "&current=weather_code"
    )
    headers = {"User-Agent": OPEN_METEO_USER_AGENT}

    with requests.Session() as s:
        while not stop_event.is_set():
            try:
                j = _http_get_json(s, url, headers=headers, timeout=8)
                cur = (j or {}).get("current", {})
                shared["weather_code"] = int(cur.get("weather_code")) if cur.get("weather_code") is not None else None
            except Exception:
                # If the icon fetch fails, keep last known value (do not set weather_err here).
                pass

            stop_event.wait(refresh_sec)

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
        c = WEATHER_KIND_COLOR.get(kind)
        if c:
            icon_base = c

    # Apply the same dimming policy as text to prevent burn-in.
    # - Night dimming disabled (time-based)
    # - Then dynamic brightness (PIR/BH1750)
    icon_color = _apply_brightness(icon_base, brightness)

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

