"""Hardware-free regression tests for every local sensor worker."""
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "test"))
from services import sensor_service as s
import sensor_diag as diag


class Stop:
    def __init__(self, polls=1, startup=0):
        self.remaining = polls + startup

    def is_set(self):
        return self.remaining <= 0

    def wait(self, seconds):
        self.remaining -= 1
        return self.is_set()


class Message:
    def __init__(self, address, data, read=False):
        self.address, self.data, self.reading = address, list(data), read

    def __iter__(self):
        return iter(self.data)


class Factory:
    @staticmethod
    def read(address, length):
        return Message(address, [0] * length, True)

    @staticmethod
    def write(address, data):
        return Message(address, data)


class PhysicalSensorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.bus = MagicMock()
        self.bus.__enter__.return_value = self.bus
        self.module = types.ModuleType("smbus2")
        self.module.SMBus = MagicMock(return_value=self.bus)
        self.module.i2c_msg = Factory
        self.stack.enter_context(patch.dict(sys.modules, {"smbus2": self.module}))
        self.stack.enter_context(patch.object(s.time, "sleep"))
        for name in ("AHT21", "BH1750", "BME280", "SCD40", "ENS160", "PIR"):
            self.stack.enter_context(patch.object(s, name + "_ENABLE", True))

    def raw(self, responses):
        responses = iter(responses)
        def transfer(msg):
            if msg.reading:
                value = next(responses)
                if isinstance(value, Exception):
                    raise value
                msg.data = value
        self.bus.i2c_rdwr.side_effect = transfer

    def test_bh1750_raw_conversion_and_close(self):
        self.raw([[0x01, 0x20]])
        state = {}
        s.fetch_bh1750_loop(state, Stop())
        self.assertEqual(state["lux"], 240)
        self.assertEqual(state["lux_err"], "")
        self.bus.read_i2c_block_data.assert_not_called()
        self.assertEqual([c.args for c in self.bus.write_byte.call_args_list],
                         [(s.BH1750_ADDR, 1), (s.BH1750_ADDR, 0x10)])
        self.bus.__exit__.assert_called_once()

    def test_bh1750_failure_keeps_previous_sample(self):
        self.bus.write_byte.side_effect = OSError("disconnected")
        state = {"lux": 40, "lux_mono": 7}
        s.fetch_bh1750_loop(state, Stop())
        self.assertEqual(state["lux_mono"], 7)
        self.assertEqual(state["lux"], 40)
        self.assertIn("disconnected", state["lux_err"])

    def test_sht20_busy_retry_conversion_and_close(self):
        self.raw([OSError("busy"), [0x68, 0x3B, 0], [0x80, 0x03, 0]])
        temp, hum = s.read_sht20_indoor()
        self.assertAlmostEqual(temp, -46.85 + 175.72 * 0x6838 / 65536)
        self.assertEqual(hum, 56)
        self.assertEqual([c.args[1] for c in self.bus.write_byte.call_args_list], [0xF3, 0xF5])
        self.bus.__exit__.assert_called_once()

    def test_sht20_exhausted_retries_returns_no_sample(self):
        self.raw([OSError("busy")] * 10)
        self.assertEqual(s.read_sht20_indoor(), (None, None))
        self.assertEqual(self.bus.i2c_rdwr.call_count, 10)

    def test_sht20_offsets_and_existing_indoor_source(self):
        state = {"in_temp_c": 10, "in_hum_pct": 20}
        with patch.object(s, "read_sht20_indoor", return_value=(25, 50)):
            s.fetch_sht20_loop(state, Stop())
        self.assertEqual(state["sht20_temp_c"], 25 + s.SHT20_TEMP_OFFSET_C)
        self.assertEqual(state["in_temp_c"], 10)
        self.assertEqual(state["in_hum_pct"], 20)
        timestamp = state["sht20_ts"]
        with patch.object(s, "read_sht20_indoor", return_value=(None, None)):
            s.fetch_sht20_loop(state, Stop())
        self.assertEqual(state["sht20_ts"], timestamp)

    def test_aht21_failure_then_recovery(self):
        state = {"aht21_ts": 1}
        with patch.object(s, "_aht21_read_temp_hum_via_i2c", side_effect=[OSError("unplugged"), (25, 50)]):
            s.fetch_aht21_loop(state, Stop())
            self.assertIn("unplugged", state["aht21_err"])
            self.assertEqual(state["aht21_ts"], 1)
            s.fetch_aht21_loop(state, Stop())
        self.assertEqual(state["aht21_err"], "")
        self.assertEqual(state["aht21_temp_c"], 25)

    def test_bme280_signed_calibration_and_invalid_length(self):
        cal = s._bme280_parse_calibration([255] * 26, [255] * 7)
        self.assertEqual(cal["T1"], 65535)
        for key in ("T2", "P2", "H2", "H4", "H5", "H6"):
            self.assertEqual(cal[key], -1)
        with self.assertRaises(ValueError):
            s._bme280_parse_calibration([], [])

    def test_bme280_worker_decodes_adc_and_applies_offset(self):
        self.bus.read_byte_data.return_value = 0x60
        self.bus.read_i2c_block_data.side_effect = [[0] * 26, [0] * 7, [0x65, 0x5A, 0xC0, 0x7E, 0xED, 0, 0x75, 0x30]]
        state = {}
        with patch.object(s, "_bme280_compensate", return_value=(25, 50, 1000)) as convert:
            s.fetch_bme280_loop(state, Stop(startup=1))
        self.assertEqual(convert.call_args.args[:3], (519888, 415148, 30000))
        self.assertEqual(state["bme280_temp_c"], 25 + s.BME280_TEMP_OFFSET_C)
        self.assertEqual(state["bme280_pressure_hpa"], 1000)
        self.assertEqual(state["bme280_err"], "")
        self.bus.__exit__.assert_called_once()

    def test_bme280_wrong_chip_rejected(self):
        self.bus.read_byte_data.return_value = 0x58
        state = {}
        s.fetch_bme280_loop(state, Stop())
        self.assertIn("chip ID", state["bme280_err"])
        self.assertNotIn("bme280_ts", state)
        self.bus.write_byte_data.assert_not_called()

    def test_scd40_known_crc_and_short_payload(self):
        self.assertEqual(s._scd40_crc8([0xBE, 0xEF]), 0x92)
        for size in (0, 8, 10):
            with self.assertRaises(ValueError):
                s._scd40_parse_measurement([0] * size)

    def test_scd40_commands_and_crc_failure_preserve_values(self):
        self.raw([[0] * 9])
        state = {"scd40_co2_ppm": 500, "scd40_ts": 10}
        s.fetch_scd40_loop(state, Stop(startup=2))
        commands = [c.args[0].data for c in self.bus.i2c_rdwr.call_args_list if not c.args[0].reading]
        self.assertEqual(commands, [[0x3F, 0x86], [0x21, 0xB1], [0xEC, 0x05]])
        self.assertIn("CRC", state["scd40_err"])
        self.assertEqual(state["scd40_co2_ppm"], 500)
        self.assertEqual(state["scd40_ts"], 10)
        self.bus.__exit__.assert_called_once()

    def test_scd40_valid_sample_published(self):
        payload = []
        for pair in ([1, 244], [0x66, 0x66], [0x80, 0]):
            payload.extend([*pair, s._scd40_crc8(pair)])
        self.raw([payload])
        state = {}
        s.fetch_scd40_loop(state, Stop(startup=2))
        self.assertEqual(state["scd40_co2_ppm"], 500)
        self.assertAlmostEqual(state["scd40_temp_c"], 25)
        self.assertAlmostEqual(state["scd40_hum_pct"], 50, places=2)
        self.assertEqual(state["scd40_err"], "")

    def test_ens160_little_endian_and_fresh_compensation(self):
        self.bus.read_byte_data.side_effect = [0x02, 2]
        self.bus.read_i2c_block_data.side_effect = [[0x34, 0x12], [0x78, 0x56]]
        state = {"bme280_ts": s.time.time(), "bme280_temp_c": 25, "bme280_hum_pct": 50}
        s.fetch_ens160_loop(state, Stop())
        self.assertEqual(state["ens_tvoc_ppb"], 0x1234)
        self.assertEqual(state["ens_eco2_ppm"], 0x5678)
        self.assertEqual(state["ens_err"], "")
        temp = round((25 + 273.15) * 64)
        self.assertEqual([c.args for c in self.bus.write_i2c_block_data.call_args_list],
                         [(s.ENS160_ADDR, 0x13, [temp & 255, temp >> 8]), (s.ENS160_ADDR, 0x15, [0, 100])])

    def test_ens160_stale_compensation_omitted_and_error_reported(self):
        self.bus.read_byte_data.side_effect = OSError("disconnected")
        state = {"bme280_ts": 0, "bme280_temp_c": 25, "bme280_hum_pct": 50, "ens_ts": 1}
        s.fetch_ens160_loop(state, Stop())
        self.bus.write_i2c_block_data.assert_not_called()
        self.assertIn("disconnected", state["ens_err"])
        self.assertEqual(state["ens_ts"], 1)

    def test_pir_active_inactive_and_cli_failure(self):
        state = {}
        with patch("subprocess.check_output", return_value='"17"=active') as cli:
            s.fetch_pir_loop(state, Stop())
        self.assertEqual(state["pir_value"], 1)
        self.assertEqual(state["activity_mono"], state["pir_mono"])
        self.assertEqual(cli.call_args.args[0][-1], str(s.PIR_LINE))
        stamp = state["pir_mono"]
        with patch("subprocess.check_output", return_value='"17"=inactive'):
            s.fetch_pir_loop(state, Stop())
        self.assertEqual(state["pir_value"], 0)
        self.assertEqual(state["pir_mono"], stamp)
        with patch("subprocess.check_output", side_effect=OSError("missing gpioget")):
            s.fetch_pir_loop(state, Stop())
        self.assertIn("missing gpioget", state["pir_err"])

    def test_disabled_workers_do_not_open_hardware(self):
        for name in ("aht21", "bh1750", "bme280", "scd40", "ens160", "pir"):
            with self.subTest(sensor=name), patch.object(s, name.upper() + "_ENABLE", False):
                state = {}
                getattr(s, f"fetch_{name}_loop")(state, Stop())
                self.assertEqual(state, {})
        self.module.SMBus.assert_not_called()


