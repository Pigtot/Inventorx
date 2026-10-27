# Lesson 5: VR Teleop Manual (Quest Pro on a Link cable)

**Teleop** (teleoperation) means you move your hand and the robot arm copies you.
This manual is how we run it: you wear the Quest Pro, hold the **right grip**, and the xArm's tool follows your hand. The D435 camera's picture floats in front of you in VR.

**Status (2026-10-25, later):** version 4 drove the real arm smoothly, including turning the gripper with a hand twist, with no errors. Version 5 also works on the real arm: the A button arms and disarms motion, and the 3D twin follows the arm. The HUD (E2), force feedback (E3), and camera calibration (H) were added after the last session: **not tested yet** on the real arm.

**Safety update (2026-10-26):** the audit fixes use a separate connection to send stop commands if the main program gets stuck. Setup checks the controller's replies and reads back the fence and speed cap before enabling motion. Tracking loss now requires a release and a fresh A press. A stop-timer fault, pause, arm error, or mode change ends the session: check the cause and restart. These changes have fake-hardware regression tests; **not tested yet on the real arm**.

**Controller buzz update (2026-10-26):** three new buzzes in E3: a buzz when VR starts (to check vibration works), an alarm when the arm stops on its own, and a "not now" double tick. Tested with fake controllers on the Mac in a dry run; **not tested yet in the headset**.

**VR view update (2026-10-26):** the 3D twin is now a real 3D model in VR (not a flat picture), the controllers show as ghosts with a "rubber band" while you drive, **X** switches the camera to a depth view, and the page and HUD were simplified. Tested with a fake headset on the Mac in a dry run; **not tested yet in the headset**. After updating, press **Ctrl + Shift + R** once on the page so Chrome drops its old copies of the files.

**Earlier:** the first version moved the real arm with the headset. During that test the arm reported an error, which switched it out of teleop mode. After that, the moves piled up in a queue, so **the arm lagged and kept moving after we let go**. Version 2 fixes this: it stops the instant you let go and quits on any arm error. Version 2 passed fake-hand tests on the PC; **not tested yet** on the real arm.
This replaces the Wi-Fi plan in Lesson 2 (Parts B and E): school Wi-Fi doesn't work for this, so **everything is connected by cable.**

