# Quest controllers on the Mac — paused 2026-10-28

**Where we stopped:** Meta Quest Developer Hub is installed and open. Its existing-account sign-in button opened Meta's browser login. Sign-in, developer account verification, headset pairing, and USB debugging approval are not confirmed. We paused at Patrick's request. **The controllers have not sent input to the Mac yet.**

The Mac can see the Quest Pro as a USB device, but `adb devices -l` returned an empty device list. Seeing the headset on USB does not mean its developer connection is enabled. The camera dry run has been stopped; its server, camera worker, and private temporary folder are gone. No arm movement was tested.

## The connection we are preparing

The Quest runs our page inside **Quest Browser**, where WebXR reads its controllers. A USB port mapping carries the page, camera pictures, and controller messages between the headset and the Mac. The Mac controls the arm through its separate Ethernet connection.

The desktop page is useful for watching the camera and status. It does not receive the Quest controllers just because the headset is plugged in. Tuesday's verified setup used Chrome and Quest Link on Windows; this Mac connection still needs an actual headset test.

Meta documents the [USB browser connection](https://developers.meta.com/vr/documentation/web/browser-remote-debugging/) and [headset setup through Developer Hub](https://developers.meta.com/vr/documentation/unity/ts-mqdh-device-setup/). The alternative phone setup uses the free Meta Horizon app: [iPhone/iPad](https://apps.apple.com/us/app/meta-horizon/id1366478176) or [Android](https://play.google.com/store/apps/details?id=com.oculus.twilight).

## Already installed

| Software | Version | Where |
|---|---|---|
| Android Platform Tools | 37.0.1 | `adb` at `/opt/homebrew/bin/adb` |
| Meta Quest Developer Hub | 6.5.2 | `/Applications/Meta Quest Developer Hub.app` |
| Teleop Python environment | Python 3.12.13 | `~/venvs/xarm` |

The app now explains the Mac/headset split instead of telling Mac users to turn on Link. Once VR runs, its status line reports whether each controller is tracked. The updated Mac instructions, camera picture, and 3D arm preview were verified in Codex's browser. That was a desktop page test, not a headset/controller test.

## Resume here

1. Finish Meta sign-in using the account that owns the headset. [Meta requires a verified developer account, developer-team membership, and an account holder aged 18 or older](https://developers.meta.com/vr/documentation/native/android/mobile-device-setup/). An adult account holder must handle that step. Enter passwords and verification codes only in Meta's own sign-in screen.
2. In Developer Hub, open **Device Manager → Set Up New Device**, choose Quest Pro, and follow the pairing steps. Keep the headset on and connected by its USB data cable. Allow USB debugging when the headset asks. The phone app's Developer Mode switch is another supported setup route.
3. Start a camera dry run from the repository root in a terminal:

   ```sh
   ~/venvs/xarm/bin/python Week01_2026-10-19/code/vr_teleop/vr_teleop.py --camera-admin
   ```

   Complete the native macOS prompt for the camera-only helper. Leave this terminal running.
4. In another terminal, run:

   ```sh
   ~/venvs/xarm/bin/python Week02_2026-10-26/code/quest_usb/connect_quest.py --wait 120
   ```

   This helper selects USB only, checks that the connected device is a Quest and the app is in dry-run mode, maps only port 8000, and opens `http://localhost:8000/` in Quest Browser. It never imports the robot SDK. The mapping and browser launch are not yet verified on the real headset.
5. Put on the headset, hold both controllers, and select **Enter VR**. Release the right grip, press **A**, then hold the grip and move your hand. Check that the on-screen target follows your hand. Try the left trigger for the simulated gripper. The real arm stays disconnected in this dry run.
6. Release the grip and exit VR. Stop the camera program with **Ctrl+C**. To remove the USB port mapping too, run `adb -d reverse --remove tcp:8000`.

After the dry run works, plan a separate live trial: clear the workspace, keep a spotter near the E-stop, and start with `--live --slow`. No live trial has been performed with the Mac setup.

## Checks saved with this work

Five hardware-free tests cover refusing another kind of USB device, refusing a live arm app, selecting USB explicitly, limiting the port mapping, and reporting browser-launch failure:

```sh
PYTHONDONTWRITEBYTECODE=1 ~/venvs/xarm/bin/python -m unittest discover -s Week02_2026-10-26/code/quest_usb -p test_connect_quest.py -v
```

Passing these checks does not verify physical controller tracking, headset rendering, connection delay, or real arm stopping behavior.
