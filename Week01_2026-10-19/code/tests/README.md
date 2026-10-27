# Offline regression tests

These tests use a fake arm and made-up camera points. They never connect to the arm, camera, headset, or internet.

1. Use a Python environment with NumPy and OpenCV installed (the existing vision environment has both).
2. From the repository root, run:

   ```sh
   python3 -m unittest discover -s Week01_2026-10-19/code/tests -v
   ```

The tests cover all eight audit findings: a blocked SDK connection, mode changes, failed safety setup, a failed first lift, tracking recovery, combined workspace limits, rejected calibration, and stable photo labels.

Passing these tests does not establish the real arm's stop time. **The safety update is not tested yet on the real arm.** Next time, clear the workspace, use a spotter with a hand near the E-stop, and start with low-speed motions.

The labeled photo manifest now includes each photo's permanent `source` URL. The `photo` number is only the old contact-sheet label. Both inference and visualization resolve the photo by `source`. Rerunning the downloader preserves existing credits and appends new numbers. If an expected source is missing, restore that photo and its credit entry instead of relabeling another download with the old number. The six source URLs were recovered from the credits embedded in the archived `media/jenga_net_explorer.html`, in the same first-use order as the original crops.
