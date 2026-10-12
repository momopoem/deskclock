# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def _bh1750_read_lux(bus, addr: int) -> float:
    """Read lux from BH1750 (continuous H-resolution mode).

    Returns:
      float lux (>=0). Raises on error.
    """
    # Power on + continuous H-Resolution mode (1 lx resolution, typical)
    bus.write_byte(addr, 0x01)  # power on
    bus.write_byte(addr, 0x10)  # continuous H-resolution mode
    # This module requires a longer conversion time than the BH1750 typical
    # value.  A one-second wait is reliable on the deployed RB5 hardware.
    time.sleep(1.0)
    # BH1750 is not register-based.  read_i2c_block_data() writes its
    # "command" argument before reading; passing 0x00 therefore sends the
    # BH1750 POWER_DOWN command and can make every sample read as zero.
    # Use a raw two-byte I2C read instead.
    from smbus2 import i2c_msg

    msg = i2c_msg.read(addr, 2)
    bus.i2c_rdwr(msg)
    data = list(msg)
    raw = (data[0] << 8) | data[1]
    lux = raw / 1.2
    if lux < 0:
        lux = 0.0
    return float(lux)

def fetch_bh1750_loop(shared, stop_event):
    """Poll BH1750 lux and write to shared:
      - lux (float)
      - lux_mono (monotonic timestamp)
      - lux_err (string)

    Resource-safety:
      - Open the I2C bus once per thread using a context manager so it is closed on exit.
    """
    if not BH1750_ENABLE:
        return

    # Raw I2C reads are required for BH1750 (it has no register address).
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
        SMBusClass = _SMBus
    except Exception as e:
        shared["lux_err"] = f"BH1750: smbus2 not available: {type(e).__name__}: {e}"
        return

    try:
        with SMBusClass(BH1750_I2C_BUS) as bus:
            while not stop_event.is_set():
                try:
                    with I2C_LOCK:
                        lux = _bh1750_read_lux(bus, BH1750_ADDR)
                    shared["lux"] = lux
                    shared["lux_mono"] = time.monotonic()
                    shared["lux_err"] = ""
                except Exception as e:
                    shared["lux_err"] = f"BH1750: {type(e).__name__}: {e}"

                stop_event.wait(BH1750_POLL_SEC)
    except Exception as e:
        shared["lux_err"] = f"BH1750: {type(e).__name__}: {e}"
