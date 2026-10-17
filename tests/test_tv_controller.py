import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


def test_power_state_reader_reports_a_middle_transition_band():
    messages = []
    reader = TvPowerStateReader(lambda: 12.0, on_watt=20.0, off_watt=5.0, log=messages.append)

    assert reader() is None
    assert messages == ["[TV] plug_power_w=12.0 power_band=middle"]


def test_power_state_reader_reports_low_band_when_configured():
    reader = TvPowerStateReader(lambda: 6.0, on_watt=20.0, off_watt=6.0)

    assert reader() is False


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


def test_delivery_skips_only_after_two_matching_power_samples():
    sent = []
    messages = []
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: True,
        settle_reads=2,
        log=messages.append,
    )

    controller._deliver(True)

    assert sent == []
    assert messages[-1] == "[TV] command=ON skipped reason=already_on"


def test_delivery_confirms_after_a_trace_of_two_high_samples():
    sent = []
    messages = []
    samples = iter([False, False, None, True, True])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=3,
        log=messages.append,
    )

    with patch("services.tv_controller.time.sleep") as sleep:
        controller._deliver(True)

    assert sent == ["turnOn"]
    assert sleep.call_args_list == [call(2.0)] * 5
    assert messages[-1] == "[TV] command=ON verification=confirmed attempts=1"


def test_delivery_waits_through_middle_transition_before_confirming_off():
    sent = []
    messages = []
    samples = iter([True, True, True, None, False, False])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=4,
        log=messages.append,
    )

    with patch("services.tv_controller.time.sleep"):
        controller._deliver(False)

    assert sent == ["turnOff"]
    assert "[TV] command=OFF verify=target trace=high>middle>low>low" in messages


def test_delivery_retries_only_after_a_complete_opposite_trace():
    sent = []
    messages = []
    samples = iter([False, False, False, False, False, True, True])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=3,
        log=messages.append,
    )
    with patch("services.tv_controller.time.sleep") as sleep:
        controller._deliver(True)

    assert sent == ["turnOn", "turnOn"]
    assert messages[-1] == "[TV] command=ON verification=confirmed attempts=2"


def test_delivery_observes_a_delayed_low_transition_without_a_second_toggle():
    sent = []
    messages = []
    samples = iter([True, True, True, None, False, False])
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=4,
        log=messages.append,
    )

    with patch("services.tv_controller.time.sleep"):
        controller._deliver(False)

    assert sent == ["turnOff"]
    assert "[TV] command=OFF verification=confirmed attempts=1" in messages


def test_delivery_reports_failure_after_tenth_stable_opposite_trace():
    sent = []
    messages = []
    samples = iter([False] * 2 + [False] * 3 * 10)
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=3,
        log=messages.append,
    )

    with patch("services.tv_controller.time.sleep"):
        controller._deliver(True)

    assert sent == ["turnOn"] * 10
    assert messages[-1] == "[TV] command=ON verification=failed attempts=10"


def test_delivery_retries_off_up_to_ten_stable_opposite_traces():
    sent = []
    samples = iter([True] * 2 + [True] * 3 * 10)
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: next(samples),
        settle_reads=3,
    )

    with patch("services.tv_controller.time.sleep"):
        controller._deliver(False)

    assert sent == ["turnOff"] * 10


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
