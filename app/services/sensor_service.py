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



# -----------------------------------------------------------------------------
# Sensor: SR501 PIR
# -----------------------------------------------------------------------------

def fetch_pir_loop(shared, stop_event):
    """Poll SR501 PIR via gpioget CLI (robust across gpiod variants).
    Updates:
      - pir_value (0/1 current)
      - pir_mono (last motion time)
    """
    if not PIR_ENABLE:
        return

    import subprocess, time, os

    chip = PIR_GPIOCHIP
    if isinstance(chip, str) and chip.startswith("/dev/"):
        chip = os.path.basename(chip)

    def read_cli():
        out = subprocess.check_output(
            ["gpioget", "-c", str(chip), str(PIR_LINE)],
            text=True,
            timeout=0.8,
            stderr=subprocess.STDOUT,
        ).strip()
        if "inactive" in out:
            return 0
        if "active" in out:
            return 1
        for ch in out:
            if ch in "01":
                return int(ch)
        raise ValueError(out)

    while not stop_event.is_set():
        try:
            v = int(read_cli())
            shared["pir_value"] = v
            if v == 1:
                nowm = time.monotonic()
                shared["pir_mono"] = nowm
                shared["activity_mono"] = nowm
            shared["pir_err"] = ""
        except Exception as e:
            shared["pir_err"] = f"PIR(gpioget): {e}"
        stop_event.wait(0.2)

# --- Display Power Manager helpers ---



# -----------------------------------------------------------------------------
# Sensor: SHT20 (indoor)
# -----------------------------------------------------------------------------

def _sht20_read_temp_hum_via_i2c(bus_num: int = 1, addr: int = SHT20_I2C_ADDR):
    """Read SHT20 temperature/humidity via SMBus, ensuring the I2C FD is closed.

    Returns:
      (temp_c: float, hum_pct: int) or (None, None) on error.
    """
    # Try smbus2 first, then smbus
    SMBusClass = None
    try:
        from smbus2 import SMBus as _SMBus  # type: ignore
        SMBusClass = _SMBus
    except Exception:
        try:
            from smbus import SMBus as _SMBus  # type: ignore
            SMBusClass = _SMBus
        except Exception:
            SMBusClass = None

    if SMBusClass is None:
        return None, None

    # SHT20 commands (no-hold master mode)
    CMD_TEMP = 0xF3
    CMD_HUM  = 0xF5

    try:
        with SMBusClass(int(bus_num)) as bus:
            # Serialize access: BH1750 thread may keep a bus open; concurrent ioctls can cause EIO.
            with I2C_LOCK:
                # Temperature (no-hold master mode)
                bus.write_byte(addr, CMD_TEMP)

            # Wait for conversion; then read 2 bytes + CRC using raw I2C read (not SMBus block read).
            tdat = None
            for _ in range(10):
                time.sleep(0.02)
                try:
                    with I2C_LOCK:
                        if hasattr(bus, "i2c_rdwr"):
                            from smbus2 import i2c_msg  # type: ignore
                            msg = i2c_msg.read(addr, 3)
                            bus.i2c_rdwr(msg)
                            tdat = list(msg)
                        else:
                            # Fallback: some SMBus implementations only support SMBus block read.
                            tdat = bus.read_i2c_block_data(addr, 0x00, 3)
                    break
                except OSError:
                    # Sensor may still be busy -> retry
                    continue
            if not tdat or len(tdat) < 2:
                return None, None
            traw = ((tdat[0] << 8) | tdat[1]) & 0xFFFC

            # Humidity
            with I2C_LOCK:
                bus.write_byte(addr, CMD_HUM)

            hdat = None
            for _ in range(10):
                time.sleep(0.02)
                try:
                    with I2C_LOCK:
                        if hasattr(bus, "i2c_rdwr"):
                            from smbus2 import i2c_msg  # type: ignore
                            msg = i2c_msg.read(addr, 3)
                            bus.i2c_rdwr(msg)
                            hdat = list(msg)
                        else:
                            hdat = bus.read_i2c_block_data(addr, 0x00, 3)
                    break
                except OSError:
                    continue
            if not hdat or len(hdat) < 2:
                return None, None
            hraw = ((hdat[0] << 8) | hdat[1]) & 0xFFFC

        temp_c = -46.85 + (175.72 * traw / 65536.0)
        hum = -6.0 + (125.0 * hraw / 65536.0)
        # Clamp humidity to 0..100, round to int
        hum_i = int(round(max(0.0, min(100.0, hum))))
        return float(temp_c), hum_i
    except Exception:
        return None, None

def read_sht20_indoor(bus: int = 1):
    # Use direct I2C read to avoid FD leaks in third-party libs.
    return _sht20_read_temp_hum_via_i2c(bus_num=bus, addr=SHT20_I2C_ADDR)


# =========================
# SwitchBot Cloud API (Outdoor/Indoor via env vars)
# =========================
SWITCHBOT_REFRESH_SEC = 60

def fetch_sht20_loop(shared, stop_event):
    """Poll SHT20 on I2C in a background thread.

    This prevents blocking the main render loop (time/seconds update priority).
    Writes to:
      - sht20_temp_c
      - sht20_hum_pct
      - sht20_ts
    """
    while not stop_event.is_set():
        try:
            t_sht, h_sht = read_sht20_indoor(bus=1)
            if t_sht is not None and h_sht is not None:
                shared["sht20_temp_c"] = float(t_sht) + SHT20_TEMP_OFFSET_C
                shared["sht20_hum_pct"] = int(h_sht) + SHT20_HUM_OFFSET_PCT
                shared["sht20_ts"] = time.time()  # last good SHT20 sample
                # Fallback mirror for UI paths that expect in_temp_c/in_hum_pct (do not override SwitchBot indoor)
                if shared.get("in_temp_c") is None:
                    shared["in_temp_c"] = shared.get("sht20_temp_c")
                if shared.get("in_hum_pct") is None:
                    shared["in_hum_pct"] = shared.get("sht20_hum_pct")
                shared["sht20_err"] = ""
                # (moved) shared["sht20_ts"] is used instead
        except Exception:
            # keep last good values; no hard fail
            pass

        stop_event.wait(SHT20_REFRESH_SEC)


# =========================
# AHT21 (optional fallback sensor)
# =========================



# -----------------------------------------------------------------------------
# Sensor: AHT21 (indoor)
# -----------------------------------------------------------------------------

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
            shared["aht21_temp_c"] = float(t)
            shared["aht21_hum_pct"] = int(h)
            shared["aht21_ts"] = time.time()
            shared["aht21_err"] = ""
        except Exception as e:
            shared["aht21_err"] = f"AHT21: {type(e).__name__}: {e}"
        stop_event.wait(AHT21_REFRESH_SEC)


# =========================
# BME280 (temperature / humidity / pressure)
# =========================

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
                    shared["bme280_hum_pct"] = hum_pct
                    shared["bme280_pressure_hpa"] = pressure_hpa
                    shared["bme280_ts"] = time.time()
                    shared["bme280_err"] = ""
                except Exception as e:
                    shared["bme280_err"] = f"BME280: {type(e).__name__}: {e}"
                stop_event.wait(BME280_REFRESH_SEC)
    except Exception as e:
        shared["bme280_err"] = f"BME280: {type(e).__name__}: {e}"


# =========================
# SCD40 (true CO2 sensor)
# =========================

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


# =========================
# ENS160 (Air Quality Sensor)
# =========================



# -----------------------------------------------------------------------------
# Sensor: ENS160
# -----------------------------------------------------------------------------

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



# =========================
# Touch-toggle source selectors
# =========================
