# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from smbus2 import SMBus
import time

ENS_ADDR = 0x53
AHT_ADDR = 0x38

# ENS160 registers
REG_OPMODE  = 0x10
REG_STATUS  = 0x20
REG_AQI     = 0x21
REG_TVOC    = 0x22  # 2 bytes, LSB then MSB
REG_ECO2    = 0x24  # 2 bytes, LSB then MSB
REG_TEMP_IN = 0x13  # write: (C+273.15)*64, LSB then MSB
REG_RH_IN   = 0x15  # write: RH%*512, LSB then MSB

def read_u16_lsb_msb(bus, reg):
    b = bus.read_i2c_block_data(ENS_ADDR, reg, 2)
    return b[0] | (b[1] << 8)

def aht21_read(bus):
    # Trigger measurement
    bus.write_i2c_block_data(AHT_ADDR, 0xAC, [0x33, 0x00])
    # Wait complete (bit7==0)
    for _ in range(10):
        time.sleep(0.02)
        st = bus.read_byte(AHT_ADDR)
        if (st & 0x80) == 0:
            break
    d = bus.read_i2c_block_data(AHT_ADDR, 0x00, 6)

    hum_raw  = (d[1] << 12) | (d[2] << 4) | (d[3] >> 4)
    temp_raw = ((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]

    rh = hum_raw * 100.0 / 1048576.0
    tc = temp_raw * 200.0 / 1048576.0 - 50.0
    return tc, rh

def ens160_write_comp(bus, tc, rh):
    # TEMP_IN: (C + 273.15) * 64  (write LSB then MSB)  :contentReference[oaicite:2]{index=2}
    temp_k64 = int(round((tc + 273.15) * 64.0))
    bus.write_i2c_block_data(ENS_ADDR, REG_TEMP_IN, [temp_k64 & 0xFF, (temp_k64 >> 8) & 0xFF])

    # RH_IN: RH% * 512 (write LSB then MSB)  :contentReference[oaicite:3]{index=3}
    rh_512 = int(round(rh * 512.0))
    bus.write_i2c_block_data(ENS_ADDR, REG_RH_IN, [rh_512 & 0xFF, (rh_512 >> 8) & 0xFF])

def decode_status(st):
    validity = (st >> 2) & 0x03  # :contentReference[oaicite:4]{index=4}
    newdat = (st >> 1) & 0x01
    running = (st >> 7) & 0x01
    err = (st >> 6) & 0x01
    return running, err, validity, newdat

with SMBus(1) as bus:
    # ENS160: Standard mode
    bus.write_byte_data(ENS_ADDR, REG_OPMODE, 0x02)
    time.sleep(1.0)

    # AHT21 init (harmless if already init)
    bus.write_i2c_block_data(AHT_ADDR, 0xBE, [0x08, 0x00])
    time.sleep(0.05)

    start = time.time()
    while True:
        # Update compensation from AHT21
        tc, rh = aht21_read(bus)
        ens160_write_comp(bus, tc, rh)

        st = bus.read_byte_data(ENS_ADDR, REG_STATUS)
        running, err, validity, newdat = decode_status(st)

        elapsed = int(time.time() - start)
        validity_str = ["OK", "WARMUP", "STARTUP", "INVALID"][validity]

        if err:
            print(f"t+{elapsed:3d}s  STATUS:0x{st:02X}  ERROR=1  validity={validity_str}")
            time.sleep(2)
            continue

        # VALIDITY が OK(0) になるまで “参考値扱い” にする
        aqi = bus.read_byte_data(ENS_ADDR, REG_AQI)
        tvoc = read_u16_lsb_msb(bus, REG_TVOC)
        eco2 = read_u16_lsb_msb(bus, REG_ECO2)

        note = "" if validity == 0 else " (warming up)"
        print(
            f"t+{elapsed:3d}s  STATUS:0x{st:02X}  {validity_str} new={newdat}  "
            f"T={tc:.1f}C RH={rh:.1f}%  AQI={aqi}  TVOC={tvoc}ppb  eCO2={eco2}ppm{note}"
        )

        time.sleep(2)

