# -*- coding: utf-8 -*-
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeSpec:
    name: str
    bg_color: tuple[int, int, int]
    fg_color: tuple[int, int, int]
    use_base_color: bool = False
    use_7seg_time: bool = True
    use_7seg_info: bool = True
    time_scale: float = 1.0
    sec_scale: float = 1.0
    ampm_scale: float = 1.0
    gap_ampm_ratio: float = -0.55
    air_bar_colors: tuple[tuple[int, int, int], ...] | None = None
    air_bar_outline_color: tuple[int, int, int] | None = None
    nixie_glass: bool = False
    nixie_small_seconds: bool = False


LCD_BAR_COLORS = (
    (44, 67, 96),
    (78, 128, 98),
    (122, 116, 46),
    (120, 84, 36),
    (106, 42, 32),
)

THEME_ORDER = ["default", "classic", "modern", "nixie", "lcd", "flip"]

_THEME_MAP: dict[str, ThemeSpec] = {
    "default": ThemeSpec(
        name="default",
        bg_color=(0, 0, 0),
        fg_color=(255, 255, 255),
        use_base_color=True,
        use_7seg_time=True,
        use_7seg_info=True,
    ),
    "classic": ThemeSpec(
        name="classic",
        bg_color=(0, 0, 0),
        fg_color=(245, 245, 245),
        use_base_color=True,
        use_7seg_time=False,
        use_7seg_info=True,
        time_scale=0.92,
        sec_scale=0.78,
        ampm_scale=0.78,
        gap_ampm_ratio=-0.10,
    ),
    "modern": ThemeSpec(
        name="modern",
        bg_color=(8, 12, 20),
        fg_color=(235, 240, 248),
        use_base_color=False,
        use_7seg_time=False,
        use_7seg_info=True,
        time_scale=0.88,
        sec_scale=0.72,
        ampm_scale=0.72,
        gap_ampm_ratio=-0.06,
    ),
    "nixie": ThemeSpec(
        name="nixie",
        bg_color=(8, 4, 1),
        fg_color=(255, 148, 62),
        use_base_color=False,
        use_7seg_time=False,
        use_7seg_info=True,
        time_scale=1.0,
        sec_scale=1.0,
        ampm_scale=1.0,
        gap_ampm_ratio=-0.55,
        nixie_glass=False,
        nixie_small_seconds=False,
    ),
    "lcd": ThemeSpec(
        name="lcd",
        bg_color=(186, 205, 176),
        fg_color=(24, 41, 74),
        use_base_color=False,
        use_7seg_time=True,
        use_7seg_info=True,
        air_bar_colors=LCD_BAR_COLORS,
        air_bar_outline_color=(64, 92, 94),
    ),
    "flip": ThemeSpec(
        name="flip",
        bg_color=(18, 18, 18),
        fg_color=(242, 238, 224),
        use_base_color=False,
        use_7seg_time=True,
        use_7seg_info=True,
    ),
}


def get_theme_spec(name: str | None) -> ThemeSpec:
    if not name:
        return _THEME_MAP["default"]
    return _THEME_MAP.get(name, _THEME_MAP["default"])


def next_theme_name(name: str | None) -> str:
    if not name or name not in THEME_ORDER:
        return THEME_ORDER[0]
    i = THEME_ORDER.index(name)
    return THEME_ORDER[(i + 1) % len(THEME_ORDER)]
