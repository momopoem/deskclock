"""SwitchBot power delivery for the desk television.

Android TV Remote v2 reports its remote-control service state, not whether
the panel is lit.  It may therefore remain reachable while the TV screen is
off.  The presence-session request is the authority for delivery: send its
explicit SwitchBot ON/OFF command once, then record remote-service
reachability only as diagnostics.
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
    """Read Android/Google TV remote-service reachability using its certificate."""

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
    """Serialize one explicit TV command per presence-session request.

    ``read_state`` is intentionally diagnostic only.  Android TV Remote's
    ``is_on`` is the remote-control service status, so it must never suppress
    an explicit SwitchBot ``turnOn`` or ``turnOff`` request.
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
        # Retained as constructor arguments to keep existing configuration
        # compatible.  Remote state is not a panel-state verifier, so polling
        # and retry guards are deliberately not used for command decisions.
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
        accepted = self.send_command("turnOn" if target_on else "turnOff")
        self.log(f"[TV] command={target} attempt=1 api_ok={accepted}")
        if not accepted:
            return

        if self.detect_delay_sec > 0:
            time.sleep(self.detect_delay_sec)
        if generation is not None and self._superseded(generation):
            self.log(f"[TV] command={target} observation=cancelled reason=superseded")
            return
        remote_service_started = self.read_state()
        self.log(
            f"[TV] command={target} remote_service_started={remote_service_started} "
            "panel_state=not_observable"
        )
