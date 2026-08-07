# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

from dataclasses import dataclass
import threading
import pygame

from config import FONT_7SEG_PATH
from utils.common import load_font, pick_info_font_path
from services.sensor_manager import SensorManager, configure_default_workers
from services.brightness_controller import BrightnessController
from state import ClockState


@dataclass(frozen=True)
class UiDependencies:
    w: int
    h: int
    canvas: pygame.Surface
    font_main_size: int
    font_sec_size: int
    font_ampm_size: int
    base_info_size: int
    TXT_RAISE_RATIO: float
    TXT_SCALE_DATE_OUT: float
    EXTRA_GAP_BETWEEN_LINES: float
    EXTRA_GAP_BETWEEN_WEATHER_LINES: float
    LABEL_RATIO: float
    LABEL_GAP_RATIO: float
    IN_LABEL_LEFT_CHARS: float
    IN_LABEL_DOWN_CHARS: float
    OUT_ROW_SHIFT_DIGITS: int
    OUT_VALUE_SHIFT_PX: int
    DAY_ROOMTEMP_GAP_PX: int
    WEEKDAY_SHIFT_PX: int
    UNIT_LABEL_PAD_PX: int
    WEEKDAY_ASCENT_ADJUST_PX: int
    OUTDOOR_ROW_SHIFT_DOWN_PX: int
    font_7seg_main: pygame.font.Font
    font_7seg_sec: pygame.font.Font
    info_font_path: str | None
    font_ampm: pygame.font.Font
    AMPM_SLOT_W: int
    DIGIT_W: int
    DIGIT_H: int
    GAP_AMPM: int
    LONG_PRESS_SEC: float
    CAL_ANIM_SEC: float
    CAL_POPUP_TIMEOUT_SEC: float


@dataclass(frozen=True)
class ServiceDependencies:
    sensor_manager: SensorManager
    sensor_flags: dict[str, bool]
    brightness_ctrl: BrightnessController


def build_ui_dependencies(sw: int, sh: int) -> UiDependencies:
    w, h = sw, sh
    canvas = pygame.Surface((w, h)).convert()

    font_main_size = int(h * 0.55 * 0.5)
    font_sec_size = int(font_main_size * 0.5)
    font_ampm_size = int(font_main_size * 0.35)

    base_info_size = int((font_main_size * 0.28) * 1.50)
    TXT_RAISE_RATIO = 0.14
    TXT_SCALE_DATE_OUT = 1.25
    EXTRA_GAP_BETWEEN_LINES = 0.45
    EXTRA_GAP_BETWEEN_WEATHER_LINES = 1.25
    LABEL_RATIO = 0.42
    LABEL_GAP_RATIO = 0.06

    IN_LABEL_LEFT_CHARS = 0.9
    IN_LABEL_DOWN_CHARS = 1.0
    OUT_ROW_SHIFT_DIGITS = 0
    OUT_VALUE_SHIFT_PX = -15
    DAY_ROOMTEMP_GAP_PX = 20
    WEEKDAY_SHIFT_PX = 10
    UNIT_LABEL_PAD_PX = 6
    WEEKDAY_ASCENT_ADJUST_PX = 6
    OUTDOOR_ROW_SHIFT_DOWN_PX = 5

    font_7seg_main = load_font(FONT_7SEG_PATH, font_main_size)
    font_7seg_sec = load_font(FONT_7SEG_PATH, font_sec_size)
    info_font_path = pick_info_font_path()
    font_ampm = load_font(info_font_path, font_ampm_size)
    AMPM_SLOT_W = max(font_ampm.size("午前")[0], font_ampm.size("午後")[0])
    sample_digit = font_7seg_main.render("1", True, (255, 255, 255))
    DIGIT_W = sample_digit.get_width()
    DIGIT_H = sample_digit.get_height()
    GAP_AMPM = -int(DIGIT_W * 0.55)

    return UiDependencies(
        w=w,
        h=h,
        canvas=canvas,
        font_main_size=font_main_size,
        font_sec_size=font_sec_size,
        font_ampm_size=font_ampm_size,
        base_info_size=base_info_size,
        TXT_RAISE_RATIO=TXT_RAISE_RATIO,
        TXT_SCALE_DATE_OUT=TXT_SCALE_DATE_OUT,
        EXTRA_GAP_BETWEEN_LINES=EXTRA_GAP_BETWEEN_LINES,
        EXTRA_GAP_BETWEEN_WEATHER_LINES=EXTRA_GAP_BETWEEN_WEATHER_LINES,
        LABEL_RATIO=LABEL_RATIO,
        LABEL_GAP_RATIO=LABEL_GAP_RATIO,
        IN_LABEL_LEFT_CHARS=IN_LABEL_LEFT_CHARS,
        IN_LABEL_DOWN_CHARS=IN_LABEL_DOWN_CHARS,
        OUT_ROW_SHIFT_DIGITS=OUT_ROW_SHIFT_DIGITS,
        OUT_VALUE_SHIFT_PX=OUT_VALUE_SHIFT_PX,
        DAY_ROOMTEMP_GAP_PX=DAY_ROOMTEMP_GAP_PX,
        WEEKDAY_SHIFT_PX=WEEKDAY_SHIFT_PX,
        UNIT_LABEL_PAD_PX=UNIT_LABEL_PAD_PX,
        WEEKDAY_ASCENT_ADJUST_PX=WEEKDAY_ASCENT_ADJUST_PX,
        OUTDOOR_ROW_SHIFT_DOWN_PX=OUTDOOR_ROW_SHIFT_DOWN_PX,
        font_7seg_main=font_7seg_main,
        font_7seg_sec=font_7seg_sec,
        info_font_path=info_font_path,
        font_ampm=font_ampm,
        AMPM_SLOT_W=AMPM_SLOT_W,
        DIGIT_W=DIGIT_W,
        DIGIT_H=DIGIT_H,
        GAP_AMPM=GAP_AMPM,
        LONG_PRESS_SEC=0.8,
        CAL_ANIM_SEC=0.18,
        CAL_POPUP_TIMEOUT_SEC=10 * 60,
    )


def build_service_dependencies(state: ClockState, stop_event: threading.Event) -> ServiceDependencies:
    sensor_manager = SensorManager(stop_event=stop_event)
    sensor_flags = configure_default_workers(sensor_manager, state)
    brightness_ctrl = BrightnessController()
    return ServiceDependencies(
        sensor_manager=sensor_manager,
        sensor_flags=sensor_flags,
        brightness_ctrl=brightness_ctrl,
    )
