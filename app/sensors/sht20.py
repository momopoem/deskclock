# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def _sht20_read_temp_hum_via_i2c(bus_num: int = 1, addr: int = SHT20_I2C_ADDR):
    """Read SHT20 temperature/humidity via SMBus, ensuring the I2C FD is closed.

    Returns:
      (temp_c: float, hum_pct: int) or (None, None) on error.
    """
    # Try smbus2 first, then smbus
    SMBusClass = None
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
        SMBusClass = _SMBus
    except Exception:
        try:
            from smbus import SMBus as _SMBus  # type: ignore
            SMBusClass = _SMBus
        except Exception:
            SMBusClass = None

    if SMBusClass is None:
        return None, None

    # SHT20 commands (no-hold master mode)
    CMD_TEMP = 0xF3
    CMD_HUM  = 0xF5

    try:
        with SMBusClass(int(bus_num)) as bus:
            # Serialize access: BH1750 thread may keep a bus open; concurrent ioctls can cause EIO.
            with I2C_LOCK:
                # Temperature (no-hold master mode)
                bus.write_byte(addr, CMD_TEMP)

            # Wait for conversion; then read 2 bytes + CRC using raw I2C read (not SMBus block read).
            tdat = None
            for _ in range(10):
                time.sleep(0.02)
                try:
                    with I2C_LOCK:
                        if hasattr(bus, "i2c_rdwr"):
                            from smbus2 import i2c_msg  # type: ignore
                            msg = i2c_msg.read(addr, 3)
                            bus.i2c_rdwr(msg)
                            tdat = list(msg)
                        else:
                            # Fallback: some SMBus implementations only support SMBus block read.
                            tdat = bus.read_i2c_block_data(addr, 0x00, 3)
                    break
                except OSError:
                    # Sensor may still be busy -> retry
                    continue
            if not tdat or len(tdat) < 2:
                return None, None
            traw = ((tdat[0] << 8) | tdat[1]) & 0xFFFC

            # Humidity
            with I2C_LOCK:
                bus.write_byte(addr, CMD_HUM)

            hdat = None
            for _ in range(10):
                time.sleep(0.02)
                try:
                    with I2C_LOCK:
                        if hasattr(bus, "i2c_rdwr"):
                            from smbus2 import i2c_msg  # type: ignore
                            msg = i2c_msg.read(addr, 3)
                            bus.i2c_rdwr(msg)
                            hdat = list(msg)
                        else:
                            hdat = bus.read_i2c_block_data(addr, 0x00, 3)
                    break
                except OSError:
                    continue
            if not hdat or len(hdat) < 2:
                return None, None
            hraw = ((hdat[0] << 8) | hdat[1]) & 0xFFFC

        temp_c = -46.85 + (175.72 * traw / 65536.0)
        hum = -6.0 + (125.0 * hraw / 65536.0)
        # Clamp humidity to 0..100, round to int
        hum_i = int(round(max(0.0, min(100.0, hum))))
        return float(temp_c), hum_i
    except Exception:
        return None, None

def read_sht20_indoor(bus: int = 1):
    # Use direct I2C read to avoid FD leaks in third-party libs.
    return _sht20_read_temp_hum_via_i2c(bus_num=bus, addr=SHT20_I2C_ADDR)


# =========================
# SwitchBot Cloud API (Outdoor/Indoor via env vars)
# =========================
SWITCHBOT_REFRESH_SEC = 60

def fetch_sht20_loop(shared, stop_event):
    """Poll SHT20 on I2C in a background thread.

    This prevents blocking the main render loop (time/seconds update priority).
    Writes to:
      - sht20_temp_c
      - sht20_hum_pct
      - sht20_ts
    """
    while not stop_event.is_set():
        try:
            t_sht, h_sht = read_sht20_indoor(bus=1)
            if t_sht is not None and h_sht is not None:
                shared["sht20_temp_c"] = float(t_sht) + SHT20_TEMP_OFFSET_C
                shared["sht20_hum_pct"] = int(h_sht) + SHT20_HUM_OFFSET_PCT
                shared["sht20_ts"] = time.time()  # last good SHT20 sample
                # Fallback mirror for UI paths that expect in_temp_c/in_hum_pct (do not override SwitchBot indoor)
                if shared.get("in_temp_c") is None:
                    shared["in_temp_c"] = shared.get("sht20_temp_c")
                if shared.get("in_hum_pct") is None:
                    shared["in_hum_pct"] = shared.get("sht20_hum_pct")
                shared["sht20_err"] = ""
                # (moved) shared["sht20_ts"] is used instead
        except Exception:
            # keep last good values; no hard fail
            pass

        stop_event.wait(SHT20_REFRESH_SEC)
