import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from services.tv_controller import (
    AndroidTvRemoteStateReader,
    SwitchBotPlugPowerReader,
    TvPowerDelivery,
    TvPowerStateReader,
)


def test_tv_reader_requires_pairing_material_before_connecting():
    reader = AndroidTvRemoteStateReader("192.0.2.1", "missing-cert", "missing-key")
    assert reader() is None


def test_plug_reader_extracts_instantaneous_watts_and_closes_response():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = (
        b'{"statusCode": 100, "body": {"weight": 62.5}}'
    )
    with patch("services.tv_controller.urlopen", return_value=response) as get:
        reader = SwitchBotPlugPowerReader("token", "secret", "device-id")
        assert reader() == 62.5

    assert "/devices/device-id/status" in get.call_args.args[0].full_url


def test_power_state_reader_uses_hysteresis_and_reports_middle_as_unknown():
    messages = []
    reader = TvPowerStateReader(lambda: 12.0, on_watt=20.0, off_watt=5.0, log=messages.append)

    assert reader() is None
    assert messages == ["[TV] plug_power_w=12.0 panel_state=unknown"]


def test_power_state_reader_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        TvPowerStateReader(lambda: 1.0, on_watt=5.0, off_watt=5.0)


def test_request_queues_a_boolean_target_without_blocking():
    controller = TvPowerDelivery(lambda command: True, lambda: False)
    started = []

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target

        def is_alive(self):
            return False

        def start(self):
            started.append(True)

    with patch("services.tv_controller.threading.Thread", FakeThread):
        controller.request(True)
    assert started == [True]
    assert controller._requests.get_nowait()[0] is True


def test_delivery_skips_a_power_confirmed_matching_state():
    sent = []
    messages = []
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: True,
        log=messages.append,
    )

    controller._deliver(True)

    assert sent == []
    assert messages == ["[TV] command=ON skipped reason=already_on"]


def test_delivery_confirms_after_two_power_samples():
    sent = []
    messages = []
    samples = iter([False, True, True])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        detect_delay_sec=0,
        poll_sec=0,
        confirm_samples=2,
        log=messages.append,
    )

    controller._deliver(True)

    assert sent == ["turnOn"]
    assert messages[-1] == "[TV] command=ON verification=confirmed attempts=1"


def test_delivery_sends_once_when_initial_power_state_is_unknown():
    sent = []
    samples = iter([None, True])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        detect_delay_sec=0,
        poll_sec=0,
        confirm_samples=1,
    )

    controller._deliver(True)

    assert sent == ["turnOn"]


def test_delivery_retries_once_after_confirmed_opposite_power_state():
    sent = []
    samples = iter([False, False, True])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        detect_delay_sec=0,
        poll_sec=0,
        retry_guard_sec=10,
        timeout_sec=30,
        confirm_samples=1,
    )
    # command_at=0; the first observation is still OFF at the retry guard.
    monotonic = iter([0.0, 0.0, 10.0, 10.0, 10.0])
    with patch("services.tv_controller.time.monotonic", side_effect=lambda: next(monotonic)), patch(
        "services.tv_controller.time.sleep"
    ):
        controller._deliver(True)

    assert sent == ["turnOn", "turnOn"]


def test_superseded_delivery_never_sends_an_old_signal():
    sent = []
    messages = []
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: False,
        log=messages.append,
    )
    controller._generation = 2

    controller._deliver(False, generation=1)

    assert sent == []
    assert messages == ["[TV] command=OFF cancelled reason=superseded"]
