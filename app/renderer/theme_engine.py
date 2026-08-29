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
    air_bar_colors: tuple[tuple[int, int, int], ...] | None = None
    air_bar_outline_color: tuple[int, int, int] | None = None


LCD_BAR_COLORS = (
    (68, 112, 164),
    (82, 158, 111),
    (184, 166, 62),
    (190, 122, 54),
    (172, 72, 65),
)

THEME_ORDER = ["default", "lcd"]

_THEME_MAP: dict[str, ThemeSpec] = {
    "default": ThemeSpec(
        name="default",
        bg_color=(0, 0, 0),
        fg_color=(255, 255, 255),
        use_base_color=True,
    ),
    "lcd": ThemeSpec(
        name="lcd",
        bg_color=(186, 205, 176),
        fg_color=(24, 41, 74),
        use_base_color=False,
        air_bar_colors=LCD_BAR_COLORS,
        air_bar_outline_color=(42, 67, 92),
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
