# Week 2: Oct 26 – Nov 1, 2026

- **Monday:** Fixed eight problems that a code review found in the arm control and camera code. Added controller buzz for safety stops.
- **Tuesday morning:** Put a real 3D model of the arm into VR, added controller ghosts and a depth view, and made the page and HUD simpler.
- **Tuesday afternoon:** The headset froze after Enter VR. We tracked it down and got the VR view working over the Link cable.
- **Wednesday:** Connected the Mac to the arm and got D435 color/depth capture working at 640×480 and 15 fps. Isolated the Mac camera driver in its own process. Installed the Quest USB tools and Developer Hub; controller setup paused at Meta sign-in. The dry-run server and camera helper are stopped.

The VR code still lives in Week 1's folder: [`code/vr_teleop/`](../Week01_2026-10-19/code/vr_teleop/).

## What we learned

1. **Measure each step before guessing.** A timing log showed our own code took 30 ms to start VR, and Chrome took 33 seconds. That stopped us from chasing the wrong things.
2. **A tiny test page splits the problem in half.** A page that only paints the headset blue worked, so the problem was in our page. The difference was the graphics mode: WebGL 1 works over Link, and WebGL 2 got no pictures.
3. **Check each connection and its supported settings.** The reconnected D435 reports USB 2.1. Its color sensor did not offer the old 640×360 mode; 640×480 at 15 fps worked with camera-only administrator access.

On the Windows PC, selecting the high-performance graphics chip for Chrome also remains part of the setup notes.

## What works

| What | Does it work? | Notes |
|---|---|---|
| VR view in the Quest Pro over the Link cable | Yes | About 70 frames a second |
| Camera picture in VR on the Windows PC | Yes | 30 frames a second; this does not establish Mac camera support |
| Mac reaches the real arm over Ethernet | Yes | Adapter `en11`: 192.168.1.100 / 255.255.255.0, no router |
| Mac dependencies and web app | Yes | Python 3.12 environment at `~/venvs/xarm`; dry run verified, then stopped on pause |
| Arm fault cleared while stopped | Yes | Wednesday's final read: error 0, state 4; no movement commands sent |
| D435 capture on the Mac | Yes | Color and aligned depth at 640×480, 15 fps; verified through the app's HTTP endpoints |
| Mac desktop camera page and 3D preview | Yes | Inspected in Codex's browser; does not verify headset rendering |
| Quest controllers connected to the Mac | Not yet | USB tools and Developer Hub installed; paused at Meta sign-in before headset authorization |
| Moving the real arm with this week's version | Not yet | Use `--live --slow` for the first try |
| Controller buzz | No | Chrome over Link can't make the controllers vibrate |
| Starting VR quickly | No | Enter VR takes about 33 seconds |

## Still broken

- Enter VR takes about 33 seconds to start.
- The controllers can't buzz, so the safety-stop alarm needs another way to warn you.
- Mac headset rendering and controller input still need a real test. The USB developer connection did not appear; resume at the [Meta sign-in and headset setup steps](code/quest_usb/README.md). Tuesday's verified Link setup was on Windows.
- Real camera unplug/crash behavior is not yet verified. Normal shutdown worked; the separate camera worker passed nine tests with generated frames. See the [Mac camera notes](code/macos_camera/README.md).

## Daily logs

- [Tuesday, Oct 27: Getting the VR view to show up in the headset](2026-10-27_Tue.md)
- [Wednesday, Oct 28: Mac setup and working camera capture](2026-10-28_Wed.md)

## Words to know

| Word | Meaning |
|---|---|
| WebGL | The part of the browser that draws 3D graphics. WebGL 1 is the older, simpler version. |
| Link | Meta's way of running VR from a PC through a USB cable |
| Frames per second | How many new pictures the headset shows each second. VR needs about 72. |
