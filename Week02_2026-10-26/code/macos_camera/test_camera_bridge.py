"""Camera subprocess tests: generated frames only, no USB or administrator prompts."""
import contextlib
import io
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

VR = Path(__file__).resolve().parents[3] / 'Week01_2026-10-19/code/vr_teleop'
sys.path.insert(0, str(VR))
import camera_bridge as bridge


class FakeStream:
    def __init__(self, data, chunk=7): self.data, self.chunk = data, chunk
    def recv(self, n):
        n = min(n, self.chunk)
        result, self.data = self.data[:n], self.data[n:]
        return result


class FrameTests(unittest.TestCase):
    def packet(self, magic=bridge.MAGIC, intr=(100.,100.,1.,1.)):
        pixels = bytes(range(18))
        depth = np.arange(6, dtype='<f4').reshape(2,3)
        return bridge.HEADER.pack(magic,3,2,*intr) + pixels + depth.tobytes(), pixels, depth
    def test_fragmented_rgb_depth_and_intrinsics_roundtrip(self):
        packet, expected_rgb, expected_depth = self.packet()
        rgb, depth, intr = bridge.read_frame(FakeStream(packet),3,2)
        self.assertEqual(rgb,expected_rgb)
        np.testing.assert_array_equal(depth,expected_depth)
        self.assertEqual(intr,(100.,100.,1.,1.))
    def test_truncated_frame_rejected(self):
        packet,_,_ = self.packet()
        with self.assertRaises(ConnectionError): bridge.read_frame(FakeStream(packet[:-1]),3,2)
    def test_wrong_shape_and_magic_rejected(self):
        packet,_,_=self.packet()
        with self.assertRaises(ValueError): bridge.read_frame(FakeStream(packet),4,2)
        packet,_,_=self.packet(magic=b'BAD!')
        with self.assertRaises(ValueError): bridge.read_frame(FakeStream(packet),3,2)
    def test_invalid_intrinsics_rejected(self):
        for intr in ((0,100,1,1),(100,float('nan'),1,1)):
            packet,_,_=self.packet(intr=intr)
            with self.assertRaises(ValueError): bridge.read_frame(FakeStream(packet),3,2)
    def test_worker_crash_is_contained_and_clears_stale_frame(self):
        camera=dict(data=b'old',depth=np.ones((2,3)),fps=30,id=1)
        command=[sys.executable,'-c','import os; os._exit(139)']
        with patch.object(bridge,'worker_command',return_value=command), contextlib.redirect_stdout(io.StringIO()):
            bridge.receive_camera(camera,threading.Condition(),threading.Event(),3,2,30)
        self.assertIsNone(camera['data'])
        self.assertIsNone(camera['depth'])
        self.assertEqual(camera['fps'],0)
        self.assertIn('did not start',camera['error'])
    def test_worker_disconnect_after_frame_clears_pixels_without_stopping_parent(self):
        packet,_,_=self.packet()
        camera=dict(data=None,depth=None,fps=0,id=0)
        code=('import socket,sys; '
              's=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); '
              's.connect(sys.argv[1]); s.sendall(bytes.fromhex(sys.argv[2])); s.close()')
        def command(path,*args,**kwargs):
            return [sys.executable,'-c',code,str(path),packet.hex()]
        with patch.object(bridge,'worker_command',side_effect=command), contextlib.redirect_stdout(io.StringIO()):
            bridge.receive_camera(camera,threading.Condition(),threading.Event(),3,2,30)
        self.assertEqual(camera['id'],1)
        self.assertIsNone(camera['data'])
        self.assertIsNone(camera['depth'])
        self.assertIn('closed its stream',camera['error'])
    def test_stop_before_worker_connects_returns_without_stale_pixels(self):
        stop=threading.Event();stop.set()
        command=[sys.executable,'-c','pass']
        with patch.object(bridge,'worker_command',return_value=command):
            bridge.receive_camera({},threading.Condition(),stop,3,2,30)
    def test_normal_worker_uses_current_python_and_camera_script_only(self):
        command=bridge.worker_command('/private/tmp/camera.sock',640,360,30,False)
        self.assertEqual(command[0],sys.executable)
        self.assertEqual(Path(command[2]).name,'camera_bridge.py')
        self.assertIn('--worker',command)
        self.assertNotIn('vr_teleop.py',' '.join(command))
    def test_admin_launch_only_authorizes_camera_worker(self):
        command=bridge.worker_command('/private/tmp/camera.sock',640,360,30,True)
        self.assertEqual(command[:2],['/usr/bin/osascript','-e'])
        self.assertIn('with administrator privileges',command[2])
        self.assertIn('camera_bridge.py',command[2])
        self.assertNotIn('vr_teleop.py',command[2])


if __name__ == '__main__': unittest.main()
