# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def _scd40_crc8(data: list[int] | tuple[int, ...] | bytes) -> int:
    crc = 0xFF
    for value in data:
        crc ^= int(value)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _scd40_parse_measurement(data: list[int] | bytes):
    if len(data) != 9:
        raise ValueError(f"SCD40 returned {len(data)} bytes, expected 9")
    words = []
    for offset in (0, 3, 6):
        pair = data[offset:offset + 2]
        if _scd40_crc8(pair) != data[offset + 2]:
            raise ValueError(f"SCD40 CRC mismatch at word {offset // 3}")
        words.append((int(pair[0]) << 8) | int(pair[1]))
    co2_ppm = words[0]
    temp_c = -45.0 + 175.0 * words[1] / 65535.0
    hum_pct = 100.0 * words[2] / 65535.0
    return int(co2_ppm), float(temp_c), float(hum_pct)


def fetch_scd40_loop(shared, stop_event):
    """Start SCD40 periodic measurement and publish true CO2 in ppm."""
    if not SCD40_ENABLE:
        return
    try:
        from smbus2 import SMBus as SMBusClass, i2c_msg  # type: ignore
    except Exception as e:
        shared["scd40_err"] = f"SCD40: smbus2 not available: {type(e).__name__}: {e}"
        return

    def command(bus, value: int):
        bus.i2c_rdwr(i2c_msg.write(SCD40_ADDR, [(value >> 8) & 0xFF, value & 0xFF]))

    try:
        with SMBusClass(int(SCD40_I2C_BUS)) as bus:
            # Stop any measurement left running by a previous process, then restart cleanly.
            try:
                with I2C_LOCK:
                    command(bus, 0x3F86)
                stop_event.wait(0.5)
            except OSError:
                pass
            with I2C_LOCK:
                command(bus, 0x21B1)
            if stop_event.wait(5.0):
                return

            while not stop_event.is_set():
                try:
                    with I2C_LOCK:
                        command(bus, 0xEC05)
                        time.sleep(0.002)
                        msg = i2c_msg.read(SCD40_ADDR, 9)
                        bus.i2c_rdwr(msg)
                        data = list(msg)
                    co2_ppm, temp_c, hum_pct = _scd40_parse_measurement(data)
                    shared["scd40_co2_ppm"] = co2_ppm
                    shared["scd40_temp_c"] = temp_c
                    shared["scd40_hum_pct"] = hum_pct
                    shared["scd40_ts"] = time.time()
                    shared["scd40_err"] = ""
                except Exception as e:
                    shared["scd40_err"] = f"SCD40: {type(e).__name__}: {e}"
                stop_event.wait(SCD40_REFRESH_SEC)
    except Exception as e:
        shared["scd40_err"] = f"SCD40: {type(e).__name__}: {e}"
