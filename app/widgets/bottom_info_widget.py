# -*- coding: utf-8 -*-
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pygame

import os

_FONT_CACHE = {}
FONT_7SEG_PATH = os.path.expanduser("~/deskclock/fonts/DSEG7Classic-Bold.ttf")

@dataclass(frozen=True)
class BottomInfoWidgetResult:
    indoor_rect_canvas: pygame.Rect
    outdoor_rect_canvas: pygame.Rect
    date_rect_canvas: pygame.Rect
    air_left_rect_canvas: pygame.Rect | None = None
    air_right_rect_canvas: pygame.Rect | None = None

def load_font(path, size):
    """Load a TTF font with caching. Falls back to pygame's default font."""
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
        # Use default font (avoids SysFont repeatedly opening freesansbold.ttf)
        font = pygame.font.Font(None, size)

    _FONT_CACHE[key] = font
    return font
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

def _lcd_ghost_surface(font, text, bg_color, fg_color):
    surf = font.render(text, True, _make_lcd_ghost_color(bg_color, fg_color)[:3])
    out = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    out.blit(surf, (0, 0))
    out.set_alpha(_make_lcd_ghost_color(bg_color, fg_color)[3])
    return out

def _to_lcd_ghost_text(s: str) -> str:
    out = []
    for ch in s:
        if ch.isdigit():
            out.append('8')
        elif ch in '.:-':
            out.append(ch)
        elif ch == ' ':
            out.append(' ')
        else:
            out.append(ch)
    return ''.join(out)

def is_7seg_char(ch: str) -> bool:
    return ch.isdigit() or ch in " -.:"

def render_run(font_7seg, font_txt, s, color, digit_w_7seg=None):
    parts = []
    buf = ""
    mode_is_7 = None

    def flush():
        nonlocal buf, mode_is_7
        if not buf:
            return

        # 7セグ部分は「スペースの幅」が数字幅より狭いと小数点位置がズレるため、
        # digit_w_7seg が与えられた場合はスペースを「数字1桁ぶんの空き」に置き換える。
        if mode_is_7 and (digit_w_7seg is not None):
            ascent = font_7seg.get_ascent()
            h = font_7seg.get_height()

            run = ""
            for ch in buf:
                if ch == " ":
                    if run:
                        surf_run = font_7seg.render(run, True, color)
                        parts.append((surf_run, ascent, True, run, font_7seg))
                        run = ""
                    parts.append((make_blank_slot(digit_w_7seg, h), ascent, True, ' ', font_7seg))
                else:
                    run += ch
            if run:
                surf_run = font_7seg.render(run, True, color)
                parts.append((surf_run, ascent, True, run, font_7seg))
        else:
            f = font_7seg if mode_is_7 else font_txt
            surf = f.render(buf, True, color)
            parts.append((surf, f.get_ascent(), mode_is_7, buf, f))

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
    return sum(s.get_width() for s, *_ in parts)
def blit_hstack_baseline(screen, parts, x, baseline_y, raise_txt_px, *, lcd_mode=False, lcd_bg_color=(186, 205, 176), main_color=(24, 41, 74)):
    cx = x
    shadow_color = _make_lcd_shadow_color(main_color)
    for surf, ascent, is_7seg, raw_text, font_used in parts:
        y = baseline_y - ascent
        if not is_7seg:
            y -= raise_txt_px
        if lcd_mode:
            if is_7seg and raw_text and raw_text.strip():
                ghost_text = _to_lcd_ghost_text(raw_text)
                if ghost_text.strip():
                    ghost = _lcd_ghost_surface(font_used, ghost_text, lcd_bg_color, main_color)
                    screen.blit(ghost, (cx, y))
            elif (not is_7seg) and raw_text and raw_text.strip():
                shadow = font_used.render(raw_text, True, shadow_color)
                screen.blit(shadow, (cx + 2, y + 2))
        screen.blit(surf, (cx, y))
        cx += surf.get_width()
    return cx


def blit_text_with_lcd_shadow(screen, font, text, color, x, y, *, lcd_mode=False):
    surf = font.render(text, True, color)
    if lcd_mode and text and text.strip():
        shadow = font.render(text, True, _make_lcd_shadow_color(color))
        screen.blit(shadow, (x + 2, y + 2))
    screen.blit(surf, (x, y))
    return surf


