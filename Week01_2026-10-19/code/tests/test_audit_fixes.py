"""Regression tests for the eight audit findings. No arm, camera, headset, GPU, or network needed.

Run: python3 -m unittest discover -s Week01_2026-10-19/code/tests -v
Needs NumPy; downloader tests also use its existing OpenCV dependency.
"""
import contextlib
import copy
import csv
import importlib.util
import io
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

CODE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CODE / 'vr_teleop'), str(CODE / 'jenga_cnn')]
import calib
from real_photos import load_crops
from safety import ArmWatchdog, HandInput, SafetyError


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


teleop = load('teleop_under_test', CODE / 'vr_teleop/vr_teleop.py')
first_move = load('first_move_under_test', CODE / '02_first_move.py')
photos = load('photos_under_test', CODE / 'jenga_cnn/07_get_real_photos.py')


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


def message(grip=False, clicks=0, pos=None, trigger=0):
    return dict(grip=grip, pos=[0., 0., 0.] if pos is None else pos,
                yaw=0., clicks=trigger, arm_clicks=clicks)


def arm_hands(hands):
    hands.update(message())
    hands.update(message(clicks=1))
    hands.update(message(grip=True, clicks=1))
    return hands.snapshot()['epoch']


class Controller:
    def __init__(self):
        self.mode, self.state, self.error_code = 7, 4, 0
        self.position = [400., 0., 150., 180., 0., 0.]
        self.settings = [0, [1000, -1000, 1000, -1000, 1000, -1000], 1000., 180., [], 0, 0]
        self.calls = []
        self.fail = None
        self.mismatch = False
        self.stopped = threading.Event()
        self.instances = []

    def factory(self, ip, **options):
        api = FakeAPI(self, options)
        self.instances.append(api)
        return api


class FakeAPI:
    collision_sensitivity = 3
    angles = [0] * 6
    def __init__(self, controller, options=None):
        self.c = controller
        self.options = options or {}
        self.connected = True
        self.connection_lock = threading.Lock()
    @property
    def mode(self): return self.c.mode
    @property
    def state(self): return self.c.state
    @property
    def error_code(self): return self.c.error_code
    @property
    def position(self): return self.c.position
    def record(self, name, *args):
        self.c.calls.append((name, args))
        return -3 if self.c.fail == name else 0
    def set_timeout(self, seconds): self.record('set_timeout', seconds)
    def set_state(self, state):
        with self.connection_lock:
            code = self.record('set_state', state)
            if not code:
                self.c.state = state
                if state == 4: self.c.stopped.set()
            return code
    def set_mode(self, mode):
        code = self.record('set_mode', mode)
        if not code: self.c.mode = mode
        return code
    def get_position(self): return self.record('get_position'), list(self.position)
    def get_gripper_position(self): return self.record('get_gripper_position'), 850
    def get_reduced_states(self):
        code = self.record('get_reduced_states')
        states = copy.deepcopy(self.c.settings)
        if self.c.mismatch and states[0]: states[2] = 900.
        return code, states
    def set_reduced_max_tcp_speed(self, speed):
        code = self.record('set_reduced_max_tcp_speed', speed)
        if not code: self.c.settings[2] = speed
        return code
    def set_reduced_tcp_boundary(self, boundary):
        code = self.record('set_reduced_tcp_boundary', boundary)
        if not code: self.c.settings[1] = list(boundary)
        return code
    def set_reduced_mode(self, enabled):
        code = self.record('set_reduced_mode', enabled)
        if not code: self.c.settings[0] = int(enabled)
        return code
    def set_fence_mode(self, enabled):
        code = self.record('set_fence_mode', enabled)
        if not code: self.c.settings[5] = int(enabled)
        return [code]   # like the real SDK 1.18.4, which returns a list here
    def clean_error(self): return self.record('clean_error')
    def motion_enable(self, enabled): return self.record('motion_enable', enabled)
    def set_gripper_mode(self, mode): return self.record('set_gripper_mode', mode)
    def set_gripper_enable(self, enabled): return self.record('set_gripper_enable', enabled)
    def set_gripper_speed(self, speed): return self.record('set_gripper_speed', speed)
    def set_gripper_position(self, pos, **kw): return self.record('set_gripper_position', pos)
    def set_position(self, *pose, **kw):
        code = self.record('set_position', *pose)
        if not code: self.c.position = list(pose)
        if getattr(self.c, 'on_move', None): self.c.on_move()
        return code
    def disconnect(self):
        self.record('disconnect')
        self.connected = False


class InputTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.hands = HandInput(self.clock)
        arm_hands(self.hands)
    def test_initially_disarmed(self):
        self.assertFalse(HandInput(self.clock).snapshot()['motion'])
    def test_normal_grip_release_keeps_motion_armed(self):
        self.hands.update(message(clicks=1))
        self.assertTrue(self.hands.snapshot()['motion'])
        self.assertFalse(self.hands.snapshot()['grip'])
    def test_jump_latches_until_release_and_new_a_press(self):
        self.hands.update(message(True, 1, [0.3, 0., 0.]))
        self.hands.update(message(True, 1, [0.3, 0., 0.]))
        self.assertFalse(self.hands.snapshot()['motion'])
        self.hands.update(message(True, 2, [0.3, 0., 0.]))
        self.assertFalse(self.hands.snapshot()['motion'])
        self.hands.update(message(False, 2, [0.3, 0., 0.]))
        self.assertFalse(self.hands.snapshot()['motion'])
        self.hands.update(message(False, 3, [0.3, 0., 0.]))
        self.assertTrue(self.hands.snapshot()['motion'])
    def test_lost_pose_cannot_resume_on_tracking_return(self):
        lost = message(clicks=1); lost['pos'] = None
        self.hands.update(lost)
        for _ in range(3): self.hands.update(message(True, 1))
        self.assertFalse(self.hands.snapshot()['motion'])
    def test_stale_packet_disarms_even_when_new_packet_arrives_before_main_loop(self):
        self.clock.now += 0.31
        self.hands.update(message(True, 1))
        self.assertFalse(self.hands.snapshot()['motion'])
    def test_release_and_regrip_between_ticks_changes_epoch(self):
        epoch = self.hands.snapshot()['epoch']
        self.hands.update(message(clicks=1))
        self.hands.update(message(True, 1))
        self.assertNotEqual(epoch, self.hands.snapshot()['epoch'])
    def test_invalid_numbers_disarm(self):
        for value in [float('nan'), float('inf'), '0', True]:
            with self.subTest(value=value):
                self.setUp()
                self.hands.update(message(True, 1, [value, 0., 0.]))
                self.assertFalse(self.hands.snapshot()['motion'])
    def test_page_counter_reset_disarms(self):
        self.hands.update(message(True, 0))
        self.assertFalse(self.hands.snapshot()['motion'])
    def test_cannot_arm_while_holding_grip(self):
        h = HandInput(self.clock)
        h.update(message())
        h.update(message(True, 1))
        self.assertFalse(h.snapshot()['motion'])


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.hands = HandInput(self.clock)
        self.epoch = arm_hands(self.hands)
        self.c = Controller()
        self.arm, self.stop_arm = self.c.factory('fake'), self.c.factory('fake')
        self.guard = ArmWatchdog(self.arm, self.stop_arm, self.hands, self.clock)
    def test_mode_change_blocks_next_command(self):
        self.guard.command(self.epoch, 'Move', self.arm.set_position, 400, 0, 160, 180, 0, 0)
        self.c.mode = 0
        with self.assertRaises(SafetyError):
            self.guard.command(self.epoch, 'Move', self.arm.set_position, 400, 0, 170, 180, 0, 0)
        self.assertEqual(sum(n == 'set_position' for n, _ in self.c.calls), 1)
        self.guard.poll()
        self.assertEqual(self.c.state, 4)
    def test_pause_is_a_fault_instead_of_a_wait(self):
        self.c.state = 3
        with self.assertRaises(SafetyError): self.guard.permit(self.epoch)
        self.guard.poll()
        self.assertEqual(self.c.state, 4)
    def test_loop_stall_stops_even_with_fresh_hand_messages(self):
        self.guard.active = True
        self.clock.now += 0.31
        self.hands.update(message(True, 1))
        self.guard.poll()
        self.assertTrue(self.guard.fault)
        self.assertEqual(self.c.state, 4)
    def test_headset_timeout_cannot_be_hidden_by_loop_pulses(self):
        self.guard.active = True
        self.clock.now += 0.31
        with self.assertRaises(SafetyError): self.guard.pulse()
        self.guard.poll()
        self.assertTrue(self.guard.fault)
        self.assertFalse(self.hands.snapshot()['motion'])
    def test_release_stops_without_fault_and_new_grip_can_resume(self):
        self.guard.active = True
        self.hands.update(message(clicks=1))
        self.guard.poll()
        self.assertEqual(self.c.state, 4)
        self.assertIsNone(self.guard.fault)
        self.hands.update(message(True, 1))
        epoch = self.hands.snapshot()['epoch']
        self.guard.command(epoch, 'Ready', self.arm.set_state, 0)
        self.guard.command(epoch, 'Move', self.arm.set_position, 400, 0, 170, 180, 0, 0)
    def test_delayed_ready_call_does_not_allow_a_followup_move(self):
        def delayed_ready(state):
            self.clock.now += 0.31
            self.guard.poll()
            return 0
        with self.assertRaises(SafetyError):
            self.guard.command(self.epoch, 'Ready', delayed_ready, 0)
        with self.assertRaises(SafetyError):
            self.guard.command(self.epoch, 'Move', self.arm.set_position, 400, 0, 170, 180, 0, 0)
        self.assertFalse(any(n == 'set_position' for n, _ in self.c.calls))
    def test_late_sdk_reply_is_rejected_even_before_watchdog_gets_a_turn(self):
        def delayed_ready(state):
            self.clock.now += 0.31
            self.hands.update(message(True, 1))
            return 0
        with self.assertRaises(SafetyError):
            self.guard.command(self.epoch, 'Ready', delayed_ready, 0)
        with self.assertRaises(SafetyError):
            self.guard.command(self.epoch, 'Move', self.arm.set_position, 400, 0, 170, 180, 0, 0)
        self.assertFalse(any(n == 'set_position' for n, _ in self.c.calls))
    def test_real_watchdog_thread_stops_through_separate_connection_while_call_blocks(self):
        hands = HandInput()
        epoch = arm_hands(hands)
        guard = ArmWatchdog(self.arm, self.stop_arm, hands)
        entered, release = threading.Event(), threading.Event()
        errors = []
        def blocked_move():
            with self.arm.connection_lock:
                entered.set()
                release.wait(2)
                return 0
        def send():
            try: guard.command(epoch, 'Blocked move', blocked_move)
            except SafetyError as exc: errors.append(str(exc))
        worker = threading.Thread(target=send, daemon=True)
        guard.start()
        try:
            worker.start()
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.c.stopped.wait(1.5), 'stop must not wait for the blocked connection')
            self.assertTrue(worker.is_alive(), 'command should still be blocked when stop arrives')
            self.assertTrue(guard.fault)
        finally:
            release.set(); worker.join(1); guard.close()
        self.assertEqual(len(errors), 1)
    def test_grip_change_during_sdk_call_invalidates_command(self):
        def delayed():
            self.hands.update(message(clicks=1))
            self.hands.update(message(True, 1))
            return 0
        with self.assertRaises(SafetyError): self.guard.command(self.epoch, 'Delayed call', delayed)


