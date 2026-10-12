# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def _bme280_parse_calibration(cal1: list[int], cal2: list[int]) -> dict[str, int]:
    """Decode the BME280 calibration registers into signed/unsigned values."""
    if len(cal1) != 26 or len(cal2) != 7:
        raise ValueError("invalid BME280 calibration length")

    def u16(data, offset):
        return int(data[offset] | (data[offset + 1] << 8))

    def s16(data, offset):
        value = u16(data, offset)
        return value - 0x10000 if value & 0x8000 else value

    def s8(value):
        return value - 0x100 if value & 0x80 else value

    def s12(value):
        return value - 0x1000 if value & 0x800 else value

    return {
        "T1": u16(cal1, 0), "T2": s16(cal1, 2), "T3": s16(cal1, 4),
        "P1": u16(cal1, 6), "P2": s16(cal1, 8), "P3": s16(cal1, 10),
        "P4": s16(cal1, 12), "P5": s16(cal1, 14), "P6": s16(cal1, 16),
        "P7": s16(cal1, 18), "P8": s16(cal1, 20), "P9": s16(cal1, 22),
        "H1": int(cal1[25]), "H2": s16(cal2, 0), "H3": int(cal2[2]),
        "H4": s12((cal2[3] << 4) | (cal2[4] & 0x0F)),
        "H5": s12((cal2[5] << 4) | (cal2[4] >> 4)),
        "H6": s8(cal2[6]),
    }


def _bme280_compensate(adc_t: int, adc_p: int, adc_h: int, cal: dict[str, int]):
    """Return temperature (C), humidity (%RH) and pressure (hPa)."""
    var1 = (adc_t / 16384.0 - cal["T1"] / 1024.0) * cal["T2"]
    var2 = ((adc_t / 131072.0 - cal["T1"] / 8192.0) ** 2) * cal["T3"]
    t_fine = var1 + var2
    temp_c = t_fine / 5120.0

    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * cal["P6"] / 32768.0
    var2 += var1 * cal["P5"] * 2.0
    var2 = var2 / 4.0 + cal["P4"] * 65536.0
    var1 = (cal["P3"] * var1 * var1 / 524288.0 + cal["P2"] * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * cal["P1"]
    if var1 == 0:
        raise ZeroDivisionError("invalid BME280 pressure calibration")
    pressure_pa = 1048576.0 - adc_p
    pressure_pa = (pressure_pa - var2 / 4096.0) * 6250.0 / var1
    var1 = cal["P9"] * pressure_pa * pressure_pa / 2147483648.0
    var2 = pressure_pa * cal["P8"] / 32768.0
    pressure_pa += (var1 + var2 + cal["P7"]) / 16.0

    humidity = t_fine - 76800.0
    humidity = (
        adc_h - (cal["H4"] * 64.0 + cal["H5"] / 16384.0 * humidity)
    ) * (
        cal["H2"] / 65536.0
        * (1.0 + cal["H6"] / 67108864.0 * humidity
           * (1.0 + cal["H3"] / 67108864.0 * humidity))
    )
    humidity *= 1.0 - cal["H1"] * humidity / 524288.0
    humidity = max(0.0, min(100.0, humidity))
    return float(temp_c), float(humidity), float(pressure_pa / 100.0)


def fetch_bme280_loop(shared, stop_event):
    """Poll BME280 and publish temperature, humidity and pressure."""
    if not BME280_ENABLE:
        return
    try:
        from smbus2 import SMBus as SMBusClass  # type: ignore
    except Exception as e:
        shared["bme280_err"] = f"BME280: smbus2 not available: {type(e).__name__}: {e}"
        return

    try:
        with SMBusClass(int(BME280_I2C_BUS)) as bus:
            with I2C_LOCK:
                chip_id = int(bus.read_byte_data(BME280_ADDR, 0xD0))
                if chip_id != 0x60:
                    raise OSError(f"unexpected chip ID 0x{chip_id:02X}")
                cal1 = list(bus.read_i2c_block_data(BME280_ADDR, 0x88, 26))
                cal2 = list(bus.read_i2c_block_data(BME280_ADDR, 0xE1, 7))
                # Humidity x1, temperature/pressure x1, normal mode, 1000 ms standby.
                bus.write_byte_data(BME280_ADDR, 0xF2, 0x01)
                bus.write_byte_data(BME280_ADDR, 0xF5, 0xA0)
                bus.write_byte_data(BME280_ADDR, 0xF4, 0x27)
            cal = _bme280_parse_calibration(cal1, cal2)
            stop_event.wait(0.1)

            while not stop_event.is_set():
                try:
                    with I2C_LOCK:
                        data = list(bus.read_i2c_block_data(BME280_ADDR, 0xF7, 8))
                    if len(data) != 8:
                        raise OSError(f"returned {len(data)} bytes, expected 8")
                    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
                    adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
                    adc_h = (data[6] << 8) | data[7]
                    temp_c, hum_pct, pressure_hpa = _bme280_compensate(adc_t, adc_p, adc_h, cal)
                    shared["bme280_temp_c"] = temp_c + BME280_TEMP_OFFSET_C
                    shared["bme280_hum_pct"] = hum_pct + BME280_HUM_OFFSET_PCT
                    shared["bme280_pressure_hpa"] = pressure_hpa
                    shared["bme280_ts"] = time.time()
                    shared["bme280_err"] = ""
                except Exception as e:
                    shared["bme280_err"] = f"BME280: {type(e).__name__}: {e}"
                stop_event.wait(BME280_REFRESH_SEC)
    except Exception as e:
        shared["bme280_err"] = f"BME280: {type(e).__name__}: {e}"
