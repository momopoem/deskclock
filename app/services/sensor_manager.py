# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import requests

from config import *
from services.sensor_service import (
    fetch_aht21_loop,
    fetch_bh1750_loop,
    fetch_ens160_loop,
    fetch_pir_loop,
    fetch_sht20_loop,
)
from services.weather_service import (
    fetch_internet_loop,
    fetch_switchbot_indoor,
    fetch_switchbot_outdoor,
    fetch_weather_loop,
    fetch_weathercode_only_loop,
)


@dataclass
class SensorWorker:
    name: str
    target: Callable
    args: tuple
    thread: threading.Thread | None = None


class SensorManager:
    """Central manager for background sensor/API worker threads.

    Step 3 goal:
    - centralize worker registration/startup
    - keep existing worker loop behavior unchanged
    - provide a single place for future lifecycle/restart policies
    """

    def __init__(self, *, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self._workers: list[SensorWorker] = []

    def add_worker(self, name: str, target: Callable, *args) -> None:
        self._workers.append(SensorWorker(name=name, target=target, args=args))

    def start_all(self) -> None:
        for wk in self._workers:
            if wk.thread and wk.thread.is_alive():
                continue
            t = threading.Thread(target=wk.target, args=wk.args, daemon=True, name=wk.name)
            wk.thread = t
            t.start()

    def list_alive(self) -> list[str]:
        return [wk.name for wk in self._workers if wk.thread and wk.thread.is_alive()]

    def stop_all(self) -> None:
        self.stop_event.set()


def _prime_open_meteo(state) -> None:
    """One-shot Open-Meteo fetch used when SwitchBot outdoor data is not configured."""
    try:
        url0 = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&timezone={TIMEZONE}"
            "&current=temperature_2m,relative_humidity_2m,weather_code"
        )
        r0 = requests.get(url0, timeout=8, headers={"User-Agent": "deskclock/1.0"})
        try:
            r0.raise_for_status()
            cur0 = r0.json().get("current", {})
        finally:
            try:
                r0.close()
            except Exception:
                pass
        state.out_temp_c = float(cur0["temperature_2m"])
        state.out_hum_pct = int(round(cur0["relative_humidity_2m"]))
        state.weather_code = int(cur0.get("weather_code")) if cur0.get("weather_code") is not None else None
        state.weather_err = ""
        state.weather_ts = time.time()
    except Exception as e:
        state.weather_err = f"{type(e).__name__}: {e}"


def configure_default_workers(manager: SensorManager, state) -> dict[str, bool]:
    """Register the default DeskClock workers for Step 3.

    Returns a small flags dict for compatibility with main():
      {
        "use_switchbot": bool,
        "use_switchbot_in": bool,
      }
    """
    stop_event = manager.stop_event

    manager.add_worker("internet", fetch_internet_loop, state, stop_event)
    manager.add_worker("sht20", fetch_sht20_loop, state, stop_event)

    if AHT21_ENABLE:
        manager.add_worker("aht21", fetch_aht21_loop, state, stop_event)
    if ENS160_ENABLE:
        manager.add_worker("ens160", fetch_ens160_loop, state, stop_event)

    # Start as "recent motion" so the screen is visible immediately after boot.
    state.pir_mono = time.monotonic()
    state.activity_mono = state.pir_mono

    if PIR_ENABLE:
        manager.add_worker("pir", fetch_pir_loop, state, stop_event)
    if BH1750_ENABLE:
        manager.add_worker("bh1750", fetch_bh1750_loop, state, stop_event)

    use_switchbot = all([
        os.environ.get("SWITCHBOT_TOKEN"),
        os.environ.get("SWITCHBOT_SECRET"),
        os.environ.get("SWITCHBOT_outDeviceId") or os.environ.get("SWITCHBOT_deviceId"),
    ])
    use_switchbot_in = all([
        os.environ.get("SWITCHBOT_TOKEN"),
        os.environ.get("SWITCHBOT_SECRET"),
        os.environ.get("SWITCHBOT_inDeviceId"),
    ])

    if use_switchbot_in:
        manager.add_worker("switchbot_indoor", fetch_switchbot_indoor, state, stop_event)

    if use_switchbot:
        manager.add_worker("switchbot_outdoor", fetch_switchbot_outdoor, state, stop_event)
        if WEATHER_ICON_ENABLE:
            manager.add_worker("weather_code", fetch_weathercode_only_loop, state, stop_event, SWITCHBOT_REFRESH_SEC)
    else:
        manager.add_worker("weather", fetch_weather_loop, state, stop_event)
        _prime_open_meteo(state)

    return {
        "use_switchbot": bool(use_switchbot),
        "use_switchbot_in": bool(use_switchbot_in),
    }
