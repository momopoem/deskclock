import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
from services.light_controller import LightMotionGate, arm_light_off, light_off_due


def test_isolated_one_second_pulses_do_not_trigger():
    gate = LightMotionGate()
    for start in range(0, 3600, 300):
        for offset in (0, .5, 1.2):
            assert not gate.update(start+offset, True)
        assert not gate.update(start+1.3, False)
    assert gate.last_motion is None


def test_continuous_signal_triggers_at_two_seconds_without_extra_wait():
    gate = LightMotionGate()
    assert not gate.update(10, True)
    assert not gate.update(11.99, True)
    assert gate.update(12, True)
    assert gate.update(20, True)
    assert gate.last_motion == 20


def test_two_real_pulses_trigger_on_second_pulse():
    gate = LightMotionGate()
    assert not gate.update(0, True)
    assert not gate.update(.5, True)
    assert not gate.update(1.2, False)
    assert not gate.update(4, True)
    assert gate.update(4.5, True)
    assert gate.last_motion == 4.5


def test_one_signal_is_not_counted_twice_by_polling():
    gate = LightMotionGate()
    for step in range(20):
        assert not gate.update(step/10, True)
    assert len(gate.hits) == 1


def test_tiny_pulses_and_old_pulses_do_not_accumulate():
    gate = LightMotionGate()
    for t in range(4):
        assert not gate.update(t, True)
        assert not gate.update(t+.1, False)
    assert not gate.update(5, True)
    assert not gate.update(5.5, True)
    gate.update(6, False)
    assert not gate.update(20, True)
    assert not gate.update(20.5, True)


def test_sensor_error_cancels_candidate_and_stale_high():
    gate = LightMotionGate()
    gate.update(0, True)
    gate.update(.5, True)
    assert not gate.update(1, True, valid=False)
    assert not gate.update(2, True)
    assert not gate.update(2.5, True)
    assert gate.update(4, True)
    assert not gate.update(5, True, valid=False)
    assert gate.last_motion == 4


def light_control_block():
    tree = ast.parse((Path(__file__).parents[1]/'app/clock.py').read_text(encoding='utf-8'))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    loop = next(n for n in main.body if isinstance(n, ast.While))
    dpm = next(n for n in loop.body if isinstance(n, ast.If)
               and isinstance(n.test, ast.Name) and n.test.id == 'DISPLAY_PM_ENABLE')
    begin = next(i for i,n in enumerate(dpm.body) if isinstance(n, ast.Assign)
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'pir_v')
    end = next(i for i,n in enumerate(dpm.body) if isinstance(n, ast.If)
               and ast.unparse(n.test) == 'state.light.enabled')
    return compile(ast.Module(body=dpm.body[begin:end+1], type_ignores=[]), 'light-block', 'exec')


def test_actual_light_path_ignores_raw_signal_then_sends_on_when_qualified():
    calls = []
    light = NS(enabled=True, prev_pir_value=0, on_failed_latched=False,
               on_verify_active=False, is_on=False, last_cmd_mono=0, deadline_mono=0)
    env = dict(state=NS(light=light, pir_value=1), light_motion_active=False,
               light_motion=LightMotionGate(), now_mono=100, lux_f=0, is_dark=True,
               disp_state='OFF', LIGHT_ON_MOTION_HOLD_SEC=20,
               SWITCHBOT_LIGHT_COOLDOWN_SEC=3, LIGHT_ON_REPEAT_SEC=3,
               LIGHT_OFF_TIMEOUT_SEC=300, arm_light_off=arm_light_off,
               light_off_due=light_off_due, sb_token=None, sb_secret=None, sb_light_id=None,
               switchbot_light_on=lambda *a: calls.append('ON') or {'ok': True},
               switchbot_light_off=lambda *a: calls.append('OFF') or {'ok': True},
               switchbot_command_succeeded=lambda r: r['ok'], _log_light_event=lambda s: None)
    code = light_control_block()
    exec(code, env)
    assert calls == []
    assert light.deadline_mono == 0
    env['light_motion_active'] = True
    exec(code, env)
    assert calls == ['ON']
    assert light.deadline_mono == 400
    # An ignored pulse while already ON cannot postpone the scheduled OFF.
    light.on_verify_active = False
    light.is_on = True
    env.update(light_motion_active=False, now_mono=401)
    exec(code, env)
    assert calls == ['ON', 'OFF']
