# Mac D435 capture — 2026-10-28

After reconnecting the camera, color and aligned depth capture worked. The D435 reports USB **2.1** on the current connection. Its available color profiles include 640×480 at 15 fps, but not the app's previous 640×360 color mode. The successful camera-only probe used **640×480 at 15 fps for both streams** and received ten frames, with 97,707 valid depth pixels in the last frame.

The teleop app now uses that mode on macOS. Its camera driver runs in [`camera_bridge.py`](../../../Week01_2026-10-19/code/vr_teleop/camera_bridge.py), alongside the existing Week 1 application. Only the camera worker gets administrator USB access; the HTTP server and robot code run as the normal user. The worker script is staged in a private temporary directory because the privileged process cannot read the project's Documents folder. Color, aligned depth in millimeters, and lens settings travel through a private local socket.

## Tested Python environment

Python **3.12.13** is installed at `~/venvs/xarm`, outside the synced project folder. To recreate the environment on another Apple Silicon Mac with Python 3.12 installed:

```sh
python3.12 -m venv ~/venvs/xarm
~/venvs/xarm/bin/python -m pip install numpy==2.5.4 xarm-python-sdk==1.18.4 opencv-python-headless==5.0.0.93 pillow==13.0.0 pyrealsense2-macosx==2.56.5
```

All these imports and the package dependency check passed. The RealSense package above is the Mac wrapper; use the existing Windows environment for the Windows PC.

## Run a dry test

From the repository root:

```sh
~/venvs/xarm/bin/python Week01_2026-10-19/code/vr_teleop/vr_teleop.py --camera-admin
```

Approve the native macOS administrator prompt, then open [the teleop page](http://localhost:8000). This command does not connect to or enable the arm. Press Ctrl+C in the launching terminal to stop it. Windows keeps its existing camera path and 640×360 at 30 fps setting.

## Verified

- Standalone D435 color and aligned depth capture: [`camera_probe.py`](camera_probe.py), [`successful output`](camera_probe.log). The probe needs the same administrator USB access; on this Mac stage it outside Documents before invoking the native prompt.
- Integrated `/camera` and `/camera?view=depth` each returned 921,600 RGB bytes, with `X-Picture` reporting 640×480.
- Six samples over ten seconds advanced from picture 799 to 950, measured at 15.0 fps. Both pictures contained nonzero pixels.
- `/status` remained `live: false`, `motion: false`. Process inspection confirmed only the camera helper was root.
- Nine hardware-free worker tests passed, including a child crash and a child disconnect after a valid frame. Both clear stale pixels without killing the parent. The camera permission flag also passed a separate test proving it leaves live mode disabled.

Run the worker tests with local socket access:

```sh
PYTHONDONTWRITEBYTECODE=1 ~/venvs/xarm/bin/python -m unittest discover -s Week02_2026-10-26/code/macos_camera -p test_camera_bridge.py -v
```

Earlier failures are retained in [`camera_probe_failed.log`](camera_probe_failed.log). They included a missing USB device, power-state errors, and a native libusb cleanup crash. The successful test establishes capture after reconnection and a supported mode; it does not establish that all earlier symptoms shared one cause.

On pausing, the dry-run program was stopped with SIGINT (the signal sent by Ctrl+C). Its server and camera helper exited, port 8000 stopped listening, and the private worker folder was removed. Real camera unplug/crash behavior has not been tested end to end. VR rendering, controller input, and robot movement on this Mac have not been verified. No movement commands were sent during these camera tests. Continue with the [Quest USB setup notes](../quest_usb/README.md).
