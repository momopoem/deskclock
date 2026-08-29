# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import time

from renderer.theme_engine import get_theme_spec


@dataclass
class CalendarPopupState:
    popup: bool = False
    anim_phase: str = "closed"  # closed|opening|open|closing
    anim_t0: float = 0.0
    open_mono: float = 0.0
    month_offset: int = 0

    def close(self) -> None:
        self.popup = False
        self.anim_phase = "closed"
        self.anim_t0 = 0.0
        self.open_mono = 0.0
        self.month_offset = 0

    def open(self, now_mono: float, month_offset: int = 0) -> None:
        self.popup = True
        self.anim_phase = "open"
        self.anim_t0 = 0.0
        self.open_mono = now_mono
        self.month_offset = month_offset


@dataclass
class LightControlState:
    enabled: bool = False
    is_on: bool = False
    last_cmd_mono: float = 0.0
    probe_until_mono: float = 0.0
    authorized_user_until_mono: float = 0.0
    deadline_mono: float = 0.0
    prev_pir_value: int = 0
    on_verify_active: bool = False
    on_baseline_lux: Optional[float] = None
    on_next_action_mono: float = 0.0
    on_next_action: str = ""
    on_attempts: int = 0
    on_failed_latched: bool = False
    face_recognition_pending: bool = False


@dataclass
class RuntimeUiState:
    base_color: tuple[int, int, int] = (255, 255, 255)
    touch_rects_screen: dict[str, Any] = field(default_factory=lambda: {
        "indoor": None,
        "outdoor": None,
        "date": None,
        "time": None,
        "weather": None,
        "air_left": None,
        "air_right": None,
    })
    last_key: str = ""
    color_changed: bool = False


@dataclass
class ClockState:
    """Shared runtime state for DeskSide Clock.

    Supports both attribute-style and mapping-style access so existing worker
    loops can continue to use shared["key"] / shared.get("key") during staged
    refactoring.
    """

    # Activity / brightness related
    activity_mono: float = field(default_factory=time.monotonic)
    pir_mono: float = field(default_factory=time.monotonic)
    pir_value: int = 0
    pir_err: str = ""
    lux: Optional[float] = None
    lux_mono: float = 0.0
    lux_err: str = ""
    _lux_state: str = "light"

    # Indoor sensors
    sht20_temp_c: Optional[float] = None
    sht20_hum_pct: Optional[int] = None
    sht20_ts: float = 0.0
    sht20_err: str = ""

    aht21_temp_c: Optional[float] = None
    aht21_hum_pct: Optional[int] = None
    aht21_ts: float = 0.0
    aht21_err: str = ""

    ens_aqi: Optional[int] = None
    ens_tvoc_ppb: Optional[int] = None
    ens_eco2_ppm: Optional[int] = None
    ens_ts: float = 0.0
    ens_err: str = ""

    bme280_temp_c: Optional[float] = None
    bme280_hum_pct: Optional[float] = None
    bme280_pressure_hpa: Optional[float] = None
    bme280_ts: float = 0.0
    bme280_err: str = ""

    scd40_co2_ppm: Optional[int] = None
    scd40_temp_c: Optional[float] = None
    scd40_hum_pct: Optional[float] = None
    scd40_ts: float = 0.0
    scd40_err: str = ""

    # SwitchBot indoor
    in_temp_c: Optional[float] = None
    in_hum_pct: Optional[int] = None
    in_ts: float = 0.0
    in_err: str = ""
    in_source: str = ""

    # Outdoor / weather
    out_temp_c: Optional[float] = None
    out_hum_pct: Optional[int] = None
    weather_code: Optional[int] = None
    weather_ts: float = 0.0
    weather_err: str = ""

    # Open-Meteo fallback
    net_temp_c: Optional[float] = None
    net_hum_pct: Optional[int] = None
    net_weather_code: Optional[int] = None
    net_ts: float = 0.0
    net_err: str = ""

    # UI/runtime state
    indoor_mode: str = "SHT20"
    outdoor_mode: str = "SWITCHBOT"
    time_mode_24h: bool = False
    theme: str = "default"
    air_left_mode: str = "ECO2"
    air_right_mode: str = "TVOC"
    ntp_synced: bool = False
    colon_visible: bool = True
    brightness_cur: float = 1.0
    brightness_target: float = 1.0
    ui: RuntimeUiState = field(default_factory=RuntimeUiState)
    calendar: CalendarPopupState = field(default_factory=CalendarPopupState)
    light: LightControlState = field(default_factory=LightControlState)
    ntp_state: dict[str, Any] = field(default_factory=lambda: {"last_check": 0.0, "synced": False})

    # For future expansion / backward-compatible unknown keys
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_ui_snapshot(cls, ui_state: dict[str, Any]) -> "ClockState":
        obj = cls()
        obj.indoor_mode = ui_state.get("indoor_mode", obj.indoor_mode)
        obj.outdoor_mode = ui_state.get("outdoor_mode", obj.outdoor_mode)
        obj.time_mode_24h = bool(ui_state.get("time_mode_24h", obj.time_mode_24h))
        obj.theme = get_theme_spec(ui_state.get("theme", obj.theme)).name
        obj.air_left_mode = ui_state.get("air_left_mode", obj.air_left_mode)
        if obj.air_left_mode not in ("ECO2", "PRESSURE"):
            obj.air_left_mode = "ECO2"
        obj.air_right_mode = ui_state.get("air_right_mode", obj.air_right_mode)
        if obj.air_right_mode not in ("TVOC", "CO2"):
            obj.air_right_mode = "TVOC"
        c = ui_state.get("ui_color", [255, 255, 255])
        if isinstance(c, (list, tuple)) and len(c) == 3:
            try:
                obj.ui.base_color = tuple(int(max(0, min(255, int(v)))) for v in c)
            except Exception:
                pass
        return obj

    @property
    def base_color(self) -> tuple[int, int, int]:
        return self.ui.base_color

    @base_color.setter
    def base_color(self, value: tuple[int, int, int]) -> None:
        self.ui.base_color = value

    @property
    def touch_rects_screen(self) -> dict[str, Any]:
        return self.ui.touch_rects_screen

    @property
    def last_key(self) -> str:
        return self.ui.last_key

    @last_key.setter
    def last_key(self, value: str) -> None:
        self.ui.last_key = value

    def save_ui_state(self, save_func) -> None:
        save_func(
            self.indoor_mode,
            self.outdoor_mode,
            self.time_mode_24h,
            self.base_color,
            self.theme,
            self.air_left_mode,
            self.air_right_mode,
        )

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self._extra[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self._extra.get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            cur = getattr(self, key)
            if cur is None:
                setattr(self, key, default)
                return default
            return cur
        return self._extra.setdefault(key, default)

    def update(self, *args, **kwargs) -> None:
        items: dict[str, Any] = {}
        for arg in args:
            if isinstance(arg, dict):
                items.update(arg)
        items.update(kwargs)
        for k, v in items.items():
            self[k] = v

    def to_dict(self) -> dict[str, Any]:
        data = {k: getattr(self, k) for k in self.__dataclass_fields__.keys() if k != "_extra"}
        data.update(self._extra)
        return data
