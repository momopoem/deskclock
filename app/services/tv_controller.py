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
    """Classify a Plug Mini reading as a power *band*, not a final state.

    A television can spend several seconds between its normal 50--65 W running
    draw and its low standby draw.  Consequently callers must use a sequence
    of these observations; one high or low measurement never proves a panel
    state on its own.
    """

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
            label = "high"
        elif watts <= self.off_watt:
            state = False
            label = "low"
        else:
            state = None
            label = "middle"
        self.log(f"[TV] plug_power_w={watts:.1f} power_band={label}")
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
    """Serialize toggle-IR delivery and verify a power-transition trace.

    The learned infrared power key is a toggle in practice.  A retry is only
    safe after a complete observation window ends in a stable opposite band;
    a delayed fall or rise must never be mistaken for an immediate failure.
    """

    def __init__(
        self,
        send_command: SwitchBotSender,
        read_state: TvStateReader,
        *,
        detect_delay_sec: float = 2.0,
        on_max_attempts: int = 10,
        off_max_attempts: int = 10,
        settle_reads: int = 6,
        confirm_reads: int = 2,
        log: Callable[[str], None] | None = None,
    ):
        self.send_command = send_command
        self.read_state = read_state
        self.detect_delay_sec = float(detect_delay_sec)
        self.on_max_attempts = max(1, int(on_max_attempts))
        self.off_max_attempts = max(1, int(off_max_attempts))
        self.settle_reads = max(2, int(settle_reads))
        self.confirm_reads = max(2, int(confirm_reads))
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
        initial, _ = self._observe_trace(
            target_on, target, generation, phase="initial", early_opposite=True,
        )
        if initial == "target":
            self.log(f"[TV] command={target} skipped reason=already_{target.lower()}")
            return

        def deliver_attempt(attempt: int) -> bool:
            if generation is not None and self._superseded(generation):
                self.log(f"[TV] command={target} cancelled reason=superseded")
                return False
            accepted = self.send_command("turnOn" if target_on else "turnOff")
            self.log(f"[TV] command={target} attempt={attempt} api_ok={accepted}")
            return bool(accepted)

        max_attempts = self.on_max_attempts if target_on else self.off_max_attempts
        for attempt in range(1, max_attempts + 1):
            if not deliver_attempt(attempt):
                return
            outcome, trace = self._observe_trace(target_on, target, generation, phase="verify")
            if outcome == "cancelled":
                return
            if outcome == "target":
                self.log(f"[TV] command={target} verification=confirmed attempts={attempt}")
                return
            if outcome == "inconclusive":
                # Do not turn an unclear, possibly still-moving transition into
                # a second toggle.  Observe it once more before giving up.
                outcome, trace = self._observe_trace(target_on, target, generation, phase="settle")
                if outcome == "cancelled":
                    return
                if outcome == "target":
                    self.log(f"[TV] command={target} verification=confirmed attempts={attempt}")
                    return
            if outcome != "opposite":
                self.log(
                    f"[TV] command={target} verification=unresolved attempts={attempt} "
                    f"trace={self._format_trace(trace)}"
                )
                return
            # Send another toggle only after the entire observation window has
            # ended in a stable opposite band.
            if attempt < max_attempts:
                continue
            self.log(f"[TV] command={target} verification=failed attempts={attempt}")

    def _observe_trace(
        self,
        target_on: bool,
        target: str,
        generation: int | None,
        *,
        phase: str,
        early_opposite: bool = False,
    ) -> tuple[str, list[bool | None]]:
        """Observe a bounded transition and return target/opposite/inconclusive.

        ``True`` is the sustained running-power band, ``False`` the sustained
        low-power band, and ``None`` a transition/middle reading.  The values
        are deliberately evaluated as a trace rather than an absolute state.
        """
        trace: list[bool | None] = []
        for probe in range(1, self.settle_reads + 1):
            if generation is not None and self._superseded(generation):
                self.log(f"[TV] command={target} {phase}=cancelled reason=superseded")
                return "cancelled", trace
            if self.detect_delay_sec > 0:
                time.sleep(self.detect_delay_sec)
            observed = self.read_state()
            trace.append(observed)
            self.log(
                f"[TV] command={target} {phase}=sample probe={probe} "
                f"band={self._band_label(observed)}"
            )
            if self._has_stable_tail(trace, target_on):
                self.log(
                    f"[TV] command={target} {phase}=target trace={self._format_trace(trace)}"
                )
                return "target", trace
            if early_opposite and self._has_stable_tail(trace, not target_on):
                self.log(
                    f"[TV] command={target} {phase}=opposite trace={self._format_trace(trace)}"
                )
                return "opposite", trace

        if self._has_stable_tail(trace, not target_on):
            self.log(
                f"[TV] command={target} {phase}=opposite trace={self._format_trace(trace)}"
            )
            return "opposite", trace
        self.log(f"[TV] command={target} {phase}=inconclusive trace={self._format_trace(trace)}")
        return "inconclusive", trace

    def _has_stable_tail(self, trace: list[bool | None], state: bool) -> bool:
        return len(trace) >= self.confirm_reads and all(
            item is state for item in trace[-self.confirm_reads:]
        )

    @staticmethod
    def _band_label(state: bool | None) -> str:
        return "high" if state is True else "low" if state is False else "middle"

    @classmethod
    def _format_trace(cls, trace: list[bool | None]) -> str:
        return ">".join(cls._band_label(item) for item in trace)
