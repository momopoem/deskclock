# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations
import os
import threading
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default

__product__ = "Desk Side Clock"
__version__ = "v2.4.8"
__status__ = "release"
APP_VERSION = __version__

UI_SCALE = 1.2
I2C_LOCK = threading.Lock()

# The TCL's physical output is 1920x1200.  Wayland can transiently hand SDL a
# 1920x1080 *logical* surface after HDMI wake; that value must never determine
# font sizes or the Desk Side Clock layout.
DISPLAY_NATIVE_WIDTH = 1920
DISPLAY_NATIVE_HEIGHT = 1200
DISPLAY_LAYOUT_WIDTH = 1920
DISPLAY_LAYOUT_HEIGHT = 1200

AHT21_ENABLE = True
AHT21_I2C_BUS = 1
AHT21_ADDR = 0x38
AHT21_REFRESH_SEC = 5
AHT21_TEMP_OFFSET_C = -7.1
AHT21_HUM_OFFSET_PCT = 11

ENS160_ENABLE = True
ENS160_I2C_BUS = 1
ENS160_ADDR = 0x53
ENS160_REFRESH_SEC = 5
ENS160_COMP_STALE_SEC = 15.0
ENS160_VALUE_STALE_SEC = 30.0

BME280_ENABLE = True
BME280_I2C_BUS = int(os.environ.get("BME280_I2C_BUS", "1"))
BME280_ADDR = int(os.environ.get("BME280_ADDR", "0x76"), 16)
BME280_REFRESH_SEC = 5
# Existing temperature offset -5.1°C plus the requested -0.1°C adjustment.
BME280_TEMP_OFFSET_C = -5.2
BME280_HUM_OFFSET_PCT = 15
BME280_VALUE_STALE_SEC = 30.0

SCD40_ENABLE = True
SCD40_I2C_BUS = int(os.environ.get("SCD40_I2C_BUS", "1"))
SCD40_ADDR = int(os.environ.get("SCD40_ADDR", "0x62"), 16)
SCD40_REFRESH_SEC = 5
SCD40_VALUE_STALE_SEC = 30.0

# Existing offsets plus the requested temperature -4.8°C / humidity +14%RH.
SHT20_TEMP_OFFSET_C = -9.0
SHT20_HUM_OFFSET_PCT = 14
SHT20_REFRESH_SEC = 5
SHT20_I2C_ADDR = int(os.environ.get("SHT20_ADDR", "0x40"), 16)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONT_7SEG_PATH = str(PROJECT_ROOT / "fonts" / "DSEG7Classic-Bold.ttf")
INFO_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

LAT = float(os.environ.get("OPEN_METEO_LATITUDE", "35.0"))
LON = float(os.environ.get("OPEN_METEO_LONGITUDE", "135.0"))
TIMEZONE = os.environ.get("OPEN_METEO_TIMEZONE", "Asia/Tokyo")
WEATHER_REFRESH_SEC = 900
OPEN_METEO_BASE_URL = os.environ.get(
    "OPEN_METEO_BASE_URL",
    "https://api.open-meteo.com/v1/forecast",
).rstrip("?")
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
OPEN_METEO_DISPLAY_LABEL = "OPEN-METEO.COM"

WEATHER_ICON_ENABLE = True
WEATHER_ICON_MARGIN_Y = 2
WEATHER_ICON_STROKE = 2
WEATHER_ICON_SCALE = 1.44
WEATHER_ICON_RAISE_PX = 16
WEATHER_ICON_TTF_PATH = str(PROJECT_ROOT / "fonts" / "weathericons" / "weathericons-regular-webfont.ttf")
WEATHER_ICON_USE_PSEUDO_COLOR = True
WEATHER_KIND_COLOR = {
    "sun":       (255, 200, 0),
    "sun_cloud": (255, 200, 0),
    "cloud":     (200, 200, 200),
    "fog":       (180, 180, 180),
    "rain":      (80, 170, 255),
    "snow":      (210, 240, 255),
    "thunder":   (255, 220, 0),
    "unknown":   None,
}
WEATHER_KIND_GLYPH = {
    "sun":       "\uf00d",
    "sun_cloud": "\uf002",
    "cloud":     "\uf013",
    "fog":       "\uf014",
    "rain":      "\uf019",
    "snow":      "\uf01b",
    "thunder":   "\uf01e",
    "unknown":   "\uf07b",
}

NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 7
NIGHT_DIM_RATIO = 1.0

BRIGHTNESS_GAMMA = 1.0

PIR_ENABLE = True
PIR_GPIOCHIP = os.environ.get("SR501_GPIOCHIP", "gpiochip0")
PIR_LINE = int(os.environ.get("SR501_LINE", "17"))

DISPLAY_PM_ENABLE = True
DIM_AFTER_SEC = 180
OFF_AFTER_SEC = 300
OFF_AFTER_DIM_SEC = 60
LUX_DARK = 3.0
LUX_BRIGHT = 10.0
DIM_BRIGHTNESS_CAP = 0.08
OFF_NIGHT_START = (23, 0)
OFF_NIGHT_END = (6, 0)
HDMI_OFF_CMD = ["sudo", "-n", "/usr/local/bin/hdmi_off.sh"]
HDMI_ON_CMD = ["sudo", "-n", "/usr/local/bin/hdmi_on.sh"]

