# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import argparse
import time

from smbus2 import SMBus, i2c_msg

POWER_ON = 0x01
RESET = 0x07
ONE_TIME_HIRES = 0x20


def read_lux(bus: SMBus, addr: int, measurement_time: float) -> tuple[int, float]:
    """Take one BH1750 high-resolution measurement using a raw I2C read."""
    bus.write_byte(addr, POWER_ON)
    bus.write_byte(addr, RESET)
    bus.write_byte(addr, ONE_TIME_HIRES)
    time.sleep(max(0.0, measurement_time))

    msg = i2c_msg.read(addr, 2)
    bus.i2c_rdwr(msg)
    data = list(msg)
    raw = (data[0] << 8) | data[1]
    return raw, raw / 1.2


def main() -> None:
    parser = argparse.ArgumentParser(description="Read BH1750 illuminance")
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x23)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--measurement-time", type=float, default=1.0)
    args = parser.parse_args()

    with SMBus(args.bus) as bus:
        for index in range(max(1, args.count)):
            raw, lux = read_lux(bus, args.address, args.measurement_time)
            print(f"sample={index + 1} raw=0x{raw:04x} lux={lux:.1f} lx")
            if index + 1 < args.count:
                time.sleep(max(0.0, args.interval))


if __name__ == "__main__":
    main()

