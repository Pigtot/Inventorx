# Offline regression tests

These tests use a fake arm and made-up camera points. They never connect to the arm, camera, headset, or internet.

1. Use a Python environment with NumPy and OpenCV installed (the existing vision environment has both).
2. From the repository root, run:

   ```sh
   python3 -m unittest discover -s Week01_2026-10-19/code/tests -v
   ```

The tests cover all eight audit findings: a blocked SDK connection, mode changes, failed safety setup, a failed first lift, tracking recovery, combined workspace limits, rejected calibration, and stable photo labels.

The Mac camera and Quest USB setup checks added in Week 2 live with that week's diagnostics. From the repository root, run them with local socket access:

```sh
python3 -m unittest discover -s Week02_2026-10-26/code/macos_camera -p test_camera_bridge.py -v
python3 -m unittest discover -s Week02_2026-10-26/code/quest_usb -p test_connect_quest.py -v
```

They use generated camera frames, fake devices, and fake HTTP responses. They never request administrator access or contact hardware. The mode tests also check that `--camera-admin` does not enable live arm control.

For the VR startup regression alone, from the **week folder** on the Windows PC, run:

```powershell
& "$env:USERPROFILE\venvs\xarm\Scripts\python.exe" -m unittest discover -s code/tests -p test_vr_startup.py -v
```

This check needs NumPy and installed Google Chrome. It uses a temporary browser profile and fake headset sessions to check repeat clicks, rejected requests, session exit, and failed graphics setup. It never connects to hardware. It skips on computers without Chrome at the standard Windows installation path. A restricted execution sandbox may prevent Chrome from starting its graphics process.

Passing these tests does not establish the real arm's stop time. **The safety update is not tested yet on the real arm.** Next time, clear the workspace, use a spotter with a hand near the E-stop, and start with low-speed motions.

The labeled photo manifest now includes each photo's permanent `source` URL. The `photo` number is only the old contact-sheet label. Both inference and visualization resolve the photo by `source`. Rerunning the downloader preserves existing credits and appends new numbers. If an expected source is missing, restore that photo and its credit entry instead of relabeling another download with the old number. The six source URLs were recovered from the credits embedded in the archived `media/jenga_net_explorer.html`, in the same first-use order as the original crops.
