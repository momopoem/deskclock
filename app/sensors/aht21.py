# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def _aht21_read_temp_hum_via_i2c(bus_num: int = AHT21_I2C_BUS, addr: int = AHT21_ADDR):
    """Read AHT21 temperature/humidity using raw I2C transactions.

    Returns:
      (temp_c: float, hum_pct: int). Raises on communication errors.

    AHT21 commands and responses are not SMBus register operations. In
    particular, ``read_i2c_block_data(addr, 0x00, 6)`` writes a command byte
    before reading, which changes the transaction the sensor receives. Use
    I2C_RDWR messages so the bytes on the wire match the AHT21 protocol.
    """
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
        from smbus2 import i2c_msg
    except Exception as e:
        raise RuntimeError("AHT21 requires smbus2 raw I2C support") from e

    def raw_write(bus, payload):
        msg = i2c_msg.write(addr, payload)
        bus.i2c_rdwr(msg)

    def raw_read(bus, length: int):
        msg = i2c_msg.read(addr, length)
        bus.i2c_rdwr(msg)
        return list(msg)

    with _SMBus(int(bus_num)) as bus:
        # Initialise only if the calibration-enable status bit is clear.
        with I2C_LOCK:
            status_data = raw_read(bus, 1)
        if not status_data:
            raise OSError("AHT21 returned an empty status response")
        if (status_data[0] & 0x08) == 0:
            with I2C_LOCK:
                raw_write(bus, [0xBE, 0x08, 0x00])
            time.sleep(0.02)

        # Trigger measurement.
        with I2C_LOCK:
            raw_write(bus, [0xAC, 0x33, 0x00])

        # Wait for the busy status bit to clear.
        status = 0x80
        for _ in range(10):
            time.sleep(0.02)
            with I2C_LOCK:
                current_status = raw_read(bus, 1)
            if not current_status:
                raise OSError("AHT21 returned an empty busy-status response")
            status = current_status[0]
            if (status & 0x80) == 0:
                break
        else:
            raise TimeoutError("AHT21 measurement did not complete")

        with I2C_LOCK:
            data = raw_read(bus, 6)

    if len(data) != 6:
        raise OSError(f"AHT21 returned {len(data)} measurement bytes, expected 6")

    hum_raw = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
    temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

    rh = hum_raw * 100.0 / 1048576.0
    tc = temp_raw * 200.0 / 1048576.0 - 50.0
    hum_i = int(round(max(0.0, min(100.0, rh))))
    return float(tc), hum_i

def fetch_aht21_loop(shared, stop_event):
    """Poll AHT21 in a background thread.

    Writes to shared:
      - aht21_temp_c
      - aht21_hum_pct
      - aht21_ts
      - aht21_err
    """
    if not AHT21_ENABLE:
        return

    while not stop_event.is_set():
        try:
            t, h = _aht21_read_temp_hum_via_i2c(bus_num=AHT21_I2C_BUS, addr=AHT21_ADDR)
            shared["aht21_temp_c"] = float(t) + AHT21_TEMP_OFFSET_C
            shared["aht21_hum_pct"] = int(h) + AHT21_HUM_OFFSET_PCT
            shared["aht21_ts"] = time.time()
            shared["aht21_err"] = ""
        except Exception as e:
            shared["aht21_err"] = f"AHT21: {type(e).__name__}: {e}"
        stop_event.wait(AHT21_REFRESH_SEC)
