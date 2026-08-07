# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import smbus
import time

BUS = 1
ADDR = 0x23

POWER_ON = 0x01
RESET = 0x07
CONT_HIRES = 0x10  # 1lx res

bus = smbus.SMBus(BUS)

bus.write_byte(ADDR, POWER_ON)
bus.write_byte(ADDR, RESET)
bus.write_byte(ADDR, CONT_HIRES)
time.sleep(0.18)

print("BH1750 loop: Ctrl+C to stop")
try:
    while True:
        data = bus.read_i2c_block_data(ADDR, 0x00, 2)
        raw = (data[0] << 8) | data[1]
        lux = raw / 1.2
        print(f"{time.strftime('%H:%M:%S')}  {lux:8.1f} lx")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass

