"""Verified SwitchBot infrared delivery for the desk television.

The television stays powered from the mains. Its SwitchBot virtual remote only
transmits infrared commands; a separate SwitchBot Plug Mini measures the
television's real-time draw and verifies the panel state. Network reachability
and Android TV Remote state are not used to infer whether the panel is lit.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen


TvStateReader = Callable[[], bool | None]
SwitchBotSender = Callable[[str], bool]
PowerReader = Callable[[], float | None]


class SwitchBotPlugPowerReader:
    """Read Plug Mini instantaneous power without ever controlling its relay."""

    def __init__(
        self,
        token: str,
        secret: str,
        device_id: str,
        *,
        timeout_sec: float = 8.0,
        log: Callable[[str], None] | None = None,
    ):
        self.token = token
        self.secret = secret
        self.device_id = device_id
        self.timeout_sec = float(timeout_sec)
        self.log = log or logging.getLogger(__name__).info

    def __call__(self) -> float | None:
        started_at = time.monotonic()
        try:
            timestamp = str(int(time.time() * 1000))
            signature = base64.b64encode(
                hmac.new(
                    self.secret.encode("utf-8"),
                    f"{self.token}{timestamp}".encode("utf-8"),
                    hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            request = Request(
                f"https://api.switch-bot.com/v1.1/devices/{self.device_id}/status",
                headers={
                    "Authorization": self.token,
                    "t": timestamp,
                    "nonce": "",
                    "sign": signature,
                    "Content-Type": "application/json",
                },
            )
            with urlopen(request, timeout=self.timeout_sec) as response:
                payload = json.load(response)
            if payload.get("statusCode") != 100:
                raise ValueError(f"api_status_{payload.get('statusCode')}")
            watts = float(payload["body"]["weight"])
            if watts < 0:
                raise ValueError("negative_watts")
            return watts
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            self.log(f"[TV] plug_power=unknown error={type(exc).__name__} elapsed_ms={elapsed_ms}")
            return None


class TvPowerStateReader:
    """Convert Plug Mini watts into a conservative panel ON/OFF state."""

    def __init__(
        self,
        read_watts: PowerReader,
        *,
        on_watt: float,
        off_watt: float,
        log: Callable[[str], None] | None = None,
    ):
        if on_watt <= off_watt or off_watt < 0:
            raise ValueError("on_watt must be greater than non-negative off_watt")
        self.read_watts = read_watts
        self.on_watt = float(on_watt)
        self.off_watt = float(off_watt)
        self.log = log or logging.getLogger(__name__).info

    def __call__(self) -> bool | None:
        watts = self.read_watts()
        if watts is None:
            return None
        if watts >= self.on_watt:
            state: bool | None = True
            label = "on"
        elif watts <= self.off_watt:
            state = False
            label = "off"
        else:
            state = None
            label = "unknown"
        self.log(f"[TV] plug_power_w={watts:.1f} panel_state={label}")
        return state


class AndroidTvRemoteStateReader:
    """Legacy remote-service diagnostic reader; not a panel-state reader."""

    def __init__(
        self,
        host: str,
        cert_path: str,
        key_path: str,
        *,
        name: str = "Desk Side Clock",
        timeout_sec: float = 5.0,
        log: Callable[[str], None] | None = None,
    ):
        self.host = host
        self.cert_path = cert_path
        self.key_path = key_path
        self.name = name
        self.timeout_sec = float(timeout_sec)
        self.log = log or logging.getLogger(__name__).info

    def __call__(self) -> bool | None:
        if not self.host or not Path(self.cert_path).is_file() or not Path(self.key_path).is_file():
            return None
        started_at = time.monotonic()
        try:
            return asyncio.run(self._read())
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            self.log(f"[TV] remote_service=unknown error={type(exc).__name__} elapsed_ms={elapsed_ms}")
            return None

    async def _read(self) -> bool | None:
        try:
            from androidtvremote2 import AndroidTVRemote
        except ImportError:
            return None
        remote = AndroidTVRemote(
            self.name, self.cert_path, self.key_path, self.host, enable_voice=False,
        )
        try:
            await asyncio.wait_for(remote.async_connect(), timeout=self.timeout_sec)
            return bool(remote.is_on)
        finally:
            remote.disconnect()


class TvPowerDelivery:
    """Serialize infrared delivery and verify it from Plug Mini power draw."""

    def __init__(
        self,
        send_command: SwitchBotSender,
        read_state: TvStateReader,
        *,
        detect_delay_sec: float = 2.0,
        poll_sec: float = 2.0,
        retry_guard_sec: float = 10.0,
        timeout_sec: float = 30.0,
        confirm_samples: int = 2,
        log: Callable[[str], None] | None = None,
    ):
        self.send_command = send_command
        self.read_state = read_state
        self.detect_delay_sec = float(detect_delay_sec)
        self.poll_sec = float(poll_sec)
        self.retry_guard_sec = float(retry_guard_sec)
        self.timeout_sec = float(timeout_sec)
        self.confirm_samples = max(1, int(confirm_samples))
        self.log = log or logging.getLogger(__name__).info
        self._requests: queue.Queue[tuple[bool, int] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._generation = 0

    def request(self, target_on: bool) -> None:
        """Request a transition; newer desired state supersedes queued work."""
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._requests.put((bool(target_on), generation))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="deskclock-tv-power", daemon=True)
                self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._requests.put(None)

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            target, generation = request
            while True:
                try:
                    newer = self._requests.get_nowait()
                except queue.Empty:
                    break
                if newer is None:
                    return
                target, generation = newer
            self._deliver(target, generation)

    def _superseded(self, generation: int) -> bool:
        with self._lock:
            return generation != self._generation

    def _deliver(self, target_on: bool, generation: int | None = None) -> None:
        target = "ON" if target_on else "OFF"
        if generation is not None and self._superseded(generation):
            self.log(f"[TV] command={target} cancelled reason=superseded")
            return
        current = self.read_state()
        if current is target_on:
            self.log(f"[TV] command={target} skipped reason=already_{target.lower()}")
            return

        command_at = time.monotonic()
        attempts = 0
        last_state = current
        while attempts < 2:
            if generation is not None and self._superseded(generation):
                self.log(f"[TV] command={target} cancelled reason=superseded")
                return
            attempts += 1
            accepted = self.send_command("turnOn" if target_on else "turnOff")
            self.log(f"[TV] command={target} attempt={attempts} api_ok={accepted}")
            if not accepted:
                return

            deadline = command_at + self.timeout_sec
            retry_at = command_at + self.retry_guard_sec
            if self.detect_delay_sec > 0:
                time.sleep(self.detect_delay_sec)
            confirmations = 0
            while time.monotonic() < deadline:
                if generation is not None and self._superseded(generation):
                    self.log(f"[TV] command={target} verification=cancelled reason=superseded")
                    return
                last_state = self.read_state()
                if last_state is target_on:
                    confirmations += 1
                    if confirmations >= self.confirm_samples:
                        self.log(f"[TV] command={target} verification=confirmed attempts={attempts}")
                        return
                else:
                    confirmations = 0
                if attempts == 1 and last_state is (not target_on) and time.monotonic() >= retry_at:
                    break
                if self.poll_sec > 0:
                    time.sleep(self.poll_sec)

            if attempts == 1 and last_state is (not target_on):
                time.sleep(max(0.0, retry_at - time.monotonic()))
                continue
            break
        self.log(f"[TV] command={target} verification=failed attempts={attempts}")