def blit_lcd_ghost_only(screen, parts, x, baseline_y, raise_txt_px, *, lcd_bg_color=(186, 205, 176), main_color=(24, 41, 74)):
    cx = x
    for surf, ascent, is_7seg, raw_text, font_used in parts:
        y = baseline_y - ascent
        if not is_7seg:
            y -= raise_txt_px
        if raw_text and raw_text.strip():
            ghost_text = _to_lcd_ghost_text(raw_text)
            if ghost_text.strip():
                ghost = _lcd_ghost_surface(font_used, ghost_text, lcd_bg_color, main_color)
                screen.blit(ghost, (cx, y))
        cx += surf.get_width()
def digit_top_y(parts, baseline_y):
    tops = []
    for surf, ascent, is_7seg, raw_text, font_used in parts:
        if is_7seg:
            tops.append(baseline_y - ascent)
    return min(tops) if tops else None
def fmt_temp_field(temp):
    # 温度は必ず「幅5」で右寄せ → 小数点位置が行間で固定
    if temp is None:
        return " --.-"
    return f"{temp:5.1f}"


def _measure_7seg_width(font_7seg, s: str, digit_w: int) -> int:
    """Measure width of a string as rendered by render_run() for 7-seg runs.
    - Digits/punct are measured via the font.
    - Spaces are treated as a full digit slot (digit_w) to keep decimal positions stable.
    """
    w = 0
    for ch in s:
        if ch == " ":
            w += int(digit_w)
        else:
            try:
                w += int(font_7seg.size(ch)[0])
            except Exception:
                w += 0
    return int(w)

def _dot_x_from_temp_field(start_x: int, temp_field: str, font_7seg, digit_w: int) -> int | None:
    """Return absolute X coordinate of '.' within a fixed-width temperature field (e.g. ' --.-' / ' 12.3').
    If '.' is missing, returns None.
    """
    if not temp_field:
        return None
    i = temp_field.find(".")
    if i < 0:
        return None
    prefix = temp_field[:i]  # up to, but not including '.'
    return int(start_x + _measure_7seg_width(font_7seg, prefix, digit_w))



# -----------------------------------------------------------------------------
# Drawing primitives
# -----------------------------------------------------------------------------




# Air quality bar (5-level) + ENS160 value block layout helpers
AIR_BAR_HEIGHT_PX = 30  # 1.5x of 20px
AIR_BAR_SEGMENTS = 5
# Gap above and below the air-quality bar.
# NOTE: This is *spacing between rows*, so the date/indoor line is pushed DOWN
# by (AIR_BAR_PAD_Y*2 + AIR_BAR_HEIGHT_PX). Do not treat this as an internal
# padding that changes centering.
AIR_BAR_PAD_Y = 20
# Visual tweak: integer rounding tends to bias "center" slightly upward.
# A small positive bias moves the bar a few pixels downward for optical centering.
AIR_BAR_CENTER_BIAS_PX = 3
# Colors: Blue, Green, Yellow, Orange, Red
AIR_BAR_COLORS = (
    (0, 120, 255),
    (0, 200, 0),
    (255, 220, 0),
    (255, 140, 0),
    (255, 0, 0),
)

def _mul_rgb(c, m: float):
    try:
        r, g, b = c
        return (max(0, min(255, int(r * m))), max(0, min(255, int(g * m))), max(0, min(255, int(b * m))))
    except Exception:
        return c

def _brightness_from_ui_color(ui_color) -> float:
    # ui_color is already brightness-dimmed for text (typically white scaled).
    # Derive a 0..1 factor so fixed palette colors dim consistently.
    try:
        if not isinstance(ui_color, (tuple, list)) or len(ui_color) < 3:
            return 1.0
        return max(0.10, min(1.0, float(max(ui_color[0], ui_color[1], ui_color[2])) / 255.0))
    except Exception:
        return 1.0


