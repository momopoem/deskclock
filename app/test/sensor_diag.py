"""Bounded hardware diagnostics using the application's sensor workers."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import sensor_service as sensors

# Worker name, freshness key, error key, required measurement fields.
SENSORS = {
    "bme280": ("bme280", "bme280_ts", "bme280_err", ("bme280_temp_c", "bme280_hum_pct", "bme280_pressure_hpa")),
    "scd40": ("scd40", "scd40_ts", "scd40_err", ("scd40_co2_ppm", "scd40_temp_c", "scd40_hum_pct")),
    "sht20": ("sht20", "sht20_ts", "sht20_err", ("sht20_temp_c", "sht20_hum_pct")),
    "aht21": ("aht21", "aht21_ts", "aht21_err", ("aht21_temp_c", "aht21_hum_pct")),
    "ens160": ("ens160", "ens_ts", "ens_err", ("ens_status", "ens_aqi", "ens_tvoc_ppb", "ens_eco2_ppm")),
    "bh1750": ("bh1750", "lux_mono", "lux_err", ("lux",)),
    "pir": ("pir", None, "pir_err", ("pir_value",)),
}


def validate_sample(name, state):
    fields = SENSORS[name][3]
    values = {key: state[key] for key in fields}
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values.values()):
        raise ValueError("missing or non-finite measurement")
    for key, value in values.items():
        if key.endswith("hum_pct") and not 0 <= value <= 100:
            raise ValueError(f"{key} outside 0..100: {value}")
    if name == "scd40" and values["scd40_co2_ppm"] <= 0:
        raise ValueError("SCD40 has not produced a valid CO2 sample")
    if name == "bme280" and values["bme280_pressure_hpa"] <= 0:
        raise ValueError("invalid pressure")
    if name == "bh1750" and values["lux"] < 0:
        raise ValueError("negative illuminance")
    if name == "pir" and values["pir_value"] not in (0, 1):
        raise ValueError("invalid PIR level")
    if name == "ens160":
        validity = (int(values["ens_status"]) >> 2) & 3
        if validity:
            raise ValueError(f"ENS160 validity={validity}: warming up (1/2) or invalid (3); retry later")
        if not 1 <= values["ens_aqi"] <= 5:
            raise ValueError("ENS160 AQI outside 1..5")
    return values


class SampleStop:
    """A worker-compatible event; inspect only at completed polling boundaries."""
    def __init__(self, name, state, samples, timeout, emit):
        self.name, self.state, self.samples = name, state, samples
        self.deadline = time.monotonic() + timeout
        self.emit = emit
        self.count = 0
        self.previous = None
        self.error = "no fresh measurement (check wiring, dependencies and sensor enable flag)"

    def is_set(self):
        return self.count >= self.samples or time.monotonic() >= self.deadline

    def wait(self, seconds):
        _, stamp, error, fields = SENSORS[self.name]
        token = self.state.get(stamp) if stamp else self.count
        if self.state.get(error):
            self.error = self.state[error]
        elif all(k in self.state for k in fields) and token is not None and token != self.previous:
            self.previous = token
            try:
                values = validate_sample(self.name, self.state)
            except ValueError as exc:
                self.error = str(exc)
            else:
                self.count += 1
                self.emit({"sensor": self.name, "sample": self.count, "values": values})
        if not self.is_set():
            time.sleep(max(0, min(seconds, self.deadline - time.monotonic())))
        return self.is_set()


def camera_probe(samples, device, emit):
    # VideoCapture also accepts network URLs and video files. This diagnostic
    # intentionally accepts local cameras only, so credentials cannot be sent
    # to a remote endpoint or echoed in backend errors.
    if not (device.isdecimal() or re.fullmatch(r"/dev/video[0-9]+", device)):
        raise ValueError("camera device must be a local index or /dev/videoN")
    import cv2
    capture = cv2.VideoCapture(int(device) if device.isdecimal() else device)
    try:
        if not capture.isOpened():
            raise RuntimeError("camera open failed")
        for index in range(samples):
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                raise RuntimeError("camera returned an empty frame")
            emit({"sensor": "camera", "sample": index + 1,
                  "values": {"height": int(frame.shape[0]), "width": int(frame.shape[1])}})
    finally:
        capture.release()


def probe(name, samples, timeout, device, emit):
    if name == "camera":
        camera_probe(samples, device, emit)
        return
    state = {}
    stop = SampleStop(name, state, samples, timeout, emit)
    getattr(sensors, f"fetch_{SENSORS[name][0]}_loop")(state, stop)
    if stop.count < samples:
        raise RuntimeError(state.get(SENSORS[name][2]) or stop.error)


def main(default_sensor=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensor", choices=[*SENSORS, "camera", "all"], default=default_sensor or "all")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20, help="seconds per sensor")
    parser.add_argument("--device", default="0", help="camera index or device path")
    parser.add_argument("--output", type=Path, help="write aggregate JSON report")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("samples and timeout must be positive")
    if args.worker:
        try:
            probe(args.sensor, args.samples, args.timeout, args.device,
                  lambda row: print(json.dumps(row, ensure_ascii=False), flush=True))
            return 0
        except Exception as exc:
            print(json.dumps({"sensor": args.sensor, "error": str(exc)}, ensure_ascii=False), flush=True)
            return 1
    names = [*SENSORS, "camera"] if args.sensor == "all" else [args.sensor]
    results = []
    try:
        for name in names:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--sensor", name,
                       "--samples", str(args.samples), "--timeout", str(args.timeout), "--device", args.device]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout + 2)
                rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
                row = {"sensor": name, "passed": result.returncode == 0, "measurements": rows}
                if result.stderr:
                    row["stderr"] = result.stderr.strip()
            except subprocess.TimeoutExpired:
                row = {"sensor": name, "passed": False, "error": "hardware communication timed out"}
            except (OSError, ValueError) as exc:
                row = {"sensor": name, "passed": False, "error": str(exc)}
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        return 130
    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
