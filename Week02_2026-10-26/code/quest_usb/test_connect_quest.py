"""USB setup checks with fake devices and HTTP replies. No hardware is contacted."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import connect_quest as quest


class ConnectionTests(unittest.TestCase):
    def response(self, live):
        return io.StringIO(json.dumps({"live": live, "motion": False}))

    def test_non_quest_is_rejected_before_port_mapping(self):
        with patch.object(quest, 'run', return_value='Pixel 9') as command, \
             patch.object(quest.urllib.request, 'urlopen') as web:
            with self.assertRaisesRegex(RuntimeError, 'not a Quest'):
                quest.connect('adb')
        self.assertEqual(command.call_count, 1)
        web.assert_not_called()

    def test_live_app_is_rejected_before_port_mapping(self):
        with patch.object(quest, 'run', return_value='Quest Pro') as command, \
             patch.object(quest.urllib.request, 'urlopen', return_value=self.response(True)):
            with self.assertRaisesRegex(RuntimeError, 'without --live'):
                quest.connect('adb')
        self.assertEqual(command.call_count, 1)

    def test_dry_run_maps_only_teleop_port_and_opens_quest_browser(self):
        with patch.object(quest, 'run', side_effect=['Quest Pro', '8000', 'Status: ok']) as command, \
             patch.object(quest.urllib.request, 'urlopen', return_value=self.response(False)), \
             contextlib.redirect_stdout(io.StringIO()):
            quest.connect('adb')
        self.assertEqual(command.call_args_list[1].args, ('adb', 'reverse', 'tcp:8000', 'tcp:8000'))
        self.assertEqual(command.call_args_list[2].args[-4:], ('-d', quest.URL, '-p', 'com.oculus.browser'))

    def test_browser_open_failure_is_reported(self):
        with patch.object(quest, 'run', side_effect=['Quest Pro', '8000', 'Error: no activity']), \
             patch.object(quest.urllib.request, 'urlopen', return_value=self.response(False)):
            with self.assertRaisesRegex(RuntimeError, 'did not confirm opening'):
                quest.connect('adb')

    def test_commands_use_usb_selection_and_preserve_argument_boundaries(self):
        result = subprocess.CompletedProcess([], 0, 'device\n', '')
        with patch.object(quest.subprocess, 'run', return_value=result) as command:
            self.assertEqual(quest.run('/path with spaces/adb', 'get-state'), 'device')
        self.assertEqual(command.call_args.args[0], ['/path with spaces/adb', '-d', 'get-state'])


if __name__ == '__main__':
    unittest.main()