class SetupTests(unittest.TestCase):
    def connect(self, controller):
        with patch.object(teleop.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            return teleop.connect_arm(controller.factory, lambda _: '')
    def test_each_safety_setup_failure_aborts_before_enabling_motors(self):
        for action in ['get_position', 'get_reduced_states', 'set_reduced_max_tcp_speed',
                       'set_reduced_tcp_boundary', 'set_reduced_mode', 'set_fence_mode']:
            with self.subTest(action=action):
                c = Controller(); c.fail = action
                with self.assertRaises(SafetyError): self.connect(c)
                self.assertFalse(any(n == 'motion_enable' for n, _ in c.calls))
                self.assertTrue(all(not api.connected for api in c.instances))
                self.assertEqual(c.state, 4)
    def test_readback_mismatch_aborts_before_enabling_motors(self):
        c = Controller(); c.mismatch = True
        with self.assertRaises(SafetyError): self.connect(c)
        self.assertFalse(any(n == 'motion_enable' for n, _ in c.calls))
    def test_success_checks_fence_and_starts_stopped(self):
        c = Controller(); original = copy.deepcopy(c.settings)
        arm, stop, old = self.connect(c)
        self.assertEqual(old, original)
        self.assertEqual(c.settings[1], teleop.FENCE)
        self.assertEqual(c.state, 4)
        self.assertFalse(arm.options['check_is_pause'])
        self.assertFalse(arm.options['check_cmdnum_limit'])
        self.assertFalse(stop.options['enable_report'])
    def test_restore_never_readies_arm(self):
        c = Controller(); arm, stop, old = self.connect(c)
        c.calls.clear()
        teleop.restore(stop, old)
        self.assertNotIn(('set_state', (0,)), c.calls)
        self.assertEqual(c.state, 4)
    def test_operator_cancel_disconnects_both_connections(self):
        c = Controller()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                teleop.connect_arm(c.factory, lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertTrue(all(not api.connected for api in c.instances))


class FirstMoveTests(unittest.TestCase):
    def run_first(self, c):
        with patch.object(sys, 'argv', ['02_first_move.py']), contextlib.redirect_stdout(io.StringIO()):
            return first_move.main(c.factory, lambda _: '')
    def test_failed_lift_sends_no_descent(self):
        c = Controller(); c.fail = 'set_position'
        self.assertEqual(self.run_first(c), 1)
        moves = [args for name, args in c.calls if name == 'set_position']
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0][2], 200)
        self.assertEqual(c.state, 4)
        self.assertFalse(c.instances[0].connected)
    def test_success_returns_to_exact_start_pose(self):
        c = Controller(); start = list(c.position)
        self.assertEqual(self.run_first(c), 0)
        moves = [args for name, args in c.calls if name == 'set_position']
        self.assertEqual(list(moves[-1]), start)
    def test_failed_pose_read_sends_no_move(self):
        c = Controller(); c.fail = 'get_position'
        self.assertEqual(self.run_first(c), 1)
        self.assertFalse(any(n == 'set_position' for n, _ in c.calls))


