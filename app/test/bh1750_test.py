# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import smbus
import time

BUS = 1
ADDR = 0x23

POWER_ON = 0x01
RESET = 0x07
CONT_HIRES = 0x10

bus = smbus.SMBus(BUS)

bus.write_byte(ADDR, POWER_ON)
bus.write_byte(ADDR, RESET)
bus.write_byte(ADDR, CONT_HIRES)
time.sleep(0.18)

data = bus.read_i2c_block_data(ADDR, 0x00, 2)
raw = (data[0] << 8) | data[1]
lux = raw / 1.2

print(f"{lux:.1f} lx")

