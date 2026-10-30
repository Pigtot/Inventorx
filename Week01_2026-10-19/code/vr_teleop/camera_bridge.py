"""Run the Mac RealSense driver in a camera-only process, outside the control loop.

Some macOS versions require administrator USB access. --camera-admin asks macOS
to authorize only this worker. The web server and robot SDK keep normal user
permissions. A driver crash closes the stream instead of killing robot control.
"""
import math
import os
from pathlib import Path
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np

HEADER = struct.Struct("!4sHH4d")
MAGIC = b"XRC1"


def read_exact(connection, size):
    parts = bytearray()
    while len(parts) < size:
        chunk = connection.recv(size - len(parts))
        if not chunk:
            raise ConnectionError("Camera worker closed its stream.")
        parts.extend(chunk)
    return bytes(parts)


def read_frame(connection, width, height):
    magic, w, h, *intr = HEADER.unpack(read_exact(connection, HEADER.size))
    if magic != MAGIC or (w, h) != (width, height):
        raise ValueError("Camera worker sent an unexpected frame size.")
    if not all(math.isfinite(v) for v in intr) or intr[0] <= 0 or intr[1] <= 0:
        raise ValueError("Camera worker sent invalid lens settings.")
    color = read_exact(connection, w * h * 3)
    depth = np.frombuffer(read_exact(connection, w * h * 4), dtype="<f4").reshape(h, w)
    return color, depth, tuple(intr)


def worker_command(path, width, height, fps, admin, script=None):
    command = [sys.executable, "-u", str(script or Path(__file__).resolve()), "--worker", str(path),
               str(width), str(height), str(fps)]
    if not admin:
        return command
    shell = shlex.join(["/usr/bin/env", "PYTHONDONTWRITEBYTECODE=1", *command])
    # AppleScript string quoting, followed by normal shell argument quoting above.
    quoted = shell.replace("\\", "\\\\").replace('"', '\\"')
    return ["/usr/bin/osascript", "-e", f'do shell script "{quoted}" with administrator privileges']


def receive_camera(camera, changed, stop, width, height, fps, admin=False):
    """Receive RGB and aligned depth through a private local socket. No camera SDK is imported here."""
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="xarm-camera-", dir="/private/tmp") as folder:
            folder = Path(folder)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener, \
                    open(folder / "worker.log", "w+") as log:
                path = folder / "stream.sock"
                listener.bind(str(path))
                os.chmod(path, 0o600)
                listener.listen(1)
                listener.settimeout(0.25)
                if admin:
                    print("\nmacOS may ask to allow the camera-only USB worker.", flush=True)
                # The authorized process may not have permission to read Documents,
                # even as root. Stage just this camera script in the private temp dir.
                script = folder / "camera_bridge.py"
                shutil.copyfile(Path(__file__).resolve(), script)
                process = subprocess.Popen(worker_command(path, width, height, fps, admin, script=script),
                                           stdout=log, stderr=subprocess.STDOUT)
                connection = None
                while not stop.is_set() and connection is None:
                    if process.poll() is not None:
                        raise RuntimeError("Camera worker did not start. " + worker_error(log))
                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue
                if connection is None:
                    return
                try:
                    connection.settimeout(20)   # allow the driver to open the device and deliver its first frame
                    count, began = 0, time.monotonic()
                    while not stop.is_set():
                        color, depth, intr = read_frame(connection, width, height)
                        connection.settimeout(5)
                        with changed:
                            camera.update(data=color, depth=depth, intr=intr, error=None)
                            camera["id"] += 1
                            changed.notify_all()
                        count += 1
                        now = time.monotonic()
                        if now - began >= 1:
                            camera["fps"], count, began = round(count / (now - began)), 0, now
                except (ConnectionError, OSError, ValueError) as exc:
                    raise RuntimeError(f"{exc} " + worker_error(log)) from exc
                finally:
                    connection.close()   # worker exits on broken pipe; no privileged kill is needed
    except Exception as exc:
        if not stop.is_set():
            with changed:
                camera.update(data=None, depth=None, fps=0, error=str(exc))
                changed.notify_all()
            print(f"\nCamera unavailable: {exc}", flush=True)
    finally:
        if process:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()


def worker_error(log):
    log.flush()
    log.seek(0)
    lines = log.read().strip().splitlines()
    return " ".join(lines[-4:]) or "No camera frames received."


def capture(path, width, height, fps):
    """Camera-only worker. Never imports or connects to the robot SDK."""
    import pyrealsense2 as rs
    pipeline = rs.pipeline()
    started = False
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(path)
        try:
            config = rs.config()
            config.enable_stream(rs.stream.color, width, height, rs.format.rgb8, fps)
            config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
            profile = pipeline.start(config)
            started = True
            scale = profile.get_device().first_depth_sensor().get_depth_scale() * 1000
            lens = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
            header = HEADER.pack(MAGIC, width, height, lens.fx, lens.fy, lens.ppx, lens.ppy)
            align = rs.align(rs.stream.color)
            print("D435 stream started.", flush=True)
            first_frame = True
            while True:
                frames = align.process(pipeline.wait_for_frames(15000 if first_frame else 3000))
                first_frame = False
                rgb = bytes(frames.get_color_frame().get_data())
                depth = (np.asanyarray(frames.get_depth_frame().get_data()) * scale).astype("<f4")
                connection.sendall(header + rgb + depth.tobytes())
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if started:
                pipeline.stop()


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "--worker":
        raise SystemExit("This is a camera worker. Start vr_teleop.py instead.")
    capture(sys.argv[2], *map(int, sys.argv[3:]))