class MainLoopTests(unittest.TestCase):
    def run_loop(self, frames, controller=None, during_move=None):
        c = controller or Controller()
        arm, stop = c.factory('fake'), c.factory('fake')
        old = copy.deepcopy(c.settings)
        hands = HandInput()
        if during_move:
            c.on_move = lambda: during_move(hands)
        frames = iter(frames)
        class FakeServer:
            def __init__(self, *args): pass
            def serve_forever(self): pass
            def shutdown(self): c.recorded_shutdown = len(c.calls)
            def server_close(self): pass
        def tick(_):
            try: frame = next(frames)
            except StopIteration: raise KeyboardInterrupt()
            if isinstance(frame, int):
                c.calls.append(('external_mode_change', (frame,)))
                c.mode = frame
            else: hands.update(frame)
        with patch.object(teleop, 'Server', FakeServer), patch.object(teleop, 'camera_loop', lambda: None), \
             patch.object(teleop, 'MOVE_ARM', True), patch.object(teleop, 'hands', hands), \
             patch.object(teleop, 'arm', None), patch.object(teleop, 'report', {}), \
             patch.object(teleop, 'connect_arm', return_value=(arm, stop, old)), \
             patch.object(ArmWatchdog, 'start'), patch.object(teleop.time, 'sleep', side_effect=tick), \
             contextlib.redirect_stdout(io.StringIO()):
            result = teleop.main()
            self.assertFalse(teleop.report['motion'])
        return result, c
    def test_main_loop_stops_on_mode_change_during_grip(self):
        result, c = self.run_loop([message(), message(clicks=1), message(True, 1), 0])
        self.assertEqual(result, 1)
        change = next(i for i, (n, _) in enumerate(c.calls) if n == 'external_mode_change')
        self.assertFalse(any(n == 'set_position' for n, _ in c.calls[change:]))
    def test_normal_release_and_regrip_work_without_restart(self):
        result, c = self.run_loop([message(), message(clicks=1), message(True, 1),
                                   message(clicks=1), message(True, 1)])
        self.assertEqual(result, 0)
        self.assertEqual(sum((n, args) == ('set_state', (0,)) for n, args in c.calls), 2)
    def test_release_during_sdk_reply_cancels_without_exiting(self):
        result, c = self.run_loop([message(), message(clicks=1), message(True, 1), message(clicks=1)],
                                  during_move=lambda hands: hands.update(message(clicks=1)))
        self.assertEqual(result, 0)
        self.assertEqual(c.state, 4)
        self.assertEqual(sum(n == 'set_position' for n, _ in c.calls), 1)
    def test_shutdown_stops_before_disconnect_and_web_server(self):
        result, c = self.run_loop([message(), message(clicks=1), message(True, 1)])
        self.assertEqual(result, 0)
        disconnected = next(i for i, (n, _) in enumerate(c.calls) if n == 'disconnect')
        self.assertIn(('set_state', (4,)), c.calls[:disconnected])
        self.assertLess(disconnected, c.recorded_shutdown)
        self.assertEqual(c.state, 4)
    def test_tracking_fault_requires_release_and_a_in_actual_loop(self):
        result, c = self.run_loop([message(), message(clicks=1), message(True, 1),
                                   message(True, 1, [0.3, 0, 0]), message(True, 1, [0.3, 0, 0]),
                                   message(True, 2, [0.3, 0, 0]), message(False, 2),
                                   message(False, 3), message(True, 3)])
        self.assertEqual(result, 0)
        self.assertEqual(sum(n == 'set_position' for n, _ in c.calls), 2)


