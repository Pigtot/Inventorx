"""Check live/slow configuration without connecting to the arm, camera or headset."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

VR = Path(__file__).resolve().parents[1] / 'vr_teleop'


def settings(*flags):
    code = (
        'import json, runpy, sys; '
        'sys.path.insert(0, sys.argv[1]); '
        'sys.argv = [sys.argv[1] + "/vr_teleop.py", *sys.argv[2:]]; '
        'app = runpy.run_path(sys.argv[0], run_name="configuration_test"); '
        'print(json.dumps({key: app[key] for key in '
        '("MOVE_ARM", "SPEED", "SLOW_SPEED", "ARM_MAX_SPEED")}))'
    )
    return json.loads(subprocess.check_output(
        [sys.executable, '-c', code, str(VR), *flags], text=True, timeout=10))


class ModeTests(unittest.TestCase):
    def test_slow_alone_does_not_enable_live_mode(self):
        self.assertFalse(settings('--slow')['MOVE_ARM'])

    def test_first_live_test_caps_tool_speed(self):
        config = settings('--live', '--slow')
        self.assertTrue(config['MOVE_ARM'])
        self.assertGreater(config['SPEED'], 0)
        self.assertLessEqual(config['SPEED'], 50)
        self.assertLessEqual(config['ARM_MAX_SPEED'], 50)
        self.assertLessEqual(config['SPEED'], config['ARM_MAX_SPEED'])
        self.assertGreater(config['SLOW_SPEED'], 0)
        self.assertLessEqual(config['SLOW_SPEED'], 25)

    def test_no_flags_keeps_dry_run(self):
        self.assertFalse(settings()['MOVE_ARM'])

    def test_camera_authorization_keeps_dry_run(self):
        self.assertFalse(settings('--camera-admin')['MOVE_ARM'])


if __name__ == '__main__':
    unittest.main()
