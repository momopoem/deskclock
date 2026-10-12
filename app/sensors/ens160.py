# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def fetch_ens160_loop(shared, stop_event):
    """Poll ENS160 in a background thread.

    Writes to shared:
      - ens_status
      - ens_aqi
      - ens_tvoc_ppb
      - ens_eco2_ppm
      - ens_ts
      - ens_err

    Compensation:
      - Use fresh BME280 temperature and humidity values.
    """
    if not ENS160_ENABLE:
        return

    SMBusClass = None
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
        SMBusClass = _SMBus
    except Exception:
        try:
            from smbus import SMBus as _SMBus  # type: ignore
            SMBusClass = _SMBus
        except Exception as e:
            shared["ens_err"] = f"ENS160: SMBus not available: {type(e).__name__}: {e}"
            return

    # ENS160 registers
    REG_OPMODE = 0x10
    REG_STATUS = 0x20
    REG_AQI = 0x21
    REG_TVOC = 0x22
    REG_ECO2 = 0x24
    REG_TEMP_IN = 0x13  # (C + 273.15) * 64, LSB then MSB
    REG_RH_IN = 0x15    # RH% * 512, LSB then MSB

    def read_u16_lsb_msb(bus, reg: int) -> int:
        d = bus.read_i2c_block_data(ENS160_ADDR, reg, 2)
        return int(d[0] | (d[1] << 8))

    def write_comp(bus, tc: float, rh: float):
        temp_k64 = int(round((tc + 273.15) * 64.0))
        rh_512 = int(round(rh * 512.0))
        bus.write_i2c_block_data(ENS160_ADDR, REG_TEMP_IN, [temp_k64 & 0xFF, (temp_k64 >> 8) & 0xFF])
        bus.write_i2c_block_data(ENS160_ADDR, REG_RH_IN, [rh_512 & 0xFF, (rh_512 >> 8) & 0xFF])

    try:
        with SMBusClass(int(ENS160_I2C_BUS)) as bus:
            # Standard mode
            with I2C_LOCK:
                bus.write_byte_data(ENS160_ADDR, REG_OPMODE, 0x02)
            time.sleep(1.0)

            while not stop_event.is_set():
                try:
                    now_ts = time.time()

                    # ---- Pick compensation source (BME280) ----
                    tc = rh = None

                    bme_ts = shared.get("bme280_ts")
                    if isinstance(bme_ts, (int, float)) and (now_ts - float(bme_ts) <= float(ENS160_COMP_STALE_SEC)):
                        bme_t = shared.get("bme280_temp_c")
                        bme_h = shared.get("bme280_hum_pct")
                        if bme_t is not None and bme_h is not None:
                            tc = float(bme_t)
                            rh = float(bme_h)

                    # ---- Write compensation (if fresh) ----
                    if tc is not None and rh is not None:
                        with I2C_LOCK:
                            write_comp(bus, tc, rh)

                    # ---- Read values ----
                    with I2C_LOCK:
                        st = int(bus.read_byte_data(ENS160_ADDR, REG_STATUS))
                        aqi = int(bus.read_byte_data(ENS160_ADDR, REG_AQI))
                        tvoc = int(read_u16_lsb_msb(bus, REG_TVOC))
                        eco2 = int(read_u16_lsb_msb(bus, REG_ECO2))

                    shared["ens_status"] = st
                    shared["ens_aqi"] = aqi
                    shared["ens_tvoc_ppb"] = tvoc
                    shared["ens_eco2_ppm"] = eco2
                    shared["ens_ts"] = time.time()
                    shared["ens_err"] = ""

                except Exception as e:
                    shared["ens_err"] = f"ENS160: {type(e).__name__}: {e}"

                stop_event.wait(ENS160_REFRESH_SEC)
    except Exception as e:
        shared["ens_err"] = f"ENS160: {type(e).__name__}: {e}"