class DiagnosticTests(unittest.TestCase):
    def test_camera_rejects_network_urls_and_files_before_opening(self):
        cv = types.ModuleType("cv2")
        cv.VideoCapture = MagicMock()
        for device in ("https://example.invalid/stream", "rtsp://example.invalid/camera", "recording.mp4"):
            with self.subTest(device=device), patch.dict(sys.modules, {"cv2": cv}):
                with self.assertRaisesRegex(ValueError, "local index"):
                    diag.camera_probe(1, device, lambda row: None)
        cv.VideoCapture.assert_not_called()

    def test_all_diagnostics_continue_after_timeout(self):
        import subprocess
        result = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        outcomes = [subprocess.TimeoutExpired("probe", 1)] + [result] * 7
        with patch.object(sys, "argv", ["sensor_diag.py", "--sensor", "all"]), \
             patch.object(diag.subprocess, "run", side_effect=outcomes) as run, \
             patch("builtins.print"):
            self.assertEqual(diag.main(), 1)
        self.assertEqual(run.call_count, 8)
        self.assertTrue(all(call.kwargs["timeout"] == 22 for call in run.call_args_list))

    def test_individual_diagnostic_propagates_failure(self):
        result = types.SimpleNamespace(returncode=1, stdout='{"error": "disconnected"}\n', stderr="")
        with patch.object(sys, "argv", ["bme280_test.py"]), \
             patch.object(diag.subprocess, "run", return_value=result) as run, \
             patch("builtins.print"):
            self.assertEqual(diag.main("bme280"), 1)
        self.assertIn("bme280", run.call_args.args[0])

    def test_camera_success_and_failures_release_capture(self):
        for opened, ok in ((True, True), (False, False), (True, False)):
            with self.subTest(opened=opened, ok=ok):
                cv = types.ModuleType("cv2")
                capture = MagicMock()
                capture.isOpened.return_value = opened
                capture.read.return_value = (ok, types.SimpleNamespace(size=12, shape=(2, 2, 3)))
                cv.VideoCapture = MagicMock(return_value=capture)
                rows = []
                with patch.dict(sys.modules, {"cv2": cv}):
                    if opened and ok:
                        diag.camera_probe(2, "0", rows.append)
                        self.assertEqual(len(rows), 2)
                        self.assertEqual(rows[0]["values"], {"height": 2, "width": 2})
                    else:
                        with self.assertRaises(RuntimeError):
                            diag.camera_probe(1, "0", rows.append)
                capture.release.assert_called_once()

    def test_diagnostic_rejects_stale_and_invalid_samples(self):
        state = {"lux": 0, "lux_mono": 1}
        rows = []
        stop = diag.SampleStop("bh1750", state, 2, 10, rows.append)
        stop.wait(0)
        stop.wait(0)
        self.assertEqual(stop.count, 1)
        state.update(lux=float("nan"), lux_mono=2)
        stop.wait(0)
        self.assertEqual(stop.count, 1)
        state.update(lux=50, lux_mono=3)
        self.assertTrue(stop.wait(0))

    def test_ens160_warmup_not_reported_as_pass(self):
        for status in (4, 8, 12):
            with self.assertRaisesRegex(ValueError, "validity"):
                diag.validate_sample("ens160", dict(ens_status=status, ens_aqi=2, ens_tvoc_ppb=10, ens_eco2_ppm=400))

    def test_missing_sht20_measurement_fails(self):
        with patch.object(s, "fetch_sht20_loop"):
            with self.assertRaisesRegex(RuntimeError, "no fresh"):
                diag.probe("sht20", 1, 1, "0", lambda row: None)


if __name__ == "__main__":
    unittest.main()
