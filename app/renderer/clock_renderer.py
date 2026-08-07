# -*- coding: utf-8 -*-
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import os
import time
import threading
import datetime as _dt
import calendar as _cal
import pygame

# Optional holiday providers (best-effort)
try:
    import holidays  # type: ignore
except Exception:
    holidays = None
try:
    import jpholiday  # type: ignore
except Exception:
    jpholiday = None

from widgets.top_time_widget import TimeWidget
from widgets.bottom_info_widget import BottomInfoWidget
from renderer.theme_engine import get_theme_spec

_FONT_CACHE: dict[tuple[str, int], pygame.font.Font] = {}
FONT_7SEG_PATH = os.path.expanduser("~/deskclock/fonts/DSEG7Classic-Bold.ttf")
NIXIE_ONE_PATH = os.path.expanduser("~/deskclock/fonts/NixieOne-Resular.ttf")
NIXIE_FALLBACK_CANDIDATES = [
    NIXIE_ONE_PATH,
    os.path.expanduser("~/deskclock/fonts/NixieOne-Regular.ttf"),
    os.path.expanduser("~/deskclock/fonts/NixieOne.ttf"),
]
CUTIVE_MONO_PATH = os.path.expanduser("~/deskclock/fonts/CutiveMono-Regular.ttf")
CUTIVE_FALLBACK_CANDIDATES = [
    CUTIVE_MONO_PATH,
    "/usr/share/fonts/truetype/paratype/PTM55F.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Light.ttf",
    "/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
JP_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _pick_jp_font_path(preferred: str | None = None) -> str | None:
    if preferred and os.path.exists(preferred):
        return preferred
    for p in JP_FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None




def _pick_nixie_font_path() -> str | None:
    for p in NIXIE_FALLBACK_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def _pick_cutive_like_font_path() -> str | None:
    for p in CUTIVE_FALLBACK_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return _pick_jp_font_path()

def _load_font(path: str | None, size: int) -> pygame.font.Font:
    try:
        size = max(6, int(size))
    except Exception:
        size = 12
    key = (path or "", size)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    font = None
    if path and os.path.exists(path):
        try:
            font = pygame.font.Font(path, size)
        except Exception:
            font = None
    if font is None:
        font = pygame.font.Font(None, size)
    _FONT_CACHE[key] = font
    return font


@dataclass(frozen=True)
class TopLineCtx:
    font_ampm: pygame.font.Font
    font_7seg_main: pygame.font.Font
    font_7seg_sec: pygame.font.Font
    AMPM_SLOT_W: int
    GAP_AMPM: int
    DIGIT_W: int
    DIGIT_H: int
    font_main_size: int

    ampm: str
    hour_tens_char: str
    hour_ones_char: str
    colon_min: str
    ss: str

    WEATHER_ICON_ENABLE: bool
    WEATHER_ICON_SCALE: float
    WEATHER_ICON_MARGIN_Y: int
    WEATHER_ICON_STROKE: int
    WEATHER_ICON_RAISE_PX: int


@dataclass(frozen=True)
class BottomInfoCtx:
    info_font_path: str
    base_info_size: int
    TXT_SCALE_DATE_OUT: float
    TXT_RAISE_RATIO: float
    LABEL_RATIO: float
    LABEL_GAP_RATIO: float
    EXTRA_GAP_BETWEEN_LINES: float
    EXTRA_GAP_BETWEEN_WEATHER_LINES: float
    IN_LABEL_LEFT_CHARS: float
    IN_LABEL_DOWN_CHARS: float
    OUT_ROW_SHIFT_DIGITS: int
    OUT_VALUE_SHIFT_PX: int
    DAY_ROOMTEMP_GAP_PX: int
    WEEKDAY_SHIFT_PX: int
    UNIT_LABEL_PAD_PX: int
    WEEKDAY_ASCENT_ADJUST_PX: int
    OUTDOOR_ROW_SHIFT_DOWN_PX: int

    date_text: str
    date_weekday_char: str
    date_day_suffix: str
    m_field: str
    d_field: str
    in_text: str
    out_text: str

    indoor_mode: str = "SHT20"
    outdoor_mode: str = "SWITCHBOT"
    ens_fresh: bool = False

    in_temp: float | None = None
    in_hum: int | None = None
    out_temp: float | None = None
    out_hum: int | None = None

    ens_aqi: int | None = None
    ens_tvoc: int | None = None
    ens_eco2: int | None = None


@dataclass(frozen=True)
class RenderCtx:
    canvas: pygame.Surface
    w: int
    h: int
    UI_SCALE: float
    touch_rects_screen: dict
    render_color: Any
    top: TopLineCtx
    bottom: BottomInfoCtx
    weather: dict
    brightness_cur: float
    now: Any
    calendar_popup: bool = False
    calendar_anim: float = 0.0
    calendar_month_offset: int = 0
    theme: str = "classic"



def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    m = month - 1 + delta
    y = year + (m // 12)
    m2 = (m % 12) + 1
    return y, m2


def _jp_holiday_map_for_month(year: int, month: int) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        if holidays is not None:
            jp = holidays.country_holidays("JP", years=[year])  # type: ignore[attr-defined]
            for d, name in jp.items():
                if getattr(d, "year", None) == year and getattr(d, "month", None) == month:
                    out[int(d.day)] = str(name)
        if out:
            return out
        if jpholiday is not None:
            last = _cal.monthrange(year, month)[1]
            for day in range(1, last + 1):
                dt = _dt.date(year, month, day)
                name = jpholiday.is_holiday_name(dt)  # type: ignore[attr-defined]
                if name:
                    out[day] = str(name)
    except Exception:
        return out
    return out


def _clip_text_to_width(font: pygame.font.Font, text: str, max_w: int) -> str:
    if not text:
        return text
    if font.size(text)[0] <= max_w:
        return text
    ell = "…"
    t = text
    while t and font.size(t + ell)[0] > max_w:
        t = t[:-1]
    return (t + ell) if t else ""


class ClockRenderer:
    def __init__(self, *, screen: pygame.Surface, sw: int, sh: int) -> None:
        self.screen = screen
        self.sw = sw
        self.sh = sh
        self.time_widget = TimeWidget()
        self.bottom_widget = BottomInfoWidget()
        self._calendar_panel_cache: dict[tuple, tuple[pygame.Surface, dict[int, pygame.Rect]]] = {}
        self._holiday_month_cache: dict[tuple[int, int], dict[int, str]] = {}
        self._calendar_cache_plan_key: tuple | None = None
        self._calendar_prewarm_offsets: list[int] = []
        self._calendar_cache_lock = threading.Lock()
        self._dim_surface_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        self._cal_last_offset: int | None = None
        self._cal_slide_from_offset: int = 0
        self._cal_slide_to_offset: int = 0
        self._cal_slide_t0: float = 0.0
        self._cal_slide_active: bool = False
        self._cal_slide_dir: int = 0
        self._cal_slide_sec: float = 0.16

    def _calendar_base_months(self, now: _dt.datetime | _dt.date) -> tuple[int, int]:
        return int(getattr(now, "year")), int(getattr(now, "month"))

    def _schedule_calendar_cache_refresh(self, *, now: _dt.datetime | _dt.date, panel_size: tuple[int, int], info_font_path: str | None) -> None:
        base_y, base_m = self._calendar_base_months(now)
        plan_key = (base_y, base_m, int(panel_size[0]), int(panel_size[1]), info_font_path or "")
        if plan_key == self._calendar_cache_plan_key:
            return
        self._calendar_cache_plan_key = plan_key
        # offset range: base-3 .. base+4 so that month_offset +3 still has its right-side month ready
        self._calendar_prewarm_offsets = list(range(-3, 5))
        allowed = {(base_y, base_m)}
        for off in range(-3, 5):
            allowed.add(_month_add(base_y, base_m, off))
        # prune stale panel cache conservatively
        stale = []
        for k in self._calendar_panel_cache.keys():
            try:
                _, _, yy, mm, fp = k
                if (yy, mm) not in allowed or fp != (info_font_path or ""):
                    stale.append(k)
            except Exception:
                stale.append(k)
        for k in stale:
            self._calendar_panel_cache.pop(k, None)
        stale_h = [k for k in self._holiday_month_cache.keys() if k not in allowed]
        for k in stale_h:
            self._holiday_month_cache.pop(k, None)

    def warm_calendar_cache_step(self, *, now: _dt.datetime | _dt.date, w: int, h: int, info_font_path: str | None, budget_steps: int = 2) -> None:
        popup_w = int(w * 0.737)
        old_popup_h = int(h * 0.605)
        old_popup_y = int(h * 0.165)
        old_popup_bottom = old_popup_y + old_popup_h
        old_pad_top = int(old_popup_h * 0.015)
        old_pad_bottom = int(old_popup_h * 0.006)
        old_content_h = max(1, old_popup_h - old_pad_top - old_pad_bottom)
        new_popup_h = old_content_h + int(h * 0.045) + old_pad_bottom
        new_popup_y = max(12, old_popup_bottom - new_popup_h)
        content_top = max(0, new_popup_h - old_pad_bottom - old_content_h)
        pad_x = int(popup_w * 0.018)
        panel_gap = int((popup_w - pad_x * 2) * 0.040)
        panel_w = max(1, ((popup_w - pad_x * 2) - panel_gap) // 2)
        panel_h = max(1, old_content_h)
        self._schedule_calendar_cache_refresh(now=now, panel_size=(panel_w, panel_h), info_font_path=info_font_path)
        steps = 0
        while self._calendar_prewarm_offsets and steps < max(1, int(budget_steps)):
            off = self._calendar_prewarm_offsets.pop(0)
            yy, mm = _month_add(int(getattr(now, "year")), int(getattr(now, "month")), off)
            self._get_month_panel_cached(panel_size=(panel_w, panel_h), yy=yy, mm=mm, info_font_path=info_font_path)
            steps += 1

    def _get_holiday_map_cached(self, year: int, month: int) -> dict[int, str]:
        key = (year, month)
        cached = self._holiday_month_cache.get(key)
        if cached is not None:
            return cached
        out = _jp_holiday_map_for_month(year, month)
        self._holiday_month_cache[key] = out
        return out

    def _get_month_panel_cached(
        self,
        *,
        panel_size: tuple[int, int],
        yy: int,
        mm: int,
        info_font_path: str | None,
    ) -> tuple[pygame.Surface, dict[int, pygame.Rect]]:
        key = (panel_size[0], panel_size[1], yy, mm, info_font_path or "")
        cached = self._calendar_panel_cache.get(key)
        if cached is not None:
            return cached

        panel_w, panel_h = panel_size
        surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        COL_WHITE = (255, 255, 255)
        COL_RED = (255, 64, 64)
        COL_BLUE = (80, 150, 255)

        dseg_title = _load_font(FONT_7SEG_PATH, int(panel_h * 0.082))
        dseg_day = _load_font(FONT_7SEG_PATH, int(panel_h * 0.073))
        wd_font = _load_font(_pick_jp_font_path(info_font_path), int(panel_h * 0.037))
        wd_font.set_bold(False)
        hol_font = _load_font(_pick_jp_font_path(info_font_path), int(panel_h * 0.019))
        unit_font = _load_font(_pick_jp_font_path(info_font_path), max(10, int(panel_h * 0.046)))

        year_digits = dseg_title.render(f"{yy:04d}", True, COL_WHITE)
        month_digits = dseg_title.render(f"{mm}", True, COL_WHITE)
        year_unit = unit_font.render("年", True, COL_WHITE)
        month_unit = unit_font.render("月", True, COL_WHITE)
        title_gap = max(4, int(panel_w * 0.010))
        title_total_w = year_digits.get_width() + title_gap + year_unit.get_width() + title_gap * 2 + month_digits.get_width() + title_gap + month_unit.get_width()
        title_top_gap = int(panel_h * 0.050)
        title_y = title_top_gap
        title_x = (panel_w - title_total_w) // 2
        title_baseline = title_y + max(year_digits.get_height(), month_digits.get_height())
        surf.blit(year_digits, (title_x, title_baseline - year_digits.get_height()))
        x = title_x + year_digits.get_width() + title_gap
        surf.blit(year_unit, (x, title_baseline - year_unit.get_height()))
        x += year_unit.get_width() + title_gap * 2
        surf.blit(month_digits, (x, title_baseline - month_digits.get_height()))
        x += month_digits.get_width() + title_gap
        surf.blit(month_unit, (x, title_baseline - month_unit.get_height()))

        weekdays = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
        header_gap = int(panel_h * 0.010)
        header_y = title_baseline + header_gap
        cell_w = panel_w // 7
        header_pad_r = max(4, int(cell_w * 0.08))
        for i, wd in enumerate(weekdays):
            c = COL_WHITE
            if i == 0:
                c = COL_RED
            elif i == 6:
                c = COL_BLUE
            ws = wd_font.render(wd, True, c)
            x = (i + 1) * cell_w - header_pad_r - ws.get_width()
            surf.blit(ws, (x, header_y))

        grid_top = header_y + wd_font.get_height() + int(panel_h * 0.012)
        rows = 6
        grid_bottom = panel_h - int(panel_h * 0.028)
        cell_h = max(1, (grid_bottom - grid_top) // rows)

        hmap = self._get_holiday_map_cached(yy, mm)
        first_wd, last_day = _cal.monthrange(yy, mm)
        start_col = (first_wd + 1) % 7

        day = 1
        num_pad_r = max(6, int(cell_w * 0.12))
        num_top = int(cell_h * 0.02)
        day_boxes: dict[int, pygame.Rect] = {}

        for r in range(rows):
            y = grid_top + r * cell_h
            for c in range(7):
                x = c * cell_w
                idx = r * 7 + c
                if idx < start_col or day > last_day:
                    continue

                col = COL_WHITE
                if c == 0:
                    col = COL_RED
                elif c == 6:
                    col = COL_BLUE
                if day in hmap:
                    col = COL_RED

                ds = dseg_day.render(f"{day:2d}", True, col)
                dx = x + cell_w - num_pad_r - ds.get_width()
                dy = y + num_top
                surf.blit(ds, (dx, dy))
                day_boxes[day] = pygame.Rect(x, y, cell_w, cell_h)

                if day in hmap:
                    name = _clip_text_to_width(hol_font, hmap[day], cell_w - 10)
                    if name:
                        hs = hol_font.render(name, True, COL_WHITE)
                        draw_x = x + (cell_w - hs.get_width()) // 2
                        draw_y = min(y + cell_h - hs.get_height() - max(2, int(cell_h * 0.07)), dy + ds.get_height() + max(2, int(cell_h * 0.02)))
                        surf.blit(hs, (draw_x, draw_y))
                day += 1

        cached = (surf, day_boxes)
        self._calendar_panel_cache[key] = cached
        return cached

    def _draw_today_highlight(
        self,
        *,
        dst: pygame.Surface,
        panel_rect: pygame.Rect,
        day_box: pygame.Rect,
        alpha_fg: int,
    ) -> None:
        hi = pygame.Rect(
            panel_rect.left + day_box.left + max(2, int(day_box.width * 0.04)),
            panel_rect.top + day_box.top - 10,
            day_box.width - max(4, int(day_box.width * 0.08)),
            int(day_box.height * 0.78) + 18,
        )
        # Keep the day number fully visible: draw only a light outline,
        # and extend the box slightly downward per the requested layout.
        pygame.draw.rect(dst, (255, 255, 255, alpha_fg), hi, width=2, border_radius=10)

    def _blit_panel_pair(
        self,
        *,
        dst: pygame.Surface,
        content_rect: pygame.Rect,
        base_left_offset: int,
        yy: int,
        mm: int,
        info_font_path: str | None,
        today: _dt.date,
        alpha_fg: int,
    ) -> None:
        gap = int(content_rect.width * 0.060)
        panel_w = (content_rect.width - gap) // 2
        panel_h = content_rect.height
        left_panel = pygame.Rect(content_rect.left + base_left_offset, content_rect.top, panel_w, panel_h)
        right_panel = pygame.Rect(left_panel.right + gap, content_rect.top, panel_w, panel_h)

        for panel_rect, py, pm in [
            (left_panel, yy, mm),
            (right_panel, *_month_add(yy, mm, 1)),
        ]:
            if panel_rect.right < content_rect.left - panel_w or panel_rect.left > content_rect.right + panel_w:
                continue
            panel_surf, day_boxes = self._get_month_panel_cached(
                panel_size=(panel_w, panel_h),
                yy=py,
                mm=pm,
                info_font_path=info_font_path,
            )
            if alpha_fg < 255:
                s = panel_surf.copy()
                s.set_alpha(alpha_fg)
                dst.blit(s, panel_rect.topleft)
            else:
                dst.blit(panel_surf, panel_rect.topleft)
            if py == today.year and pm == today.month and today.day in day_boxes:
                self._draw_today_highlight(dst=dst, panel_rect=panel_rect, day_box=day_boxes[today.day], alpha_fg=alpha_fg)

    def _draw_calendar_overlay(self, *, canvas: pygame.Surface, w: int, h: int, ctx: RenderCtx) -> tuple[pygame.Rect | None, pygame.Rect | None]:
        now = ctx.now
        anim = max(0.0, min(1.0, float(getattr(ctx, "calendar_anim", 1.0))))
        if anim <= 0.0:
            self._cal_slide_active = False
            return None, None

        # backdrop fade (cached per size/alpha)
        dim_alpha = int(170 * anim)
        dim_key = (w, h, dim_alpha)
        dim = self._dim_surface_cache.get(dim_key)
        if dim is None:
            dim = pygame.Surface((w, h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, dim_alpha))
            self._dim_surface_cache[dim_key] = dim
            if len(self._dim_surface_cache) > 24:
                self._dim_surface_cache.clear()
                self._dim_surface_cache[dim_key] = dim
        canvas.blit(dim, (0, 0))

        popup_w = int(w * 0.737)
        old_popup_h = int(h * 0.605)
        popup_x = (w - popup_w) // 2
        old_popup_y = int(h * 0.165)
        old_popup_bottom = old_popup_y + old_popup_h
        old_pad_top = int(old_popup_h * 0.015)
        old_pad_bottom = int(old_popup_h * 0.006)
        old_content_h = max(1, old_popup_h - old_pad_top - old_pad_bottom)
        popup_h = old_content_h + int(h * 0.045) + old_pad_bottom
        popup_y = max(12, old_popup_bottom - popup_h)
        popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)

        popup = pygame.Surface((popup_rect.width, popup_rect.height), pygame.SRCALPHA)
        COL_WHITE = (255, 255, 255)
        COL_BG = (0, 0, 0)
        alpha_fg = max(0, min(255, int(255 * anim)))

        pygame.draw.rect(popup, (*COL_BG, alpha_fg), popup.get_rect(), border_radius=18)
        pygame.draw.rect(popup, (*COL_WHITE, alpha_fg), popup.get_rect(), width=2, border_radius=18)

        pad_x = int(popup_rect.width * 0.018)
        content_top = max(0, popup_h - old_pad_bottom - old_content_h) + max(2, int(h * 0.006))
        pad_bottom = old_pad_bottom
        inner = pygame.Rect(pad_x, 0, popup_rect.width - pad_x * 2, popup_rect.height - pad_bottom)

        panel_gap = int(inner.width * 0.040)
        panel_w = (inner.width - panel_gap) // 2
        panel_h = old_content_h
        arrow_font = _load_font(_pick_jp_font_path(ctx.bottom.info_font_path), int(panel_h * 0.070))
        prev_label = arrow_font.render("◀", True, COL_WHITE)
        next_label = arrow_font.render("▶", True, COL_WHITE)
        side_pad = max(4, int(popup_rect.width * 0.006))
        arrow_y = 2
        prev_rect = prev_label.get_rect(topleft=(side_pad, arrow_y))
        next_rect = next_label.get_rect(topright=(popup_rect.width - side_pad, arrow_y))

        month_offset = int(getattr(ctx, "calendar_month_offset", 0))
        show_prev = month_offset > -3
        show_next = month_offset < 3
        self._cal_last_offset = month_offset if getattr(ctx, "calendar_popup", False) else None
        self._cal_slide_active = False

        content = pygame.Rect(inner.left, content_top, inner.width, panel_h)
        today = _dt.date(int(getattr(now, "year")), int(getattr(now, "month")), int(getattr(now, "day")))

        # Draw calendar panels on a dedicated content layer and clip to the content area.
        # This prevents transient 7-seg fragments from appearing outside the intended area
        # while the month-slide animation is in progress.
        content_layer = pygame.Surface((content.width, content.height), pygame.SRCALPHA)
        content_layer.fill((0, 0, 0, 0))
        content_local = pygame.Rect(0, 0, content.width, content.height)

        y0, m0 = _month_add(int(getattr(now, "year")), int(getattr(now, "month")), month_offset)
        self._blit_panel_pair(dst=content_layer, content_rect=content_local, base_left_offset=0, yy=y0, mm=m0, info_font_path=ctx.bottom.info_font_path, today=today, alpha_fg=alpha_fg)

        popup.blit(content_layer, content.topleft)

        def _blit_with_alpha(dst: pygame.Surface, surf: pygame.Surface, pos: tuple[int, int]) -> None:
            if alpha_fg >= 255:
                dst.blit(surf, pos)
            else:
                s = surf.copy()
                s.set_alpha(alpha_fg)
                dst.blit(s, pos)

        if show_prev:
            _blit_with_alpha(popup, prev_label, prev_rect.topleft)
        if show_next:
            _blit_with_alpha(popup, next_label, next_rect.topleft)

        popup.set_alpha(alpha_fg)
        canvas.blit(popup, popup_rect.topleft)

        prev_canvas = pygame.Rect(popup_rect.left + prev_rect.left - 12, popup_rect.top + prev_rect.top - 8, prev_rect.width + 24, prev_rect.height + 16) if show_prev else None
        next_canvas = pygame.Rect(popup_rect.left + next_rect.left - 12, popup_rect.top + next_rect.top - 8, next_rect.width + 24, next_rect.height + 16) if show_next else None
        return prev_canvas, next_canvas

    def render_and_update_touch_rects(self, *, ctx: RenderCtx) -> None:
        canvas = ctx.canvas
        w = ctx.w
        h = ctx.h
        UI_SCALE = ctx.UI_SCALE
        touch_rects_screen = ctx.touch_rects_screen
        render_color = ctx.render_color
        weather = ctx.weather
        brightness_cur = ctx.brightness_cur
        now = ctx.now

        font_ampm = ctx.top.font_ampm
        font_7seg_main = ctx.top.font_7seg_main
        font_7seg_sec = ctx.top.font_7seg_sec
        AMPM_SLOT_W = ctx.top.AMPM_SLOT_W
        GAP_AMPM = ctx.top.GAP_AMPM
        DIGIT_W = ctx.top.DIGIT_W
        DIGIT_H = ctx.top.DIGIT_H
        font_main_size = ctx.top.font_main_size
        ampm = ctx.top.ampm
        hour_tens_char = ctx.top.hour_tens_char
        hour_ones_char = ctx.top.hour_ones_char
        colon_min = ctx.top.colon_min
        ss = ctx.top.ss
        WEATHER_ICON_ENABLE = ctx.top.WEATHER_ICON_ENABLE
        WEATHER_ICON_SCALE = ctx.top.WEATHER_ICON_SCALE
        WEATHER_ICON_MARGIN_Y = ctx.top.WEATHER_ICON_MARGIN_Y
        WEATHER_ICON_STROKE = ctx.top.WEATHER_ICON_STROKE
        WEATHER_ICON_RAISE_PX = ctx.top.WEATHER_ICON_RAISE_PX

        info_font_path = ctx.bottom.info_font_path
        base_info_size = ctx.bottom.base_info_size
        TXT_SCALE_DATE_OUT = ctx.bottom.TXT_SCALE_DATE_OUT
        TXT_RAISE_RATIO = ctx.bottom.TXT_RAISE_RATIO
        LABEL_RATIO = ctx.bottom.LABEL_RATIO
        LABEL_GAP_RATIO = ctx.bottom.LABEL_GAP_RATIO
        EXTRA_GAP_BETWEEN_LINES = ctx.bottom.EXTRA_GAP_BETWEEN_LINES
        EXTRA_GAP_BETWEEN_WEATHER_LINES = ctx.bottom.EXTRA_GAP_BETWEEN_WEATHER_LINES
        IN_LABEL_LEFT_CHARS = ctx.bottom.IN_LABEL_LEFT_CHARS
        IN_LABEL_DOWN_CHARS = ctx.bottom.IN_LABEL_DOWN_CHARS
        OUT_ROW_SHIFT_DIGITS = ctx.bottom.OUT_ROW_SHIFT_DIGITS
        OUT_VALUE_SHIFT_PX = ctx.bottom.OUT_VALUE_SHIFT_PX
        DAY_ROOMTEMP_GAP_PX = ctx.bottom.DAY_ROOMTEMP_GAP_PX
        WEEKDAY_SHIFT_PX = ctx.bottom.WEEKDAY_SHIFT_PX
        UNIT_LABEL_PAD_PX = ctx.bottom.UNIT_LABEL_PAD_PX
        WEEKDAY_ASCENT_ADJUST_PX = ctx.bottom.WEEKDAY_ASCENT_ADJUST_PX
        OUTDOOR_ROW_SHIFT_DOWN_PX = ctx.bottom.OUTDOOR_ROW_SHIFT_DOWN_PX

        date_text = ctx.bottom.date_text
        date_weekday_char = ctx.bottom.date_weekday_char
        date_day_suffix = ctx.bottom.date_day_suffix
        m_field = ctx.bottom.m_field
        d_field = ctx.bottom.d_field
        in_text = ctx.bottom.in_text
        out_text = ctx.bottom.out_text
        indoor_mode = getattr(ctx.bottom, "indoor_mode", "SHT20")
        outdoor_mode = getattr(ctx.bottom, "outdoor_mode", "SWITCHBOT")
        ens_fresh = getattr(ctx.bottom, "ens_fresh", False)
        in_temp = ctx.bottom.in_temp
        out_temp = ctx.bottom.out_temp
        ens_aqi = ctx.bottom.ens_aqi
        ens_tvoc = ctx.bottom.ens_tvoc
        ens_eco2 = ctx.bottom.ens_eco2

        sw, sh = self.sw, self.sh
        screen = self.screen

        theme_spec = get_theme_spec(getattr(ctx, "theme", "classic"))
        canvas.fill(theme_spec.bg_color)
        color = render_color

        top_font_main = font_7seg_main
        top_font_sec = font_7seg_sec
        top_font_ampm = font_ampm
        gap_ampm = GAP_AMPM
        digit_w = DIGIT_W
        digit_h = DIGIT_H
        value_font_path = FONT_7SEG_PATH
        if theme_spec.name == "nixie":
            time_font_path = _pick_nixie_font_path() or _pick_cutive_like_font_path() or info_font_path or _pick_jp_font_path()
            hm_size = max(8, int(round(font_main_size * 0.88)))
            sec_size = max(8, int(round(font_7seg_sec.get_height() * 1.20)))
            ampm_size = max(8, int(round(hm_size * 0.35)))
            top_font_main = _load_font(time_font_path, hm_size)
            top_font_sec = _load_font(time_font_path, sec_size)
            top_font_ampm = _load_font(info_font_path or _pick_jp_font_path(), ampm_size)
            digit_w = max(1, max(top_font_main.size(str(d))[0] for d in range(10)))
            digit_h = max(1, top_font_main.get_height())
            gap_ampm = GAP_AMPM
        elif not theme_spec.use_7seg_time:
            time_font_path = info_font_path or _pick_jp_font_path()
            top_font_main = _load_font(time_font_path, int(font_main_size * theme_spec.time_scale))
            top_font_sec = _load_font(time_font_path, max(8, int(font_main_size * theme_spec.time_scale * theme_spec.sec_scale)))
            top_font_ampm = _load_font(info_font_path or _pick_jp_font_path(), max(8, int(top_font_main.get_height() * 0.34 * theme_spec.ampm_scale)))
            digit_w = max(1, top_font_main.size("0")[0])
            digit_h = max(1, top_font_main.get_height())
            gap_ampm = int(digit_w * theme_spec.gap_ampm_ratio)
        if not theme_spec.use_7seg_info:
            value_font_path = info_font_path or _pick_jp_font_path()

        t_res = self.time_widget.render(
            canvas=canvas,
            w=w,
            h=h,
            color=color,
            font_ampm=top_font_ampm,
            font_7seg_main=top_font_main,
            font_7seg_sec=top_font_sec,
            AMPM_SLOT_W=max(top_font_ampm.size("午前")[0], top_font_ampm.size("午後")[0]),
            GAP_AMPM=gap_ampm,
            DIGIT_W=digit_w,
            DIGIT_H=digit_h,
            font_main_size=font_main_size,
            ampm=ampm,
            hour_tens_char=hour_tens_char,
            hour_ones_char=hour_ones_char,
            colon_min=colon_min,
            ss=ss,
            weather=weather,
            brightness_cur=brightness_cur,
            now=now,
            WEATHER_ICON_ENABLE=WEATHER_ICON_ENABLE,
            WEATHER_ICON_SCALE=WEATHER_ICON_SCALE,
            WEATHER_ICON_MARGIN_Y=WEATHER_ICON_MARGIN_Y,
            WEATHER_ICON_STROKE=WEATHER_ICON_STROKE,
            WEATHER_ICON_RAISE_PX=WEATHER_ICON_RAISE_PX,
            theme_name=theme_spec.name,
            theme_spec=theme_spec,
        )

        b_res = self.bottom_widget.render(
            canvas=canvas,
            color=color,
            top_width=t_res.top_width,
            time_rect_canvas=t_res.time_rect_canvas,
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
            now=now,
            date_text=date_text,
            date_weekday_char=date_weekday_char,
            date_day_suffix=date_day_suffix,
            m_field=m_field,
            d_field=d_field,
            in_text=in_text,
            out_text=out_text,
            in_temp=in_temp,
            out_temp=out_temp,
            indoor_mode=indoor_mode,
            outdoor_mode=outdoor_mode,
            ens_fresh=ens_fresh,
            ens_aqi=ens_aqi,
            ens_tvoc=ens_tvoc,
            ens_eco2=ens_eco2,
            value_font_path=value_font_path,
            air_bar_colors=theme_spec.air_bar_colors,
            air_bar_outline_color=theme_spec.air_bar_outline_color,
            theme_name=theme_spec.name,
            theme_spec=theme_spec,
        )

        indoor_rect_canvas = b_res.indoor_rect_canvas
        outdoor_rect_canvas = b_res.outdoor_rect_canvas
        date_rect_canvas = getattr(b_res, 'date_rect_canvas', None)
        time_rect_canvas = t_res.time_rect_canvas

        if abs(UI_SCALE - 1.0) < 1e-6:
            ox_now, oy_now, scale_now = 0, 0, 1.0
        else:
            zw = max(1, int(sw * UI_SCALE))
            zh = max(1, int(sh * UI_SCALE))
            ox_now = (sw - zw) // 2
            oy_now = (sh - zh) // 2
            scale_now = UI_SCALE

        def _canvas_rect_to_screen(r):
            return pygame.Rect(
                int(ox_now + r.left * scale_now),
                int(oy_now + r.top * scale_now),
                int(r.width * scale_now),
                int(r.height * scale_now),
            )

        touch_rects_screen["indoor"] = _canvas_rect_to_screen(indoor_rect_canvas)
        touch_rects_screen["outdoor"] = _canvas_rect_to_screen(outdoor_rect_canvas)
        touch_rects_screen["date"] = _canvas_rect_to_screen(date_rect_canvas) if isinstance(date_rect_canvas, pygame.Rect) else None
        touch_rects_screen["time"] = _canvas_rect_to_screen(time_rect_canvas)
        touch_rects_screen["weather"] = _canvas_rect_to_screen(t_res.weather_rect_canvas) if isinstance(getattr(t_res, "weather_rect_canvas", None), pygame.Rect) else None

        cal_prev_canvas = None
        cal_next_canvas = None
        if getattr(ctx, "calendar_popup", False) or float(getattr(ctx, "calendar_anim", 0.0)) > 0.0:
            cal_prev_canvas, cal_next_canvas = self._draw_calendar_overlay(canvas=canvas, w=w, h=h, ctx=ctx)

        touch_rects_screen["cal_prev"] = _canvas_rect_to_screen(cal_prev_canvas) if isinstance(cal_prev_canvas, pygame.Rect) else None
        touch_rects_screen["cal_next"] = _canvas_rect_to_screen(cal_next_canvas) if isinstance(cal_next_canvas, pygame.Rect) else None

        if abs(UI_SCALE - 1.0) < 1e-6:
            screen.blit(canvas, (0, 0))
        else:
            zw = max(1, int(sw * UI_SCALE))
            zh = max(1, int(sh * UI_SCALE))
            scaled = pygame.transform.smoothscale(canvas, (zw, zh))
            ox = (sw - zw) // 2
            oy = (sh - zh) // 2
            screen.fill((0, 0, 0))
            screen.blit(scaled, (ox, oy))

        pygame.display.flip()
