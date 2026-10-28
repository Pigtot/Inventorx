# Week 2: Oct 26 – Nov 1, 2026

- **Monday:** Fixed eight problems that a code review found in the arm control and camera code. Added controller buzz for safety stops.
- **Tuesday morning:** Put a real 3D model of the arm into VR, added controller ghosts and a depth view, and made the page and HUD simpler.
- **Tuesday afternoon:** The headset froze after Enter VR. We tracked it down and got the VR view working over the Link cable.

The VR code still lives in Week 1's folder: [`code/vr_teleop/`](../Week01_2026-10-19/code/vr_teleop/).

## What we learned

1. **Measure each step before guessing.** A timing log showed our own code took 30 ms to start VR, and Chrome took 33 seconds. That stopped us from chasing the wrong things.
2. **A tiny test page splits the problem in half.** A page that only paints the headset blue worked, so the problem was in our page. The difference was the graphics mode: WebGL 1 works over Link, and WebGL 2 got no pictures.
3. **Laptops with two graphics chips can pick the weak one.** Chrome was drawing on the Intel chip. For VR, set Chrome to "High performance" in Windows graphics settings.

## What works

| What | Does it work? | Notes |
|---|---|---|
| VR view in the Quest Pro over the Link cable | Yes | About 70 frames a second |
| Camera picture in VR | Yes | 30 frames a second |
| Moving the real arm with this week's version | Not yet | Use `--live --slow` for the first try |
| Controller buzz | No | Chrome over Link can't make the controllers vibrate |
| Starting VR quickly | No | Enter VR takes about 33 seconds |

## Still broken

- Enter VR takes about 33 seconds to start.
- The controllers can't buzz, so the safety-stop alarm needs another way to warn you.

## Daily logs

- [Tuesday, Oct 27: Getting the VR view to show up in the headset](2026-10-27_Tue.md)

## Words to know

| Word | Meaning |
|---|---|
| WebGL | The part of the browser that draws 3D graphics. WebGL 1 is the older, simpler version. |
| Link | Meta's way of running VR from a PC through a USB cable |
| Frames per second | How many new pictures the headset shows each second. VR needs about 72. |
