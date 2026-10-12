"""Verified SwitchBot power delivery for the desk television.

The SwitchBot infrared API acknowledges delivery to the Hub, not whether the
television changed state.  This worker therefore treats Android TV Remote v2
as the source of truth.  It is deliberately independent from LightOnDelivery:
repeating an infrared TV command blindly could undo a successful toggle.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path


TvStateReader = Callable[[], bool | None]
SwitchBotSender = Callable[[str], bool]


class AndroidTvRemoteStateReader:
    """Read an Android/Google TV standby state using its paired certificate."""

    def __init__(self, host: str, cert_path: str, key_path: str, *, name: str = "Desk Side Clock"):
        self.host = host
        self.cert_path = cert_path
        self.key_path = key_path
        self.name = name

    def __call__(self) -> bool | None:
        if not self.host or not Path(self.cert_path).is_file() or not Path(self.key_path).is_file():
            return None
        try:
            return asyncio.run(self._read())
        except Exception:
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
            await remote.async_connect()
            return bool(remote.is_on)
        finally:
            remote.disconnect()


class TvPowerDelivery:
    """Serialize verified ON/OFF delivery without blocking the pygame loop.

    A request is ignored until the current network state is known.  After a
    SwitchBot command, polling starts after ``detect_delay_sec``.  One retry is
    allowed only when the state is still known to be the opposite of the target
    and at least ``retry_guard_sec`` has elapsed since the first command.
    """

    def __init__(
        self,
        send_command: SwitchBotSender,
        read_state: TvStateReader,
        *,
        detect_delay_sec: float = 2.0,
        poll_sec: float = 2.0,
        retry_guard_sec: float = 10.0,
        timeout_sec: float = 30.0,
        log: Callable[[str], None] | None = None,
    ):
        self.send_command = send_command
        self.read_state = read_state
        self.detect_delay_sec = float(detect_delay_sec)
        self.poll_sec = float(poll_sec)
        self.retry_guard_sec = float(retry_guard_sec)
        self.timeout_sec = float(timeout_sec)
        self.log = log or logging.getLogger(__name__).info
        self._requests: queue.Queue[tuple[bool, int] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._generation = 0

    def request(self, target_on: bool) -> None:
        """Request a state transition; duplicate requests are coalesced by order."""
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._requests.put((bool(target_on), generation))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="deskclock-tv-power", daemon=True)
                self._thread.start()

    def stop(self) -> None:
        # Also cancel an in-flight verification before the process exits.
        with self._lock:
            self._generation += 1
            self._requests.put(None)

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            target, generation = request
            # A newer desired state supersedes queued work before any signal is sent.
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
        if current is None:
            self.log(f"[TV] command={target} skipped reason=state_unknown")
            return
        if current is target_on:
            self.log(f"[TV] command={target} skipped reason=already_{target.lower()}")
            return

        command_at = time.monotonic()
        attempts = 0
        while attempts < 2:
            if generation is not None and self._superseded(generation):
                self.log(f"[TV] command={target} cancelled reason=superseded")
                return
            attempts += 1
            accepted = self.send_command("turnOn" if target_on else "turnOff")
            self.log(f"[TV] command={target} attempt={attempts} api_ok={accepted}")
            if not accepted:
                return

            poll_at = time.monotonic() + self.detect_delay_sec
            retry_at = command_at + self.retry_guard_sec
            deadline = command_at + self.timeout_sec
            last_state: bool | None = current
            while time.monotonic() < deadline:
                if generation is not None and self._superseded(generation):
                    self.log(f"[TV] command={target} cancelled reason=superseded")
                    return
                wait_until = min(poll_at, deadline)
                time.sleep(max(0.0, wait_until - time.monotonic()))
                if time.monotonic() >= deadline:
                    break
                last_state = self.read_state()
                if last_state is target_on:
                    self.log(f"[TV] command={target} verification=confirmed attempts={attempts}")
                    return
                if last_state is None:
                    self.log(f"[TV] command={target} verification=state_unknown")
                    return
                if attempts == 1 and time.monotonic() >= retry_at:
                    break
                poll_at = time.monotonic() + self.poll_sec

            if attempts == 1 and last_state is (not target_on):
                # Keep at least the tested OFF->ON guard interval between IR signals.
                time.sleep(max(0.0, retry_at - time.monotonic()))
                continue
            break
        self.log(f"[TV] command={target} verification=failed attempts={attempts}")
