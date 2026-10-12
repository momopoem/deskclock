"""Compatibility exports for the former monolithic sensor worker module.

New production code imports workers from :mod:`sensors`. Keeping this thin
module avoids breaking existing diagnostics and third-party local scripts.
"""
from __future__ import annotations

import time

from config import *
from sensors import aht21, bh1750, bme280, ens160, pir, scd40, sht20


def _sync_legacy_settings(module) -> None:
    """Preserve monkey-patchable legacy configuration for diagnostic callers."""
    module.time = time
    for name, value in globals().items():
        if name.isupper():
            setattr(module, name, value)


_bh1750_read_lux = bh1750._bh1750_read_lux
_sht20_read_temp_hum_via_i2c = sht20._sht20_read_temp_hum_via_i2c
read_sht20_indoor = sht20.read_sht20_indoor
_aht21_read_temp_hum_via_i2c = aht21._aht21_read_temp_hum_via_i2c
_bme280_parse_calibration = bme280._bme280_parse_calibration
_bme280_compensate = bme280._bme280_compensate
_scd40_crc8 = scd40._scd40_crc8
_scd40_parse_measurement = scd40._scd40_parse_measurement


def fetch_bh1750_loop(shared, stop_event):
    _sync_legacy_settings(bh1750)
    return bh1750.fetch_bh1750_loop(shared, stop_event)


def fetch_pir_loop(shared, stop_event):
    _sync_legacy_settings(pir)
    return pir.fetch_pir_loop(shared, stop_event)


def fetch_sht20_loop(shared, stop_event):
    _sync_legacy_settings(sht20)
    sht20.read_sht20_indoor = globals()["read_sht20_indoor"]
    return sht20.fetch_sht20_loop(shared, stop_event)


def fetch_aht21_loop(shared, stop_event):
    _sync_legacy_settings(aht21)
    aht21._aht21_read_temp_hum_via_i2c = globals()["_aht21_read_temp_hum_via_i2c"]
    return aht21.fetch_aht21_loop(shared, stop_event)


def fetch_bme280_loop(shared, stop_event):
    _sync_legacy_settings(bme280)
    bme280._bme280_compensate = globals()["_bme280_compensate"]
    return bme280.fetch_bme280_loop(shared, stop_event)


def fetch_scd40_loop(shared, stop_event):
    _sync_legacy_settings(scd40)
    return scd40.fetch_scd40_loop(shared, stop_event)


def fetch_ens160_loop(shared, stop_event):
    _sync_legacy_settings(ens160)
    return ens160.fetch_ens160_loop(shared, stop_event)