class WorkspaceTests(unittest.TestCase):
    def assert_safe(self, point):
        x, y, z = point
        self.assertGreaterEqual(x + 1e-8, teleop.FRONT)
        self.assertGreaterEqual(math.hypot(x, y) + 1e-8, teleop.NEAR)
        self.assertLessEqual(math.hypot(x, y, z), teleop.REACH + 1e-8)
        self.assertGreaterEqual(z, teleop.FLOOR)
        self.assertLessEqual(z, teleop.CEILING)
    def test_front_and_reach_limits_hold_together(self):
        point, _ = teleop.keep_safe(0, 600, 0)
        self.assert_safe(point)
    def test_random_targets_satisfy_every_workspace_bound(self):
        rng = random.Random(7)
        for _ in range(5000):
            point, _ = teleop.keep_safe(*(rng.uniform(-1500, 1500) for _ in range(3)))
            self.assert_safe(point)
            again, _ = teleop.keep_safe(*point)
            np.testing.assert_allclose(again, point, atol=1e-8)
    def test_nonfinite_targets_are_rejected(self):
        for value in [float('nan'), float('inf'), -float('inf')]:
            for axis in range(3):
                xyz = [400, 0, 150]; xyz[axis] = value
                with self.subTest(value=value, axis=axis), self.assertRaises(SafetyError):
                    teleop.keep_safe(*xyz)


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.C = np.array([[0, 0, 200], [80, 0, 200], [0, 80, 200], [80, 80, 250]], dtype=float)
        self.T = calib.pose_matrix(60, 20, -100, 15, 25, 35)
        self.P = self.C @ self.T[:3, :3].T + self.T[:3, 3]
    def test_valid_transform_is_recovered(self):
        T, rms = calib.solve(list(zip(self.C, self.P)))
        np.testing.assert_allclose(T, self.T, atol=1e-10)
        self.assertLess(rms, 1e-9)
    def test_planar_points_are_allowed(self):
        self.C[:, 2] = 200
        P = self.C @ self.T[:3, :3].T + self.T[:3, 3]
        T, rms = calib.solve(list(zip(self.C, P)))
        np.testing.assert_allclose(T, self.T, atol=1e-10)
    def test_repeated_collinear_and_nearly_collinear_points_are_rejected(self):
        for C in [np.zeros((4, 3)), np.array([[0, 0, i * 30] for i in range(4)]),
                  np.array([[i * 30, i % 2 * 0.1, 200] for i in range(4)])]:
            with self.subTest(C=C.tolist()), self.assertRaises(ValueError): calib.solve(list(zip(C, C)))
    def test_too_few_points_rejected(self):
        with self.assertRaises(ValueError): calib.solve(list(zip(self.C[:3], self.P[:3])))
    def test_nonfinite_points_rejected(self):
        self.C[0, 0] = np.nan
        with self.assertRaises(ValueError): calib.solve(list(zip(self.C, self.P)))
    def test_high_residual_rejected(self):
        with self.assertRaises(ValueError): calib.solve(list(zip(self.C, self.P * 2)))
    def test_rejected_solve_preserves_saved_and_active_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'camera_calibration.json'
            old = calib.save(path, self.T, 1.0, 4)
            original = path.read_bytes()
            with patch.object(teleop, 'CALIB_FILE', path), patch.object(teleop, 'T_tool_cam', self.T), \
                 patch.object(teleop, 'calib_info', old), \
                 patch.object(teleop, 'calibration', {'mark': [0,0,0], 'pairs': [(self.C[0],self.P[0])] * 4}):
                reply = teleop.calibrate('solve', {})
                self.assertFalse(reply['ok'])
                self.assertEqual(path.read_bytes(), original)
                self.assertIs(teleop.T_tool_cam, self.T)
    def test_failed_atomic_save_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'camera_calibration.json'; path.write_text('original')
            with patch.object(Path, 'replace', side_effect=OSError('disk error')), self.assertRaises(OSError):
                calib.save(path, self.T, 1.0, 4)
            self.assertEqual(path.read_text(), 'original')


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.credits, self.crops = self.root/'credits.csv', self.root/'crops.csv'
    def write(self, path, rows):
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    def test_crop_source_survives_changed_photo_numbers(self):
        self.write(self.crops, [dict(photo=197, source='source-A', cx=20, cy=20, side=20)])
        self.write(self.credits, [dict(number=197, file='wrong.jpg', source='source-B'),
                                  dict(number=198, file='right.jpg', source='source-A')])
        picks, info = load_crops(self.crops, self.credits)
        self.assertEqual(info[picks[0]['source']]['file'], 'right.jpg')
    def test_missing_source_fails_instead_of_using_same_photo_number(self):
        self.write(self.crops, [dict(photo=197, source='source-A')])
        self.write(self.credits, [dict(number=197, file='wrong.jpg', source='source-B')])
        with self.assertRaises(ValueError): load_crops(self.crops, self.credits)
    def test_ambiguous_source_rejected(self):
        self.write(self.crops, [dict(photo=1, source='source-A')])
        self.write(self.credits, [dict(number=1, file='a.jpg', source='source-A'),
                                  dict(number=2, file='b.jpg', source='source-A')])
        with self.assertRaises(ValueError): load_crops(self.crops, self.credits)
    def test_new_download_keeps_old_credits_and_appends_number(self):
        old = dict(number='197', file='z-old.jpg', title='Old', creator='A', license='CC BY', source='source-A')
        self.write(self.credits, [old])
        record = dict(title='New', creator='B', license='by', license_version='2.0', foreign_landing_url='source-B')
        rows = photos.update_credits(self.credits, [('a-new.jpg', record)])
        self.assertEqual(rows[0], old)
        self.assertEqual(rows[1]['number'], 198)
        self.assertEqual(photos.update_credits(self.credits, [])[0], old)
    def test_all_original_crops_have_archived_source_ids(self):
        with open(CODE/'jenga_cnn/real_crops.csv', newline='') as f: picks = list(csv.DictReader(f))
        self.assertEqual(len(picks), 21)
        self.assertEqual(len(set(r['source'] for r in picks)), 6)
        self.assertTrue(all(r['source'].startswith('https://www.flickr.com/photos/') for r in picks))


if __name__ == '__main__':
    unittest.main()
