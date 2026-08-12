from __future__ import annotations

from datetime import datetime

import pygame

from widgets.bottom_info_widget import BottomInfoWidget


def test_air_blocks_have_independent_touch_rectangles(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    try:
        canvas = pygame.Surface((1920, 1200))
        result = BottomInfoWidget().render(
            canvas=canvas,
            color=(255, 255, 255),
            top_width=1500,
            time_rect_canvas=pygame.Rect(200, 80, 1500, 500),
            info_font_path=None,
            base_info_size=100,
            TXT_SCALE_DATE_OUT=1.25,
            TXT_RAISE_RATIO=0.14,
            LABEL_RATIO=0.42,
            LABEL_GAP_RATIO=0.06,
            EXTRA_GAP_BETWEEN_LINES=0.45,
            EXTRA_GAP_BETWEEN_WEATHER_LINES=1.25,
            IN_LABEL_LEFT_CHARS=0.9,
            IN_LABEL_DOWN_CHARS=1.0,
            OUT_ROW_SHIFT_DIGITS=0,
            OUT_VALUE_SHIFT_PX=-15,
            DAY_ROOMTEMP_GAP_PX=20,
            WEEKDAY_SHIFT_PX=10,
            UNIT_LABEL_PAD_PX=6,
            WEEKDAY_ASCENT_ADJUST_PX=6,
            OUTDOOR_ROW_SHIFT_DOWN_PX=5,
            now=datetime(2026, 8, 12),
            date_text="2026年 8月12日水曜日",
            date_weekday_char="水",
            date_day_suffix="曜日",
            m_field=" 8",
            d_field="12",
            in_text=" 25.0°C 50%",
            out_text=" 30.0°C 60%",
            in_temp=25.0,
            out_temp=30.0,
            indoor_mode="SHT20",
            outdoor_mode="SWITCHBOT",
            ens_fresh=True,
            ens_aqi=1,
            ens_tvoc=123,
            ens_eco2=456,
            air_left_kind="PRESSURE",
            air_left_value=1013,
            air_left_unit="hPa",
            air_left_source="BME280",
            air_right_kind="CO2",
            air_right_value=650,
            air_right_unit="PPM",
            air_right_source="SCD40",
        )
        assert result.air_left_rect_canvas is not None
        assert result.air_right_rect_canvas is not None
        assert not result.air_left_rect_canvas.colliderect(result.air_right_rect_canvas)
    finally:
        pygame.quit()
