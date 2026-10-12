"""Test camera parsing and display decisions without opening GPIO or the camera."""
import ast
import dataclasses
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
import config
from services.presence_controller import PresenceController


def clock_definitions(*names):
    source = (Path(__file__).parents[1] / 'app/clock.py').read_text(encoding='utf-8')
    body = [node for node in ast.parse(source).body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    env = dict(vars(config), dataclass=dataclasses.dataclass, replace=dataclasses.replace,
               Callable=Callable, Optional=Optional, os=os,
               FACE_RECOG_SCRIPT=__file__, FACE_RECOG_PY=sys.executable,
               FACE_RECOG_TIMEOUT_SEC=12)
    exec(compile(ast.Module(body=body, type_ignores=[]), 'clock-definitions', 'exec'), env)
    return env


def test_recognizer_parses_nested_json_and_uses_runtime(monkeypatch):
    def run(command, **kwargs):
        assert command[0] == sys.executable
        assert kwargs['timeout'] == 12
        assert kwargs['env']['DESKCLOCK_FACE_SAVE_DEBUG'] == '0'
        return SimpleNamespace(stdout='camera warning\n{"ok":true,"found_face":true,"filter":{"min_w":80}}\n')
    monkeypatch.setattr(subprocess, 'run', run)
    fn = clock_definitions('run_face_recognize_once')['run_face_recognize_once']
    assert fn()['found_face'] is True


def test_camera_timeout_is_reported(monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 12)
    monkeypatch.setattr(subprocess, 'run', run)
    fn = clock_definitions('run_face_recognize_once')['run_face_recognize_once']
    assert fn() == {'ok': False, 'error': 'timeout'}


def test_unreadable_camera_is_not_reported_as_no_face(tmp_path):
    source = (Path(__file__).parents[1] / 'face/recognize_once.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == 'recognize_once')
    cap = SimpleNamespace(read=lambda: (False, None), release=lambda: None)
    env = dict(open_camera=lambda: (cap, 'test'), time=time, os=os,
               DEBUG_DIR=str(tmp_path), TRY_FRAMES=4, MAX_SECONDS=10)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'camera', 'exec'), env)
    assert env['recognize_once'](None, []) == {'ok': False, 'error': 'camera_read_failed'}


def test_presence_reaches_real_display_power_decisions():
    env = clock_definitions('DimState', 'HdmiState', 'DisplayPowerDecision', 'DisplayPowerStateMachine')
    dpm = env['DisplayPowerStateMachine']()
    dpm.set_on_transition(None)
    dpm.update_dark(0)
    p = PresenceController(0)
    p.record_camera(30, {'ok': True, 'found_face': True})
    for t in (90, 150, 210):
        p.record_camera(t, {'ok': True, 'found_face': False})
    def step(t, brightness):
        return dpm.step(now_mono=t, pir_mono=t if p.hold(t) else p.last_motion,
                        brightness_target=brightness, brightness_cur=brightness)
    assert step(629, 1).dim.disp_state == 'ON'
    assert step(630, 1).dim.disp_state == 'DIM'
    assert step(640, 0).hdmi_cmd == 'OFF'
    p.update_pir(650, True)
    assert step(650, 0).dim.disp_state == 'OFF'
    p.update_pir(650.7, True)
    assert step(650.7, 0).hdmi_cmd == 'ON'
