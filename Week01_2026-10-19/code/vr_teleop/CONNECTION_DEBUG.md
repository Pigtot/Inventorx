# Quest Pro cable connection: diagnosis, 2026-10-27

The user confirmed that the full teleop page works inside the Quest Pro after the compatibility update. The log shows VR running at about 60–77 fps with the camera around 30 fps. The problem was isolated to the page's VR graphics startup; a broken Python installation or cable connection was not needed to explain it.

## What was checked

| Layer | Evidence on this Windows PC | Result |
|---|---|---|
| Python environment | `~/venvs/xarm/Scripts/python.exe`: Python 3.12.13; NumPy, RealSense and xArm imports succeeded; SDK 1.18.4 | Required runtime packages work |
| Python HTTP server | `/`, `/status`, HUD, three.js, scene modules and a mesh returned HTTP 200; JavaScript has `text/javascript` content type | Tested routes work |
| Chrome page startup | An isolated Chrome profile loaded the full page, enabled Enter VR and logged graphics compatibility completing in 17 ms | Page startup works in the tested profile |
| Meta configuration | Active OpenXR runtime points to Meta Horizon; runtime service is running | Runtime is registered |
| USB power setting | Current power plan has selective suspend disabled on both AC and battery | Already disabled; no setting changed |
| Real startup attempt | `vr_debug.log` at 14:19:39: session request took 33,185 ms, graphics attachment took 12 ms; subsequent lines show VR 0 fps while the camera continues around 30 fps | Session allocation is slow; VR loop is not receiving frames |
| Repeated clicks | Same log: `InvalidStateError: There is already an active, immersive XRSession` while the first request is pending | Confirmed page bug; fixed |
| Meta runtime log | `Service_2026-10-27_13.44.14.txt` reports “Still initializing” and “No frames available”; it also records Chrome reaching the focused session state | Link connection alone does not establish working rendering |
| Running server, follow-up | Both `localhost:8000/vr_check.html` and `127.0.0.1:8000/vr_check.html` returned 200; response matched the current file; `/status` confirmed dry run | The test page is available from the active server |
| Real headset isolation test | User reported “I see blue” from `vr_check.html` | Basic WebXR rendering works over the cable |

The isolated Chrome check did **not** enter immersive VR or test visibility inside the headset. Earlier headless Chrome attempts inside the execution sandbox failed with access-denied errors; the isolated check succeeded outside that sandbox. Those sandbox failures are not evidence of a broken graphics driver.

## What changed

- Enter VR is disabled while starting and while a session is active, preventing overlapping requests.
- An end handler is attached immediately after session allocation. Failed graphics setup ends the allocated session before allowing another attempt.
- Startup errors are displayed with their actual names and messages.
- Debug output now includes session visibility and a native Chrome frame callback. If Chrome delivers native frames but the three.js loop does not run, investigate the three.js rendering path. If neither callback runs, investigate Chrome/Meta session delivery and visibility.
- `vr_check.html` tests basic WebXR directly, without three.js, the camera, or hand commands. It only reads `/status`; it never sends `/pose` or connects to the arm.
- After the user confirmed blue in the headset, the full page was changed to explicitly use a WebGL 1 context with antialiasing disabled, matching the working test. In the bundled three.js r160, this selects the classic `XRWebGLLayer` branch instead of the WebGL 2 projection-layer branch. The actual output layer is logged after setup. This is a targeted compatibility change, not proof that projection layers caused the original failure.

Other timing diagnostics and the switch to plain VR were being edited concurrently during this investigation. Those edits were preserved.

## Short test: use the cable setup

1. From this week's folder, start a dry run in PowerShell:

   ```powershell
   & "$env:USERPROFILE\venvs\xarm\Scripts\python.exe" .\code\vr_teleop\vr_teleop.py
   ```

2. Close the old VR tab so its session can end. Connect Quest Link. In **Chrome on the Windows PC**, open `http://localhost:8000/vr_check.html`.
3. Press Enter VR once and keep the headset on. The test shows each startup stage and how long it takes. A slowly changing blue/green view means basic VR rendering works.

| Test result | Next step |
|---|---|
| Blue/green appears | Basic cable rendering works. Retry the main page after Ctrl+Shift+R and inspect its frame/error log. |
| Waiting on step 1 | Meta/OpenXR session allocation has not completed. Check for another VR tab/app holding a session. |
| Waiting on step 2 or an error at step 3 | Graphics compatibility or headset output setup failed. Keep the exact error and inspect `chrome://gpu`. |
| Waiting on step 4 with the headset on | The basic WebXR test has no tracked rendered frame yet. Check Link visibility and runtime delivery. |
| Page itself does not open | Check the Python terminal and URL first. `localhost` must refer to the PC running Python. |

This architecture uses the Quest as a cable-connected PC headset. The standalone Quest Browser is a different setup. WebXR requires a secure context; `http://localhost` on the PC qualifies. See the [WebXR startup documentation](https://developer.mozilla.org/en-US/docs/Web/API/WebXR_Device_API/Startup_and_shutdown) and [WebXR specification](https://www.w3.org/TR/webxr/).

## Validation

The browser regression in `code/tests/test_vr_startup.py` runs in real Chrome with fake XR sessions. It covers pending and active repeat clicks, request refusal, normal exit, failed graphics setup releasing its session, the WebGL 1 graphics selection, and an actual HUD/scene render with a real WebGL context. No arm or headset commands are used by the regression.

Both the isolated blue test and the full page **have been verified inside the real headset by the user, in dry-run mode**. No real arm movement has been reported for this update yet. Controller vibration is reported unavailable by Chrome, so the spotter must use visual checks and the E-stop rather than relying on buzzes.

For the first live trial, `--live --slow` requests a maximum tool speed of 50 mm/s, reduces the near-floor speed to 25 mm/s, and sets the arm controller's reduced-mode speed cap to 50 mm/s. The existing workspace fence and spotter prompt still apply. `--slow` alone remains a dry run. `run_live_slow.ps1` runs this command in the operator's console.