LIGHT_OFF_TIMEOUT_SEC = 300
LIGHT_PIR_SUSTAINED_SEC = 2.0
LIGHT_PIR_PULSE_SEC = 0.4
LIGHT_PIR_REPEAT_WINDOW_SEC = 10.0
PIR_NO_MOTION_SEC = 180
PIR_DIM_TO = 0.20
PIR_FADE_SEC = 10.0
PIR_WAKE_OVERRIDE_SEC = 2.0
# Trial display-presence policy (seconds); independent of the room-light timer.
DISPLAY_PIR_CONFIRM_SEC = 0.6
DISPLAY_MOTION_HOLD_SEC = 300.0
DISPLAY_FACE_HOLD_SEC = 600.0
DISPLAY_FADE_SEC = 30.0
DISPLAY_FACE_CHECK_IDLE_SEC = 30.0
DISPLAY_FACE_CHECK_INTERVAL_SEC = 60.0
DISPLAY_FACE_MISSES_REQUIRED = 3
DISPLAY_CAMERA_FAILURE_GRACE_SEC = 120.0
# A PIR edge alone does not start or prolong a display session. The camera
# must also observe movement in the user-selected doorway region (E2:E5 in a
# 8x6 calibration grid). Fractions survive a camera-resolution change.
DISPLAY_DOORWAY_MOTION_REQUIRED = True
DISPLAY_DOORWAY_ROI = (4 / 8, 1 / 6, 5 / 8, 5 / 6)  # E2 through E5
DISPLAY_DOORWAY_FRAMES = 4
DISPLAY_DOORWAY_FRAME_INTERVAL_SEC = 0.15
DISPLAY_DOORWAY_MIN_CHANGED_RATIO = 0.015
DISPLAY_DOORWAY_MAX_CHANGED_RATIO = 0.45
DISPLAY_DOORWAY_MIN_ACTIVE_BANDS = 2
DEBUG_SR501 = True
SR501_DOT_RADIUS = 6
SR501_DOT_MARGIN = 10

BH1750_ENABLE = True
BH1750_I2C_BUS = 1
BH1750_ADDR = int(os.environ.get("BH1750_ADDR", "0x23"), 16)
BH1750_LIGHT_ON_LX = 5.0
BH1750_WAKE_LX = 10.0
BH1750_DARK_LX = 2.0
BH1750_STALE_SEC = 10.0
BH1750_POLL_SEC = 1.0
BH1750_DIM_TO_DARK = 0.00
BH1750_DIM_TO_LIGHTOFF = 0.20
BH1750_FADE_SEC = 10.0

NTP_CHECK_INTERVAL_SEC = 5.0
NTP_RETRY_DELAY_SEC = 60.0 * 60.0
NTP_DEGRADED_CHECK_SEC = 5.0 * 60.0

SWITCHBOT_REFRESH_SEC = 60
# Keep the physical I2C sensors adjacent to make the on-screen cycle clear.
INDOOR_SOURCES = ["SHT20", "AHT21", "SWITCHBOT", "BME280"]
OUTDOOR_SOURCES = ["SWITCHBOT", "OPEN_METEO"]
STATE_DIR = os.path.expanduser("~/.config/deskclock")
STATE_PATH = os.path.join(STATE_DIR, "state.json")

SWITCHBOT_LIGHT_TIMEOUT_SEC = 8
SWITCHBOT_LIGHT_COOLDOWN_SEC = 3.0
# The desk television follows the display/light presence session. It remains
# opt-in until its dedicated SwitchBot virtual remote and Android TV pairing
# material have been provisioned on the clock.
TV_ENABLE = os.environ.get("DESKCLOCK_TV_ENABLE", "0").strip().lower() in {"1", "true", "yes", "on"}
TV_HOST = os.environ.get("DESKCLOCK_TV_HOST", "")
TV_CERT_PATH = os.path.expanduser(
    os.environ.get("DESKCLOCK_TV_CERT_PATH", "~/.config/deskclock/tv/client.pem")
)
TV_KEY_PATH = os.path.expanduser(
    os.environ.get("DESKCLOCK_TV_KEY_PATH", "~/.config/deskclock/tv/client.key")
)
TV_PLUG_DEVICE_ID = os.environ.get("SWITCHBOT_tvPlugDeviceId", "")
TV_POWER_ON_WATT = _env_float("DESKCLOCK_TV_POWER_ON_WATT", 50.0)
TV_POWER_OFF_WATT = _env_float("DESKCLOCK_TV_POWER_OFF_WATT", 40.0)
TV_DETECT_DELAY_SEC = 2.0
TV_ON_MAX_ATTEMPTS = 10
TV_OFF_MAX_ATTEMPTS = 10
# A TV often reports a middle consumption value for a few seconds while its
# panel changes state.  These are trace bands, not single-reading decisions.
TV_POWER_SETTLE_READS = 6
TV_POWER_CONFIRM_READS = 2
LIGHT_PROBE_SEC = 8.0
AUTHORIZED_USER_LIGHT_GRACE_SEC = 1800.0
LIGHT_OFF_TIMEOUT_SEC = 300.0
FACE_RECOG_PY = "/usr/bin/python3"
FACE_RECOG_SCRIPT = str(PROJECT_ROOT / "face" / "recognize_once.py")
FACE_PRIVATE_DIR = os.path.expanduser(
    os.environ.get("DESKCLOCK_FACE_DATA_DIR", "~/.local/share/deskclock/face")
)
FACE_RECOG_TIMEOUT_SEC = 12
