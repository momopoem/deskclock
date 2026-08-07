# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from smbus2 import SMBus
import time

ADDR = 0x38

def read_aht21(bus: SMBus):
    # Trigger measurement
    bus.write_i2c_block_data(ADDR, 0xAC, [0x33, 0x00])

    # Wait until measurement complete (bit7 == 0)
    for _ in range(10):
        time.sleep(0.02)
        st = bus.read_byte(ADDR)
        if (st & 0x80) == 0:
            break

    data = bus.read_i2c_block_data(ADDR, 0x00, 6)

    hum_raw  = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
    temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

    humidity = hum_raw * 100.0 / 1048576.0
    temperature = temp_raw * 200.0 / 1048576.0 - 50.0

    return temperature, humidity

with SMBus(1) as bus:
    # Init (harmless if already initialized)
    bus.write_i2c_block_data(ADDR, 0xBE, [0x08, 0x00])
    time.sleep(0.05)

    # Warm-up reads (discard)
    for _ in range(2):
        try:
            read_aht21(bus)
        except Exception:
            pass
        time.sleep(0.1)

    while True:
        t, h = read_aht21(bus)
        print(f"Temp: {t:.1f}°C  Hum: {h:.1f}%")
        time.sleep(2)

