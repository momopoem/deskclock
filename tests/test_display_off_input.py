"""Exercise the actual event-loop section without starting hardware workers."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


def event_loop():
    tree = ast.parse((Path(__file__).parents[1] / 'app/clock.py').read_text(encoding='utf-8'))
    loop = next(n for n in ast.walk(tree) if isinstance(n, ast.While)
                and isinstance(n.test, ast.Name) and n.test.id == 'running')
    body = []
    for node in loop.body:
        if isinstance(node, ast.Assign) and any(isinstance(x, ast.Call)
                and isinstance(x.func, ast.Name) and x.func.id == 'ntp_monitor_update'
                for x in ast.walk(node)):
            break
        body.append(node)
    return compile(ast.Module(body=body, type_ignores=[]), 'clock-input', 'exec')


def context(events, display='OFF', pressing=False):
    saved = []
    pg = NS(KEYDOWN=1, K_ESCAPE=27, MOUSEBUTTONDOWN=2, MOUSEBUTTONUP=3,
            FINGERDOWN=4, FINGERUP=5, event=NS(get=lambda: events))
    state = NS(base_color=(97, 227, 138), activity_mono=0,
               calendar=NS(popup=False), touch_rects_screen={},
               save_ui_state=lambda fn: saved.append(True))
    return dict(pygame=pg, state=state, time=NS(monotonic=lambda: 100),
                disp_state=display, pressing=pressing, long_press_fired=False,
                press_start=1, LONG_PRESS_SEC=2, sw=800, sh=480, running=True,
                save_ui_state=None, random_bright_color=lambda: (1, 2, 3), saved=saved)


@pytest.mark.parametrize('down,up', [(2, 3), (4, 5)])
def test_off_discards_tap_and_release_after_wake(down, up):
    env = context([NS(type=down, pos=(0, 0), x=0, y=0),
                   NS(type=up, pos=(0, 0), x=0, y=0)])
    exec(event_loop(), env)
    assert env['state'].activity_mono == 0
    assert not env['saved']
    env['disp_state'] = 'ON'
    env['pygame'].event.get = lambda: [NS(type=up, pos=(0, 0), x=0, y=0)]
    exec(event_loop(), env)
    assert not env['saved']


def test_off_cancels_pending_long_press():
    env = context([], pressing=True)
    exec(event_loop(), env)
    assert env['state'].base_color == (97, 227, 138)
    assert not env['pressing']
    assert not env['saved']


@pytest.mark.parametrize('display', ['ON', 'DIM'])
def test_visible_tap_still_changes_color(display):
    env = context([NS(type=2, pos=(0, 0)), NS(type=3, pos=(0, 0))], display)
    exec(event_loop(), env)
    assert env['state'].base_color == (1, 2, 3)
    assert env['saved'] == [True]


def test_escape_still_works_when_off():
    env = context([NS(type=1, key=27)])
    exec(event_loop(), env)
    assert not env['running']