Code: [`code/vr_teleop/`](code/vr_teleop/): `vr_teleop.py` (the program), `safety.py` (hand checks and the independent stop timer), `index.html` (the page and the VR loop), `vr_scene.js` (what you see in VR), `sim.js` (the 3D twin), `hud.js` (the HUD), `calib.py` (the camera calibration math), `meshes/` (UFACTORY's official xArm 6 and gripper CAD parts, from the `xArm-Developer/xarm_ros2` GitHub repository), and `lib/` (three.js 0.160.0, the 3D library).

---

## What plugs into what (all cables, no Wi-Fi)

| Device | Cable | Goes to |
|---|---|---|
| Meta Quest Pro | USB-C Link cable (USB 3) | the PC, straight into a laptop port (no hub) |
| xArm 6 control box | Ethernet | the PC's Ethernet port (PC = 192.168.1.100, arm = 192.168.1.217) |
| RealSense D435 | USB 3 | the PC |

```
Quest Pro ──Link cable──► Chrome on the PC (index.html, the VR page)
                              │ your hand, 30 times a second
                              ▼
D435 ──USB──► vr_teleop.py ──Ethernet──► xArm
       (newest picture only, back to the VR page)
```

---

## One-time setup (already done on the club PC)
1. **Meta Horizon Link** app installed. In it, **Settings → General → OpenXR Runtime** says *Meta Horizon Link is set as the active OpenXR Runtime*. (OpenXR is the standard that lets programs talk to a VR headset.)
2. **USB power saving off**, so Windows doesn't cut the Link connection. In PowerShell **as Administrator**:
   ```
   powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
   powercfg /setactive SCHEME_CURRENT
   ```
3. **Chrome** installed, and the xArm Python environment at `~/venvs/xarm`.

---

## Every session

### A. Safety first (before anything moves)
- [ ] **Two people.** The operator wears the headset. A **spotter keeps a hand on the E-stop**. In VR the operator can't see the real arm.
- [ ] Workspace clear: no people, bags, or loose blocks in the arm's reach.
- [ ] The operator stands **outside the arm's reach**, and the Link cable can't get caught by the arm.
- [ ] Everyone knows: **let go of the grip = the arm stops.**

### B. Put the arm in a safe start pose
The tool tip has to start **inside the safe workspace** (see "Safety limits" below), or the program refuses to start.
A good start: tool pointing down, about 400 mm in front of the base, 150–350 mm up.
Use teach mode (`05_teach_mode.py`) or UFactory Studio to move it there.

### C. Start the program
Open PowerShell in the `code\vr_teleop` folder:
```
cd "Week01_2026-10-19\code\vr_teleop"
```
1. **Dry run** (whenever something changed): the arm is never touched.
   ```
   ~/venvs/xarm/Scripts/python.exe vr_teleop.py
   ```
2. **Live** (the arm moves):
   ```
   ~/venvs/xarm/Scripts/python.exe vr_teleop.py --live
   ```
   It asks *"Spotter on the E-stop?"*. Press **Enter** only when the spotter is ready.
   The page and camera start right away, so the operator can get into VR while the spotter gets ready.
3. Leave this window open. Its status line shows what's happening:
   `following   tool x, y, z (mm): [404, 37, 187]  gripper open   camera: 30 fps`

### D. Enter VR
1. Plug in the Link cable and put on the headset.
2. In the headset: press the **Meta button** (flat button, right controller) → **Quick Settings** → **Link** → pick the PC → **Launch**.
3. On the PC, in **Chrome**, open `http://localhost:8000`.
4. (Optional) Start a recording (see section F).
5. **Face the same way as the arm's front.** Your "forward" becomes the arm's forward.
6. Click **Enter VR**. With the headset on you can't click, so a partner clicks, or you click and then put the headset on.
7. The camera window floats 1 m ahead, a little below eye level. The **3D twin** stands beside the window on your right, at 40% size and about the same distance, placed so no arm pose can cover the window: the official xArm 6 CAD model, posed live from the real joint angles and turned so its front matches yours. A blue dot shows where the arm is heading while you hold the grip, and the ring on its floor is the reach limit. You also see a ghost of each controller.
8. You should feel a short buzz in each hand. Spotter: the top of the PC page should say **Buzz L ok R ok**. If it says **unavailable**, or the operator feels nothing, the buzzes in E3 won't work in this browser. Everything else still works. The same line shows the VR frame rate and the work per frame (it should stay well under 11 ms).
9. **Release the right grip**, then press **A** to arm motion. After a tracking fault, release first, then make a new A press.

### E. Controls

| Do this | What happens |
|---|---|
| **Press A** | Arm or disarm motion. **It starts disarmed.** Release the right grip before arming. While disarmed, the grip, twist, and gripper do nothing. Tracking loss disarms motion; release, then press A again. A live stop-timer fault requires a program restart. |
| **Hold the right grip** | The arm's tool follows your hand's movement (position only; the tool keeps pointing down). |
| **Let go of the grip** | The program sends a stop and leaves the arm stopped until a fresh grip. Your hand can move freely, like lifting a computer mouse to reposition it. The old version's measured stop time was about 20 ms; the updated version's physical stop time is **not tested yet**. |
| **Twist your hand** (while holding the grip) | The gripper turns the same amount around the vertical axis (1:1). It always stays pointing straight down. Limit: ±170°. |
| **Left trigger click** | Close the gripper on a block. Click again to open it. |
| **Press B** | Turn the camera picture a quarter turn. Turn it until the arm's front is at the top. It's remembered. |
| **Press X** | Switch the camera window between the color and depth pictures (also the **Depth view** button on the PC page). |
| **Hold the Meta button** | Re-center the view in front of you. |

**Curved response (not linear).** The farther your hand goes from where you gripped, the bigger each centimeter counts:

| Hand moves | Arm moves |
|---|---|
| 2 cm | 1 cm (fine, for lining up on a block) |
| 10 cm | 8 cm |
| 20 cm | 32 cm |
| 30 cm or more | 3 times your hand (for range) |

To make a long trip: grip, reach, let go, bring your hand back, and grip again.

**Your right controller's ghost** shows what the arm will do: white = motion off, cyan = armed, bright cyan = the arm is following you, amber = at a limit. While it follows you, a thin **rubber band** runs from where you gripped to your hand. The longer the band, the farther the arm moves.

**First live test:** hold the grip and move your hand only **2–3 cm**. Check that the arm goes the same direction (forward, left, up) before making bigger moves.

**Grabbing a Jenga block:**
1. Open the gripper (left trigger).
2. Move above the block.
3. Twist your hand until the gripper fingers line up across the block's narrow side.
4. Go down slowly. Near the table the arm slows to 50 mm/s on its own.
5. Close the gripper (left trigger), then lift.

### E2. The HUD (heads-up display)
The camera picture has a simple overlay (in VR, on the PC page, and in recordings):
- **Top left:** the status, like `Motion off · Press A` or `Following your hand`. Cyan = motion armed, amber = `PC link lost`.
- **Top right:** whether the camera is calibrated.
- **Landing ring:** marks **exactly where the gripper will touch down**, with `↓ 42 mm` = how far the gripper tip is above that spot. It turns white when closer than 40 mm and amber while holding a block. It needs the camera calibration (section H). Until then a dashed ring says `Calibrate the camera`.
- **Small diamond:** the gripper tip itself, if it's in the picture.
- **Left scale:** the tool's height, from the floor limit (amber line) up to the ceiling.
- **Right:** gripper opening (%) and which way the gripper is turned.
- **Bottom:** X, Y, Z and the 6 joint angles.
- **Amber warning:** the limit you're pushing against, like `At reach limit`.
- **Depth view (X):** the picture is colored by distance from the camera: red at 15 cm, through yellow and green, to blue at 70 cm. Black = no reading. A key at the bottom says so.

### E3. Force feedback (controller shake)
The arm has no force sensor, so the controllers *simulate* force from what the program knows:

| You feel | Which hand | Meaning |
|---|---|---|
| Steady buzz | right | You're pushing the arm against a safety limit (a "virtual wall"). |
| Buzz that grows stronger | right | The gripper is within 40 mm of a surface below it (from the depth camera). Stronger = closer. |
| Strong "clunk" | left | The gripper just closed on something. |
| Light hum every ~0.4 s | left | The gripper is holding something. |
| Short tick | left / right | Gripper click registered / motion armed or disarmed. |
| **Long, strong buzz** | both | **The arm stopped on its own:** tracking was lost while motion was armed, the PC link was lost, or the program stopped. Let go and look at the arm. |
| 2 quick ticks | right | "Not now": you gripped while motion is OFF (press A first), or pressed A while still gripping (let go first). |
| Short buzz when VR starts | both | Vibration check (step D8). |

Vibration depends on the browser. The Quest Browser supports it ([Meta's docs](https://developers.meta.com/horizon/documentation/web/webxr-pro-controller)). We don't know yet whether Chrome on the PC passes it through Link, and step D8 checks that.

### F. Recording (optional)
**Record the camera view (easiest):** the PC page's **Camera** card shows the camera with the HUD, turned the same as in VR.
1. Click **Record camera**. It works in or out of VR.
2. Click **Stop and save** when done.
3. It saves to this week's `media/` folder as `d435_<date>_<time>.mp4` (640×440, 30 fps, medium quality, about 11 MB per minute).

**Record the headset view instead** (what the operator sees, including the 3D twin):
1. Open Meta's mirror window, which shows the headset view on the PC:
   ```
   & "C:\Program Files\Meta Horizon\Support\oculus-diagnostics\OculusMirror.exe"
   ```
2. On the page, click **Record headset**. In Chrome's picker, choose the **Window** tab, then **Oculus Mirror**.
3. Do your session. The video saves by itself when you leave VR, or when you click **Stop and save**.
4. Videos go to this week's `media/` folder as `vr_<date>_<time>.mp4` (720p, 30 fps, about 20 MB per minute).

### G. Shut down
1. Let go of the grip.
2. In the PowerShell window press **Ctrl + C**. The program sends a stop before closing the web server, then restores the arm's safety settings. The arm stays in the stopped state. (The gripper stays as it is, so it won't drop a block.)
3. Take off the headset.

### H. Camera calibration (do once; redo if the camera mount moves)
The D435 is bolted beside the gripper, not in its center, so the picture's middle is **not** where the gripper lands. Calibration measures exactly where the camera sits and how it's turned relative to the gripper tip. It's saved in `code/vr_teleop/camera_calibration.json`.

**How the math works:**
1. Touching a dot with the gripper tip tells us where the dot is in the **arm's** coordinates.
2. Each time you click the dot in the picture, the depth camera turns pixel + depth into the dot's 3D spot in **camera** coordinates. The arm's pose tells us where the same dot is in **gripper** coordinates.
3. With 4 or more of these pairs, the **Kabsch method** finds the one rotation and shift that best line up the camera's numbers with the gripper's. That rotation and shift *is* the camera's position on the gripper.
4. After that, the program follows the gripper's straight-down line until the depth camera says it hits a surface. That's the landing reticle.

On made-up test data with realistic errors, this found the camera's position within about 2 mm and its angle within half a degree.

**Steps (two people: operator in VR, spotter at the PC page):**
1. Put a small dot (pen mark or sticker) on the table in front of the arm.
2. Operator: drive the gripper tip down until it **just touches** the dot. Spotter: click **Record touch**.
3. Operator: lift up and let go. Spotter: **click the dot** in the HUD picture on the PC page.
4. Repeat step 3 from at least 4 different spots. Change the **height** (about 100–300 mm above the table) and the **turn** each time.
5. Spotter: click **Solve**. The program accepts at least 4 points with enough spread in two directions and a fit error of at most 5 mm. Repeated, nearly straight-line, invalid, or poor-fitting samples are rejected; the previous saved calibration is kept. If rejected, click **Start over**, move sideways as well as up, and click more carefully. Fit error is a check on these samples, not a guarantee of real-world accuracy.

---

## Safety limits built into the code
The safe workspace for the tool tip is in the arm's coordinates: X = forward, Y = left, Z = up, and 0 = the base.

| Safety layer | Value | Where to change it |
|---|---|---|
| Floor (lowest tool tip) | **z = −75 mm** (our table is below the base's zero) | `FLOOR` in `vr_teleop.py` |
| Slow zone near the floor | within 75 mm of the floor: max 50 mm/s | `SLOW_ZONE`, `SLOW_SPEED` |
| Ceiling | z = 450 mm | `CEILING` |
| Reach | at most 560 mm from the base (the arm's full reach is about 700) | `REACH` |
| Too close to the base | at least 200 mm out from its center line | `NEAR` |
| Front only | X at least 100 mm, so the arm stays in front of its base, away from the operator | `FRONT` |
| Top speed | 150 mm/s | `SPEED` |
| Gripper turn | stays within ±170°, so the wrist never spins the long way around | `YAW_LIMIT` |
| **The arm's own fence** | x 50 to 650, y ±650, z −105 to 520 mm. The arm's controller stops it if the tool leaves this box, even if our code has a bug. | `FENCE` |
| **The arm's own speed cap** | 250 mm/s while teleop runs | `ARM_MAX_SPEED` |
| Motion switch (A) | starts OFF; nothing moves until the operator presses A; lost contact turns it OFF | `motion_on` |
| Let go = stop | sends a stop; a fresh grip is needed to become ready again | `ArmWatchdog.stop()` in `safety.py` |
| Dead-man switch | no hand message or no control-loop progress for 0.3 s while moving: a separate connection sends a stop; restart required | `ArmWatchdog` in `safety.py` |
| Tracking glitch | a hand jump over 25 cm or a missing/invalid pose disarms motion; release, then press A again | `HandInput` in `safety.py` |
| Arm error, pause, or wrong mode | checked by the watchdog and before every movement command; the session ends | `ArmWatchdog.check()` |
| Safety setup failure | nonzero SDK replies or mismatched fence/speed readback abort startup | `connect_arm()` |
| Collision detection | the arm's own setting (ours is sensitivity 3); the program warns if it's off | UFactory Studio |
| Who can send hand moves | only this PC (`127.0.0.1`) | no change needed |
| Copies running at once | one. A second copy says "Port 8000 is busy" and quits. | no change needed |

## Settings you can change

| Setting | File | What it does |
|---|---|---|
| `FINE`, `FAST`, `FAR` | `vr_teleop.py` | The curve: gain for small moves (0.5), gain for big moves (3.0), and the hand distance where it's fully fast (300 mm). |
| `CAM_W, CAM_H, CAM_FPS = 640, 360, 30` | `vr_teleop.py` | Camera picture in VR. Lower = lighter, higher = sharper. We measured `848, 480, 60` working too. |
| `SCREEN_SIZE`, `SCREEN_DISTANCE` | `index.html` | Size of the floating picture and how far away it is (meters). |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Link keeps dropping | Check that USB power saving is off (one-time setup). Unplug and replug the cable. Try another USB-C port on the laptop (not a hub). |
| Page says "VR not found" | Start Link in the headset first (section D, step 2), then refresh the page. |
| "Port 8000 is busy" | Another copy is already running. Press Ctrl + C in that window first. |
| Status line says `camera: 0 fps` | Check the D435 USB cable. The program restarts the camera by itself every 2 s. |
| HUD says "PC link lost" | The PowerShell program stopped or crashed. Check its window. |
| The page looks broken or blank after an update | Press **Ctrl + Shift + R** once, so Chrome loads the new files. |
| HUD says "Following your hand" but the arm doesn't move | Is it a dry run (no `--live`)? Did the spotter press Enter at the safety question? Look for an error code in the window. |
| "The arm reported error ..." and the program quit | Look the error up in UFactory Studio and clear it there. Then restart the program. |
| "Stop timer expired", "Control loop stalled", or "Hand command expired" | Keep the grip released. Check the headset link and the Python window, then restart the program. A fresh A press does not clear a watchdog fault. |
| "Tracking glitch" but the program is still running | Wait for good tracking. Release the grip, then press A again before gripping. |
| The arm keeps moving after you let go | It shouldn't in version 2. **Press the E-stop**, then tell us what the window says. |
| "The tool is outside the safe workspace" | Move the arm inside it (section B) with teach mode, then restart. |
| Picture sideways or upside down | Press **B** until the arm's front is at the top. |
| The arm goes the wrong direction | Let go! Stop with Ctrl + C. Check that you faced the arm's front when you clicked Enter VR. |

---

## How it works (short version)
1. **Reading your hand:** the VR page uses **WebXR**, the browser feature for VR. Every frame it reads the right controller's position and whether the grip is pressed.
2. **Talking to the PC:** about 30 times a second, the page sends that to `vr_teleop.py`, which runs a tiny web server on the same PC.
3. **Moving the arm:** when you press the grip, the program remembers where your hand and the tool are. After that, it takes your hand's movement, converts it to the arm's directions and to millimeters, and bends it with the curve. It adds that to the tool's start spot and pulls the result back inside all the workspace limits together. It checks **mode 7** before every command and rejects a command if the hand changes while an SDK call is running. A separate thread and connection can send a stop even while the main SDK connection is waiting for a reply. The SDK's automatic pause and queue waits are disabled. Stop commands still depend on the PC, network, and controller working; the spotter's physical E-stop remains necessary.
4. **Camera:** the program keeps only the newest D435 picture. The page asks for the next one only after it gets the last one, so lag never piles up. Pictures stay uncompressed, because everything is on one PC.

## Check yourself
1. Why does the arm stop if the VR page freezes or the cable comes out?
2. Why does the arm's own fence matter if our code already has limits?
3. What does letting go of the grip let you do, and why is it like lifting a mouse?
4. Why is the response curved instead of straight (linear)?
5. Why do we face the arm's front when we click Enter VR?
