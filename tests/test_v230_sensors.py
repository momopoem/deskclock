from __future__ import annotations

import pytest

from services.sensor_service import (
    _bme280_compensate,
    _scd40_crc8,
    _scd40_parse_measurement,
)


def test_bme280_datasheet_temperature_and_pressure_example():
    cal = {
        "T1": 27504, "T2": 26435, "T3": -1000,
        "P1": 36477, "P2": -10685, "P3": 3024,
        "P4": 2855, "P5": 140, "P6": -7,
        "P7": 15500, "P8": -14600, "P9": 6000,
        "H1": 75, "H2": 362, "H3": 0,
        "H4": 315, "H5": 50, "H6": 30,
    }
    temp_c, humidity, pressure_hpa = _bme280_compensate(519888, 415148, 30000, cal)
    assert temp_c == pytest.approx(25.08, abs=0.02)
    assert pressure_hpa == pytest.approx(1006.53, abs=0.02)
    assert 0.0 <= humidity <= 100.0


def test_scd40_crc_and_measurement_conversion():
    words = [500, int((25.0 + 45.0) * 65535 / 175), int(50.0 * 65535 / 100)]
    payload = []
    for word in words:
        pair = [word >> 8, word & 0xFF]
        payload.extend(pair + [_scd40_crc8(pair)])

    co2, temp_c, humidity = _scd40_parse_measurement(payload)
    assert co2 == 500
    assert temp_c == pytest.approx(25.0, abs=0.01)
    assert humidity == pytest.approx(50.0, abs=0.01)


def test_scd40_crc_failure_is_rejected():
    with pytest.raises(ValueError, match="CRC mismatch"):
        _scd40_parse_measurement([0x01, 0xF4, 0x00] * 3)