class BottomInfoWidget:
    """Bottom area widget: date + indoor/outdoor + optional ENS160 block."""

    def render(
        self,
        *,
        canvas: pygame.Surface,
        color,
        top_width: int,
        time_rect_canvas: pygame.Rect,  # (added) TimeWidget rect in canvas coords
        info_font_path: str,
        base_info_size: int,
        TXT_SCALE_DATE_OUT: float,
        TXT_RAISE_RATIO: float,
        LABEL_RATIO: float,
        LABEL_GAP_RATIO: float,
        EXTRA_GAP_BETWEEN_LINES: float,
        EXTRA_GAP_BETWEEN_WEATHER_LINES: float,
        IN_LABEL_LEFT_CHARS: float,
        IN_LABEL_DOWN_CHARS: float,
        OUT_ROW_SHIFT_DIGITS: int,
        OUT_VALUE_SHIFT_PX: int,
        DAY_ROOMTEMP_GAP_PX: int,
        WEEKDAY_SHIFT_PX: int,
        UNIT_LABEL_PAD_PX: int,
        WEEKDAY_ASCENT_ADJUST_PX: int,
        OUTDOOR_ROW_SHIFT_DOWN_PX: int,
        now,
        date_text: str,
        date_weekday_char: str,
        date_day_suffix: str,
        m_field: str,
        d_field: str,
        in_text: str,
        out_text: str,
        in_temp,
        out_temp,
        indoor_mode: str,
        outdoor_mode: str,
        theme_name: str | None = None,
        theme_spec = None,
        ens_fresh: bool = False,
        ens_aqi,
        ens_tvoc,
        ens_eco2,
        air_left_kind: str = "ECO2",
        air_left_value: int | None = None,
        air_left_unit: str = "PPM",
        air_left_source: str = "ENS160",
        air_right_kind: str = "TVOC",
        air_right_value: int | None = None,
        air_right_unit: str = "PPB",
        air_right_source: str = "ENS160",
        value_font_path: str | None = None,
        air_bar_colors = None,
        air_bar_outline_color = None,
    ) -> BottomInfoWidgetResult:
        # ===== Bottom area (2 lines): 上=室温, 下=外気 =====
        value_font_path = value_font_path or FONT_7SEG_PATH
        lcd_mode = (theme_name == "lcd")
        lcd_bg_color = getattr(theme_spec, "bg_color", (186, 205, 176)) if theme_spec is not None else (186, 205, 176)
        font_7seg_info_tmp = load_font(value_font_path, base_info_size)
        font_info_txt_tmp = load_font(info_font_path, base_info_size)
        font_info_txt_big_tmp = load_font(info_font_path, int(base_info_size * TXT_SCALE_DATE_OUT))

        date_parts_tmp = render_run(font_7seg_info_tmp, font_info_txt_tmp, date_text, color)
        spacer_parts_tmp = render_run(font_7seg_info_tmp, font_info_txt_tmp, "   ", color)
        in_value_parts_tmp = render_run(font_7seg_info_tmp, font_info_txt_tmp, f"{in_text}", color, digit_w_7seg=font_7seg_info_tmp.render("0", True, color).get_width())
        in_line_tmp = date_parts_tmp + spacer_parts_tmp + in_value_parts_tmp
        out_value_parts_tmp = render_run(font_7seg_info_tmp, font_info_txt_tmp, f"{out_text}", color, digit_w_7seg=font_7seg_info_tmp.render("0", True, color).get_width())

        bottom_ref_w_tmp = max(
            total_width(in_line_tmp),
            total_width(date_parts_tmp) + total_width(spacer_parts_tmp) + total_width(out_value_parts_tmp),
            1,
        )
        BOTTOM_WIDTH_BOOST = 1.25
        max_allowed_w = int(canvas.get_width() * 0.98)
        scale = (top_width / bottom_ref_w_tmp) * BOTTOM_WIDTH_BOOST
        font_info_size = max(10, int(base_info_size * scale))

        for _ in range(6):
            font_7seg_info_chk = load_font(value_font_path, font_info_size)
            font_info_txt_chk = load_font(info_font_path, font_info_size)
            font_info_txt_big_chk = load_font(info_font_path, int(font_info_size * TXT_SCALE_DATE_OUT))
            _date_parts = render_run(font_7seg_info_chk, font_info_txt_big_chk, date_text, color)
            _spacer_parts = render_run(font_7seg_info_chk, font_info_txt_chk, "   ", color)
            _in_value_parts = render_run(font_7seg_info_chk, font_info_txt_chk, f"{in_text}", color, digit_w_7seg=font_7seg_info_chk.render("0", True, color).get_width())
            _out_value_parts = render_run(font_7seg_info_chk, font_info_txt_big_chk, f"{out_text}", color, digit_w_7seg=font_7seg_info_chk.render("0", True, color).get_width())
            _w = max(
                total_width(_date_parts) + total_width(_spacer_parts) + total_width(_in_value_parts),
                total_width(_date_parts) + total_width(_spacer_parts) + total_width(_out_value_parts),
                1,
            )
            if _w <= max_allowed_w:
                break
            font_info_size = max(10, int(font_info_size * 0.95))

        font_7seg_info = load_font(value_font_path, font_info_size)
        font_info_txt = load_font(info_font_path, font_info_size)
        font_label = load_font(info_font_path, max(8, int(font_info_size * LABEL_RATIO)))
        font_source = load_font(info_font_path, max(6, int(font_label.get_height() * 0.234)))
        TXT_RAISE_PX = int(font_info_size * TXT_RAISE_RATIO)
        LABEL_GAP_PX = max(0, int(font_info_size * LABEL_GAP_RATIO))

        digit_w_info = font_7seg_info.render("0", True, color).get_width()
        pad_unit = (make_blank_slot(UNIT_LABEL_PAD_PX, font_label.get_height()), font_label.get_ascent(), False, ' ', font_label)

        year_parts = render_run(font_7seg_info, font_label, f"{now.year:04d}", color, digit_w_7seg=digit_w_info)
        year_unit = render_run(font_7seg_info, font_label, "年", color, digit_w_7seg=digit_w_info)
        mon_parts = render_run(font_7seg_info, font_label, m_field, color, digit_w_7seg=digit_w_info)
        mon_unit = render_run(font_7seg_info, font_label, "月", color, digit_w_7seg=digit_w_info)
        day_parts = render_run(font_7seg_info, font_label, d_field, color, digit_w_7seg=digit_w_info)
        day_unit = render_run(font_7seg_info, font_label, "日", color, digit_w_7seg=digit_w_info)

        date_prefix_parts = (
            year_parts + [pad_unit] + year_unit + [pad_unit] +
            mon_parts + [pad_unit] + mon_unit + [pad_unit] +
            day_parts + [pad_unit] + day_unit
        )

        weekday_parts = render_run(font_7seg_info, font_info_txt, date_weekday_char, color, digit_w_7seg=digit_w_info) if date_weekday_char else []
        if weekday_parts and WEEKDAY_ASCENT_ADJUST_PX:
            weekday_parts = [
                (surf, ascent + WEEKDAY_ASCENT_ADJUST_PX, is7, raw_text, raw_font)
                for (surf, ascent, is7, raw_text, raw_font) in weekday_parts
            ]
        weekday_suffix_parts = ([pad_unit] + render_run(font_7seg_info, font_label, date_day_suffix, color, digit_w_7seg=digit_w_info) + [pad_unit]) if date_day_suffix else []
        date_day_parts = weekday_parts + weekday_suffix_parts

        in_value_parts = render_run(font_7seg_info, font_info_txt, f"{in_text}", color, digit_w_7seg=digit_w_info)
        out_value_parts = render_run(font_7seg_info, font_info_txt, f"{out_text}", color, digit_w_7seg=digit_w_info)

        date_w = total_width(date_prefix_parts) + total_width(date_day_parts)
        date_prefix_w = total_width(date_prefix_parts)
        spacer_parts = render_run(font_7seg_info, font_info_txt, "   ", color)
        spacer_w = total_width(spacer_parts) + DAY_ROOMTEMP_GAP_PX

        in_value_w = total_width(in_value_parts)
        in_w = date_w + spacer_w + in_value_w

        x_in = (canvas.get_width() - in_w) // 2  # (fix) center bottom line to canvas width
        digit_w_info = font_7seg_info.render("0", True, color).get_width()
        out_row_shift_px = digit_w_info * OUT_ROW_SHIFT_DIGITS
        x_out = x_in + out_row_shift_px

        # (added) Recover top position and height from TimeWidget rect


        y_top = int(time_rect_canvas.top)


        main_h = int(time_rect_canvas.height)


        # Base baseline (same as before) + explicit spacing to accommodate the air-quality bar
        # between the time line and the date/indoor line.
        # NOTE: AIR_BAR_PAD_Y is treated as the *visual gap* above/below the bar.
        baseline_y_in_base = (y_top + main_h + int(font_info_size * (1.2 + EXTRA_GAP_BETWEEN_LINES)))
        baseline_y_in = baseline_y_in_base + (AIR_BAR_PAD_Y * 2) + AIR_BAR_HEIGHT_PX
        baseline_y_out = baseline_y_in + int(font_info_size * EXTRA_GAP_BETWEEN_WEATHER_LINES) + OUTDOOR_ROW_SHIFT_DOWN_PX


        # ===== Air quality bar (between time line and date/indoor line) =====
        # Bar spans the "time width" and the "calendar+indoor width" (use the larger, centered).
        # - 5 segments (blue/green/yellow/orange/red)
        # - Current level is highlighted; others are dimmed
        # - If no fresh AQI, draw all segments dimmed
        def _parts_bbox_local(parts, x0, baseline_y, raise_txt_px):
            left = x0
            top = 10**9
            right = x0
            bottom = -10**9
            cx = x0
            for surf, ascent, is_7seg, raw_text, font_used in parts:
                y = baseline_y - ascent
                if not is_7seg:
                    y -= raise_txt_px
                r = pygame.Rect(cx, y, surf.get_width(), surf.get_height())
                top = min(top, r.top)
                bottom = max(bottom, r.bottom)
                right = max(right, r.right)
                cx += surf.get_width()
            if bottom < top:
                return pygame.Rect(x0, baseline_y - 1, 1, 1)
            return pygame.Rect(left, top, right - left, bottom - top)

        # Air bar placement:
        # Center the bar vertically between the time line and the date/indoor line.
        # Clamp to keep at least AIR_BAR_PAD_Y above/below for readability.
        time_bottom_y = (y_top + main_h)
        date_line_bbox = _parts_bbox_local(date_prefix_parts + date_day_parts, x_in, baseline_y_in, 0)
        gap_top = int(time_bottom_y)
        gap_bottom = int(date_line_bbox.top)
        # Ideal centered position (use round to avoid floor-bias) + small optical bias.
        free_h = max(0, (gap_bottom - gap_top - AIR_BAR_HEIGHT_PX))
        bar_y = int(gap_top + int(round(free_h / 2.0)) + AIR_BAR_CENTER_BIAS_PX)
        # clamp with padding
        bar_y_min = int(gap_top + AIR_BAR_PAD_Y)
        bar_y_max = int(gap_bottom - AIR_BAR_PAD_Y - AIR_BAR_HEIGHT_PX)
        if bar_y < bar_y_min:
            bar_y = bar_y_min
        if bar_y > bar_y_max:
            bar_y = bar_y_max

        bar_w = int(min(canvas.get_width() * 0.98, max(int(top_width), int(in_w))))
        bar_x = int((canvas.get_width() - bar_w) // 2)

        custom_palette = air_bar_colors is not None
        ui_b = _brightness_from_ui_color(color)
        level = int(ens_aqi) if (ens_fresh and (ens_aqi is not None)) else None
        if level is not None:
            level = max(1, min(AIR_BAR_SEGMENTS, level))

        seg_w = max(1, bar_w // AIR_BAR_SEGMENTS)
        for i in range(AIR_BAR_SEGMENTS):
            x0 = bar_x + i * seg_w
            w0 = seg_w if i < AIR_BAR_SEGMENTS - 1 else (bar_x + bar_w - x0)
            palette = air_bar_colors if air_bar_colors is not None else AIR_BAR_COLORS
            base_c = palette[i]
            active = (level is not None) and ((i + 1) == level)
            if custom_palette:
                m_c = 0.92 if active else 0.55
            else:
                m_c = (1.0 if active else 0.22) * ui_b
            c = _mul_rgb(base_c, m_c)
            pygame.draw.rect(canvas, c, pygame.Rect(x0, bar_y, w0, AIR_BAR_HEIGHT_PX), border_radius=4)

        # subtle outline (use UI color)
        try:
            outline_c = air_bar_outline_color if air_bar_outline_color is not None else _mul_rgb(color, 0.35)
            pygame.draw.rect(canvas, outline_c, pygame.Rect(bar_x, bar_y, bar_w, AIR_BAR_HEIGHT_PX), width=1, border_radius=4)
        except Exception:
            pass


        blit_hstack_baseline(canvas, date_prefix_parts, x_in, baseline_y_in, 0, lcd_mode=lcd_mode, lcd_bg_color=lcd_bg_color, main_color=color)
        if date_day_parts:
            blit_hstack_baseline(canvas, date_day_parts, x_in + date_prefix_w + WEEKDAY_SHIFT_PX, baseline_y_in, 0, lcd_mode=lcd_mode, lcd_bg_color=lcd_bg_color, main_color=color)

        value_start_x_in = x_in + date_w + spacer_w
        blit_hstack_baseline(canvas, in_value_parts, value_start_x_in, baseline_y_in, TXT_RAISE_PX, lcd_mode=lcd_mode, lcd_bg_color=lcd_bg_color, main_color=color)

        value_start_x_out = x_out + date_w + spacer_w

        in_temp_field = fmt_temp_field(in_temp)
        out_temp_field = fmt_temp_field(out_temp)
        in_dot_x = _dot_x_from_temp_field(value_start_x_in, in_temp_field, font_7seg_info, digit_w_info)
        out_dot_x = _dot_x_from_temp_field(value_start_x_out + OUT_VALUE_SHIFT_PX, out_temp_field, font_7seg_info, digit_w_info)

        decimal_align_delta = 0
        if (in_dot_x is not None) and (out_dot_x is not None):
            decimal_align_delta = int(in_dot_x - out_dot_x)
        out_value_shift_effective = int(OUT_VALUE_SHIFT_PX + decimal_align_delta)

        blit_hstack_baseline(canvas, out_value_parts, value_start_x_out + out_value_shift_effective, baseline_y_out, TXT_RAISE_PX, lcd_mode=lcd_mode, lcd_bg_color=lcd_bg_color, main_color=color)

        in_digit_top = digit_top_y(in_value_parts, baseline_y_in)
        out_digit_top = digit_top_y(out_value_parts, baseline_y_out)

        surf_label_in = font_label.render("室温", True, color)
        surf_label_out = font_label.render("外気", True, color)

        label_char_w = font_label.size("室")[0]
        label_char_h = font_label.size("室")[1]

        in_label_x = value_start_x_in - int(label_char_w * IN_LABEL_LEFT_CHARS)
        in_label_y = ((in_digit_top - LABEL_GAP_PX - surf_label_in.get_height()) if in_digit_top is not None else (baseline_y_in - surf_label_in.get_height()))
        in_label_y += int(label_char_h * IN_LABEL_DOWN_CHARS)

        out_label_x = value_start_x_out - int(label_char_w * IN_LABEL_LEFT_CHARS)
        out_label_y = ((out_digit_top - LABEL_GAP_PX - surf_label_out.get_height()) if out_digit_top is not None else (baseline_y_out - surf_label_out.get_height()))
        out_label_y += int(label_char_h * IN_LABEL_DOWN_CHARS)

        blit_text_with_lcd_shadow(canvas, font_label, "室温", color, in_label_x, in_label_y, lcd_mode=lcd_mode)
        blit_text_with_lcd_shadow(canvas, font_label, "外気", color, out_label_x, out_label_y, lcd_mode=lcd_mode)

        surf_in_source = font_source.render(indoor_mode, True, color)
        in_source_x = in_label_x + (surf_label_in.get_width() - surf_in_source.get_width()) // 2
        in_source_y = in_label_y + surf_label_in.get_height() + int(font_source.get_height() * 0.15)
        blit_text_with_lcd_shadow(canvas, font_source, indoor_mode, color, in_source_x, in_source_y, lcd_mode=lcd_mode)

        surf_out_source = font_source.render(outdoor_mode, True, color)
        out_source_x = out_label_x + (surf_label_out.get_width() - surf_out_source.get_width()) // 2
        out_source_y = out_label_y + surf_label_out.get_height() + int(font_source.get_height() * 0.15)
        blit_text_with_lcd_shadow(canvas, font_source, outdoor_mode, color, out_source_x, out_source_y, lcd_mode=lcd_mode)


        # Air values: persistent touch-selectable pairs.
        # Left: ENS160 eCO2 or BME280 pressure. Right: ENS160 TVOC or SCD40 CO2.
        air_left_rect_canvas = None
        air_right_rect_canvas = None
        if True:
            # Keep a safety margin from the "外気" label to avoid overlap with unit text.
            right_margin = max(10, int(font_label.get_height() * 0.55))
            left_area_x0 = x_out
            left_area_x1 = out_label_x - right_margin
            left_area_w = max(0, left_area_x1 - left_area_x0)

            left_s = "----" if air_left_value is None else f"{min(max(int(air_left_value), 0), 9999):4d}"
            right_s = "----" if air_right_value is None else f"{min(max(int(air_right_value), 0), 9999):4d}"

            base_val_h = max(10, font_7seg_info.get_height())
            val_scales = (1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60)

            def _fit_and_draw(scale: float, gap_block_mul: float) -> bool:
                f_val = load_font(FONT_7SEG_PATH, max(10, int(base_val_h * scale)))
                digit_w_val = f_val.render("0", True, color).get_width()

                # Unit font (smaller, like calendar "年" etc.)
                f_unit = load_font(info_font_path, max(8, int(font_label.get_height() * 0.50)))

                gap_x = max(2, int(f_unit.get_height() * 0.18))
                gap_block = max(0, int(f_unit.get_height() * gap_block_mul))

                # Fixed-width 4-digit 7seg runs (spaces become full digit slots)
                left_parts = render_run(f_val, f_unit, left_s, color, digit_w_7seg=digit_w_val)
                right_parts = render_run(f_val, f_unit, right_s, color, digit_w_7seg=digit_w_val)
                w_left = total_width(left_parts)
                w_right = total_width(right_parts)

                surf_unit_left = f_unit.render(air_left_unit, True, color)
                surf_unit_right = f_unit.render(air_right_unit, True, color)

                # Labels should be placed to the LEFT of each 7-seg value (like "室温"/"外気"),
                # top-aligned with the 7-seg digits.
                # Render "eCO₂" with a smaller subscript "2" (bottom-aligned).
                label_left = "eCO₂" if air_left_kind == "ECO2" else "気圧"
                label_right = "CO₂" if air_right_kind == "CO2" else "TVOC"
                surf_label_left = font_label.render(label_left, True, color)
                surf_label_right = font_label.render(label_right, True, color)
                surf_source_left = font_source.render(air_left_source, True, color)
                surf_source_right = font_source.render(air_right_source, True, color)
                left_label_w = max(surf_label_left.get_width(), surf_source_left.get_width())
                right_label_w = max(surf_label_right.get_width(), surf_source_right.get_width())
                label_gap_x = max(4, int(font_label.get_height() * 0.25))

                left_block_w = left_label_w + label_gap_x + w_left + gap_x + surf_unit_left.get_width()
                right_block_w = right_label_w + label_gap_x + w_right + gap_x + surf_unit_right.get_width()
                total_w = left_block_w + gap_block + right_block_w
                if left_area_w <= 0 or total_w > left_area_w:
                    return False

                digit_top = baseline_y_out - f_val.get_ascent()
                digit_h = f_val.get_height()
                digit_bottom = digit_top + digit_h
                # Units: subscript-style (slightly lower than the digit bottom),
                # similar to calendar "年/月/日" feel.
                unit_sub_px = max(2, int(surf_unit_left.get_height() * 0.25))
                y_unit_left = digit_top + (digit_h - surf_unit_left.get_height()) + unit_sub_px
                y_unit_right = digit_top + (digit_h - surf_unit_right.get_height()) + unit_sub_px

                x = left_area_x0 + (left_area_w - total_w) // 2

                # Labels: left of value, top-aligned with the 7-seg digits
                y_label = digit_top
                x_label = x
                label_left_x = x_label + (left_label_w - surf_label_left.get_width()) // 2
                blit_text_with_lcd_shadow(canvas, font_label, label_left, color, label_left_x, y_label, lcd_mode=lcd_mode)
                source_left_x = x_label + (left_label_w - surf_source_left.get_width()) // 2
                source_y = y_label + surf_label_left.get_height() + int(font_source.get_height() * 0.15)
                blit_text_with_lcd_shadow(canvas, font_source, air_left_source, color, source_left_x, source_y, lcd_mode=lcd_mode)

                x_value = x_label + left_label_w + label_gap_x

                # eCO2 value
                if lcd_mode:
                    left_ghost_parts = render_run(f_val, f_unit, "8888", color, digit_w_7seg=digit_w_val)
                    blit_lcd_ghost_only(canvas, left_ghost_parts, x_value, baseline_y_out, 0, lcd_bg_color=lcd_bg_color, main_color=color)
                blit_hstack_baseline(canvas, left_parts, x_value, baseline_y_out, 0, lcd_mode=False, lcd_bg_color=lcd_bg_color, main_color=color)
                x_unit = x_value + w_left + gap_x
                blit_text_with_lcd_shadow(canvas, f_unit, air_left_unit, color, x_unit, y_unit_left, lcd_mode=lcd_mode)
                left_right = x_unit + surf_unit_left.get_width()
                nonlocal air_left_rect_canvas, air_right_rect_canvas
                air_left_rect_canvas = pygame.Rect(x_label, y_label, left_right - x_label, max(digit_bottom, source_y + surf_source_left.get_height()) - y_label)

                x = left_right + gap_block

                # TVOC label + value
                x_label = x
                label_right_x = x_label + (right_label_w - surf_label_right.get_width()) // 2
                blit_text_with_lcd_shadow(canvas, font_label, label_right, color, label_right_x, y_label, lcd_mode=lcd_mode)
                source_right_x = x_label + (right_label_w - surf_source_right.get_width()) // 2
                blit_text_with_lcd_shadow(canvas, font_source, air_right_source, color, source_right_x, source_y, lcd_mode=lcd_mode)
                x_value = x_label + right_label_w + label_gap_x

                # TVOC value
                if lcd_mode:
                    right_ghost_parts = render_run(f_val, f_unit, "8888", color, digit_w_7seg=digit_w_val)
                    blit_lcd_ghost_only(canvas, right_ghost_parts, x_value, baseline_y_out, 0, lcd_bg_color=lcd_bg_color, main_color=color)
                blit_hstack_baseline(canvas, right_parts, x_value, baseline_y_out, 0, lcd_mode=False, lcd_bg_color=lcd_bg_color, main_color=color)
                x_unit = x_value + w_right + gap_x
                blit_text_with_lcd_shadow(canvas, f_unit, air_right_unit, color, x_unit, y_unit_right, lcd_mode=lcd_mode)
                right_right = x_unit + surf_unit_right.get_width()
                air_right_rect_canvas = pygame.Rect(x_label, y_label, right_right - x_label, max(digit_bottom, source_y + surf_source_right.get_height()) - y_label)
                return True

            gap_block_candidates = (0.35, 0.25, 0.15, 0.10, 0.05, 0.00)
            drawn = False
            for sc in val_scales:
                for gbm in gap_block_candidates:
                    if _fit_and_draw(sc, gbm):
                        drawn = True
                        break
                if drawn:
                    break






        def _parts_bbox(parts, x0, baseline_y, raise_txt_px):
            left = x0
            top = 10**9
            right = x0
            bottom = -10**9
            cx = x0
            for surf, ascent, is_7seg, raw_text, font_used in parts:
                y = baseline_y - ascent
                if not is_7seg:
                    y -= raise_txt_px
                r = pygame.Rect(cx, y, surf.get_width(), surf.get_height())
                top = min(top, r.top)
                bottom = max(bottom, r.bottom)
                right = max(right, r.right)
                cx += surf.get_width()
            if bottom < top:
                return pygame.Rect(x0, baseline_y - 1, 1, 1)
            return pygame.Rect(left, top, right - left, bottom - top)

        indoor_rect_canvas = _parts_bbox(in_value_parts, value_start_x_in, baseline_y_in, TXT_RAISE_PX)
        outdoor_rect_canvas = _parts_bbox(out_value_parts, value_start_x_out + out_value_shift_effective, baseline_y_out, TXT_RAISE_PX)

        # Date touch area (year/month/day + weekday)
        date_prefix_rect_canvas = _parts_bbox(date_prefix_parts, x_in, baseline_y_in, TXT_RAISE_PX)
        if date_day_parts:
            date_day_rect_canvas = _parts_bbox(date_day_parts, x_in + date_prefix_w + WEEKDAY_SHIFT_PX, baseline_y_in, TXT_RAISE_PX)
            date_rect_canvas = date_prefix_rect_canvas.union(date_day_rect_canvas)
        else:
            date_rect_canvas = date_prefix_rect_canvas

        return BottomInfoWidgetResult(
            indoor_rect_canvas=indoor_rect_canvas,
            outdoor_rect_canvas=outdoor_rect_canvas,
            date_rect_canvas=date_rect_canvas,
            air_left_rect_canvas=air_left_rect_canvas,
            air_right_rect_canvas=air_right_rect_canvas,
        )


# -----------------------------------------------------------------------------
