"""Check power-on angle branches with in-memory register and status replies."""

import math
from pathlib import Path
import struct
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'teleop_control/vendor/tianji/teleop'))
from gripper.config import position_offset, travel_bounds
from gripper.damiao import DISABLE, ENABLE, Driver
from gripper.runtime import Control, refresh_disabled_feedback


class MotorBus:
    def __init__(self, position, mode):
        self.position = position
        self.mode = mode
        self.replies = []
        self.sent = []

    def queue_feedback(self):
        position_code = round((self.position + 12.5) * 65535 / 25)
        self.replies.append((0, b'\x01' + position_code.to_bytes(2, 'big') + b'\x80\x08\x00\x1e\x1e'))

    def send(self, can_id, payload):
        self.sent.append((can_id, payload))
        if can_id == 0x7FF:
            rid = payload[3]
            value = {0x0A: self.mode, 0x09: 3000, 0x15: 12.5, 0x16: 30., 0x17: 10., 0x50: self.position}[rid]
            self.replies.append((0, payload + struct.pack('<I' if rid in (0x0A, 0x09) else '<f', value)))
        elif payload == DISABLE:
            self.queue_feedback()

    def recv(self):
        return self.replies.pop(0) if self.replies else None


def right_motor(mode=4):
    return dict(motor_id=1, master_id=0, control_mode=mode,
                open_rad=3.28, closed_rad=4.8, travel_margin_rad=.02,
                speed_rad_s=10., current_fraction=.1, feedback_timeout_s=.15,
                max_temperature_c=70)


@pytest.mark.parametrize('mode', [1, 4])
@pytest.mark.parametrize('offset', [0.0, -math.tau])
def test_preflight_and_position_frames_use_one_coherent_branch(mode, offset):
    motors = {'right': right_motor(mode)}
    measured = 3.5417023340808313
    bus = MotorBus(measured + offset, mode)
    driver = Driver(bus, motors)

    driver.preflight()
    refresh_disabled_feedback(driver, motors)

    assert driver.feedback['right'].raw_position == pytest.approx(measured + offset, abs=.0004)
    assert driver.feedback['right'].position == pytest.approx(measured, abs=.0004)
    assert all(payload != ENABLE for _, payload in bus.sent)
    assert not driver.last_position_commands

    driver.enable('right', driver.feedback['right'].position)
    assert bus.sent[-1][1] == ENABLE
    assert driver.last_position_commands['right']['position_rad'] == pytest.approx(measured + offset, abs=.0004)
    lo, hi = travel_bounds(motors['right'])
    for command, bound in ((-20., lo), (20., hi)):
        driver.send_position('right', command)
        wire = driver.last_position_commands['right']['position_rad']
        assert lo <= wire - offset <= hi
        assert wire == pytest.approx(bound + offset, abs=.0004)


def test_status_branch_disagreement_prevents_commands_during_start_and_control():
    motors = {'right': right_motor()}
    bus = MotorBus(-2.741482973098755, 4)
    driver = Driver(bus, motors)
    driver.preflight()
    bus.position += math.tau
    with pytest.raises(RuntimeError, match='motor position branch changed'):
        refresh_disabled_feedback(driver, motors)
    assert not driver.last_position_commands
    assert all(payload != ENABLE for _, payload in bus.sent)

    control = Control(motors, driver, .2)
    control.states['right'].update(state='ACTIVE', target_rad=3.55)
    # A later, apparently valid frame in the same receive batch cannot hide the change.
    bus.queue_feedback()
    bus.position -= math.tau
    bus.queue_feedback()
    now = time.monotonic()
    sample = dict(valid=True, emergency=False, context=None,
                  submitted=now, received=now, triggers={'right': 1.0})
    with pytest.raises(RuntimeError, match='motor position branch changed'):
        control.step(sample, now)
    assert not driver.last_position_commands


@pytest.mark.parametrize('offset', [0.0, -math.tau])
def test_genuine_open_end_overtravel_is_rejected(offset):
    motors = {'right': right_motor()}
    bus = MotorBus(3.30415 + offset, 4)
    driver = Driver(bus, motors)
    driver.preflight()
    refresh_disabled_feedback(driver, motors)
    bus.position = 3.27859 + offset
    with pytest.raises(RuntimeError, match=r'outside calibrated travel: .* calibrated \[3.28, 4.8\]'):
        refresh_disabled_feedback(driver, motors)
    assert not driver.last_position_commands
    assert all(payload != ENABLE for _, payload in bus.sent)


def test_only_a_complete_unambiguous_single_turn_travel_can_be_rebased():
    assert position_offset(right_motor(), -2.741482973098755) == -math.tau
    assert position_offset(right_motor(), 3.5417 + math.tau) is None
    assert position_offset(right_motor(), float('nan')) is None
    # A positive representation is equally valid for negative endpoints.
    assert position_offset(dict(open_rad=-4.8, closed_rad=-3.28), 2.74148) == math.tau
    # Only part of this travel would fit the alternate single-turn range.
    assert position_offset(dict(open_rad=1.71, closed_rad=3.23), 3.2 - math.tau) is None
