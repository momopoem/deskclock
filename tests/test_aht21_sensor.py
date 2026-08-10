from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from services import sensor_service


class _Message:
    def __init__(self, *, payload=None, length=None):
        self.payload = list(payload) if payload is not None else None
        self.data = [0] * length if length is not None else None

    def __iter__(self):
        return iter(self.data)


class _I2CMessageFactory:
    @staticmethod
    def write(_addr, payload):
        return _Message(payload=payload)

    @staticmethod
    def read(_addr, length):
        return _Message(length=length)


class _FakeBus:
    def __init__(self, _bus_num, responses):
        self.responses = iter(responses)
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def i2c_rdwr(self, message):
        if message.payload is not None:
            self.writes.append(message.payload)
        else:
            message.data = list(next(self.responses))


class AHT21RawI2CTests(unittest.TestCase):
    def _install_smbus2(self, bus):
        module = types.ModuleType("smbus2")
        module.SMBus = lambda bus_num: bus
        module.i2c_msg = _I2CMessageFactory
        return patch.dict(sys.modules, {"smbus2": module})

    def test_uses_raw_reads_without_smbus_command_byte(self):
        # Calibrated, busy once, ready, then 50% RH and 25 C.
        bus = _FakeBus(1, [[0x08], [0x88], [0x08], [0x08, 0x80, 0, 0x06, 0, 0]])

        with self._install_smbus2(bus), patch.object(sensor_service.time, "sleep"):
            temp_c, humidity = sensor_service._aht21_read_temp_hum_via_i2c()

        self.assertEqual(bus.writes, [[0xAC, 0x33, 0x00]])
        self.assertAlmostEqual(temp_c, 25.0)
        self.assertEqual(humidity, 50)

    def test_initialises_only_when_calibration_bit_is_clear(self):
        bus = _FakeBus(1, [[0x00], [0x08], [0x08, 0x80, 0, 0x06, 0, 0]])

        with self._install_smbus2(bus), patch.object(sensor_service.time, "sleep"):
            sensor_service._aht21_read_temp_hum_via_i2c()

        self.assertEqual(bus.writes, [[0xBE, 0x08, 0x00], [0xAC, 0x33, 0x00]])

    def test_reports_measurement_timeout(self):
        bus = _FakeBus(1, [[0x08]] + [[0x88]] * 10)

        with self._install_smbus2(bus), patch.object(sensor_service.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, "did not complete"):
                sensor_service._aht21_read_temp_hum_via_i2c()


if __name__ == "__main__":
    unittest.main()
