import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from services.tv_controller import AndroidTvRemoteStateReader, TvPowerDelivery


def test_tv_reader_requires_pairing_material_before_connecting():
    reader = AndroidTvRemoteStateReader("192.0.2.1", "missing-cert", "missing-key")
    assert reader() is None


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


def test_delivery_skips_an_already_matching_state():
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


def test_delivery_sends_once_when_state_is_unknown():
    sent = []
    messages = []
    controller = TvPowerDelivery(
        lambda command: sent.append(command) or True,
        lambda: None,
        detect_delay_sec=0,
        timeout_sec=0,
        log=messages.append,
    )

    controller._deliver(False)

    assert sent == ["turnOff"]
    assert messages == [
        "[TV] command=OFF state_unknown fallback=send_once",
        "[TV] command=OFF attempt=1 api_ok=True",
        "[TV] command=OFF verification=failed attempts=1",
    ]


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
