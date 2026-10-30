"""
vr_teleop.py: VR teleop with the D435 camera. Hold the right controller's grip and the arm's tool follows
your hand (position only: the tool keeps pointing the same way). Let go and it stops right there.
The response is curved: small hand moves give fine control, big hand moves cover much more ground.
VR shows the D435 picture and the arm's live coordinates. The page can also record the headset view.

How the pieces talk (all by cable):
    Quest Pro --(Link cable)--> Chrome on this PC runs index.html (WebXR)
    index.html --(30 messages per second)--> this script --(Ethernet)--> xArm
    D435 --(USB)--> this script --(newest picture only)--> index.html

SAFETY: run it first WITHOUT --live (a dry run: it only shows where the arm WOULD go).
With --live the arm really moves: clear the workspace, and a spotter keeps a hand on the E-stop.
Safety layers: workspace limits in this script, the arm's own fence and speed cap, stop on let go,
a dead-man timer, and a tracking-glitch check (see Lesson 5).
Run it like this:
    ~/venvs/xarm/Scripts/python.exe vr_teleop.py          (dry run)
    ~/venvs/xarm/Scripts/python.exe vr_teleop.py --live --slow   (first live test: 50 mm/s cap)
    ~/venvs/xarm/Scripts/python.exe vr_teleop.py --live   (the arm moves)
On the Mac, use ~/venvs/xarm/bin/python vr_teleop.py --camera-admin for a dry run.
macOS asks for camera-only USB permission. The web server and arm control stay unprivileged.
Then open http://localhost:8000 in Chrome on this PC. Press Ctrl+C here to quit.
"""
import json
import math
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

import calib   # calib.py, next to this file: camera-to-gripper calibration math
from safety import (ArmError, ArmWatchdog, COMMAND_TIMEOUT, CommandCancelled, HEADSET_TIMEOUT, HandInput,
                    SafetyError, Stalled, checked, reading)

ARM_IP = "192.168.1.217"  # from the label on our control box
MOVE_ARM = "--live" in sys.argv   # without --live, the arm is never touched
SLOW_TEST = "--slow" in sys.argv   # first live test: lower both the requested speed and the controller's cap

# Curved response: arm move = hand move x gain, and the gain grows the farther you reach from where you gripped.
FINE = 0.5      # gain for small moves (precise): 2 cm of hand = 1 cm of arm
FAST = 3.0      # gain for big moves (range): 30 cm of hand = 90 cm of arm
FAR = 300       # mm of hand movement where the gain reaches FAST
SPEED = 50 if SLOW_TEST else 150   # mm/s: the fastest this script lets the tool move

# Safe workspace for the tool tip, in the arm's coordinates (mm): X = forward, Y = left, Z = up, 0 = base.
FLOOR = -75     # lowest the tip may go (our table is below the base's zero)
SLOW_ZONE = 75  # within this many mm above the floor, the tool slows down...
SLOW_SPEED = 25 if SLOW_TEST else 50 # ...to this speed (mm/s), so touching down on a block is gentle
CEILING = 450   # highest
REACH = 560     # farthest from the base (full reach is about 700 mm; we keep a margin)
NEAR = 200      # closest to the base's center line, so the arm can't fold into itself
FRONT = 100     # X stays above this: the arm stays in front of its base, away from the operator
# Second layer, checked by the arm's own controller even if this script has a bug:
FENCE = [650, 50, 650, -650, 520, -105]   # x_max, x_min, y_max, y_min, z_max, z_min (mm): leaving it = arm stops
ARM_MAX_SPEED = 50 if SLOW_TEST else 250   # mm/s: the arm controller's own speed cap
GRIPPER_OPEN, GRIPPER_CLOSED = 850, 0   # xArm Gripper positions: 850 = wide open, 0 = closed (it stops on the block)
GRIPPER_SPEED = 3000
YAW_LIMIT = 170   # degrees: the gripper's turn stays within -170..170, so it never spins the long way around

# Our Mac connection reports USB 2.1: its color sensor offers 640x480, not 640x360.
CAM_W, CAM_H, CAM_FPS = (640, 480, 15) if sys.platform == "darwin" else (640, 360, 30)
# Depth view: distances from DEPTH_NEAR to DEPTH_FAR (mm) get colors red, yellow, green, cyan, blue.
DEPTH_NEAR, DEPTH_FAR = 150, 700
DEPTH_COLORS = np.array([[255, 60, 40], [255, 220, 0], [60, 220, 90], [0, 200, 255], [40, 70, 255]])
DEPTH_LUT = np.stack([np.interp(np.linspace(0, 4, 256), range(5), DEPTH_COLORS[:, c]) for c in range(3)],
                     axis=1).astype(np.uint8)   # 256 colors blended between those 5
PORT = 8000
HERE = Path(__file__).resolve().parent
MEDIA = HERE.parents[1] / "media"   # this week's media/ folder
CALIB_FILE = HERE / "camera_calibration.json"   # where the D435 sits on the gripper (made by the calibration steps)
SLOW_STEP = 0.1   # s: a loop step slower than this gets noted, so a "Control loop stalled" stop names its cause
# The controller answers the first move after "ready" slowly (we measured 359 ms). That move goes to where the
# tool already is, so it may take this long (s). Every other move keeps the normal 0.3 s limit.
FIRST_MOVE_ALLOW = 1.0

hands = HandInput()   # validates headset messages even while the control loop is busy
report = {}   # what the VR page shows (status and live coordinates), rebuilt 30 times a second
camera = {"data": None, "id": 0, "fps": 0,    # newest D435 picture (raw RGB bytes) and its number
          "depth": None, "intr": None}         # its depth picture (mm, lined up with the color) and lens numbers
new_picture = threading.Condition()   # lets the web server wait until a newer picture arrives
camera_stop = threading.Event()
T_tool_cam, calib_info = calib.load(CALIB_FILE)   # None until the camera is calibrated
calibration = {"mark": None, "pairs": []}       # calibration in progress: the dot (base mm) and the point pairs
arm, target, yaw = None, [300.0, 0.0, 300.0], 0.0   # set for real once the arm is on
watchdog = None   # the stop timer, once the arm is on


class Server(ThreadingHTTPServer):
    # On Windows, "reuse address" lets a second copy of this script share the port, and then both would get
    # your hand. Turn it off there, so a second copy fails to start instead.
    allow_reuse_address = sys.platform != "win32"

    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], ConnectionError):   # a page reload drops a connection: not worth a scary message
            super().handle_error(request, client_address)


class Handler(SimpleHTTPRequestHandler):
    """Sends index.html to Chrome, sends camera pictures (/camera), receives hand poses (/pose) and
    answers with the live coordinates, and saves finished videos (/video.mp4)."""
    protocol_version = "HTTP/1.1"   # reuse one connection instead of opening 30 new ones a second

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")   # Chrome always checks for newer files, so updates never mix with old ones
        super().end_headers()

    def do_GET(self):
        if self.path == "/status":   # read-only: the live coordinates, for the PC page's live view
            reply = json.dumps(report).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)
            return
        if not self.path.startswith("/camera"):
            return super().do_GET()   # a normal file, like index.html
        query = parse_qs(urlsplit(self.path).query)
        after = int(query.get("after", ["0"])[0])   # the picture number Chrome already has
        with new_picture:   # wait (up to 1 s) for a newer picture, so Chrome never gets the same one twice
            new_picture.wait_for(lambda: camera["id"] > after, timeout=1)
            data, depth, number = camera["data"], camera["depth"], camera["id"]
        if query.get("view") == ["depth"] and depth is not None:
            data = depth_picture(depth)   # made only when someone is looking at it
        if data is None:
            self.send_response(503)   # 503 = "not ready": no camera picture yet
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Picture", f"{number} {CAM_W} {CAM_H}")   # number, width, height
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        reply = b""
        if self.path == "/pose":
            msg = json.loads(body)
            hands.update(msg)
            reply = json.dumps(report).encode()   # answer with the live coordinates for the VR display
        elif self.path.startswith("/calib/"):   # calibration steps, from the buttons on the PC page
            reply = json.dumps(calibrate(self.path[len("/calib/"):], json.loads(body or b"{}"))).encode()
        elif self.path in ("/video.mp4", "/video.webm", "/d435.mp4", "/d435.webm"):   # headset mirror or D435 view
            MEDIA.mkdir(exist_ok=True)
            name = "d435" if self.path.startswith("/d435") else "vr"
            out = MEDIA / f"{name}_{datetime.now():%Y-%m-%d_%H%M%S}{Path(self.path).suffix}"
            out.write_bytes(body)
            print(f"\nSaved video: {out} ({len(body) / 1e6:.1f} MB)")
        elif self.path == "/log":   # debug timing from the page (temporary), kept in vr_debug.log
            with open(HERE / "vr_debug.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S.%f}"[:12] + "  " + body.decode() + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass   # don't print a line for every message


def note_slow(step, seconds):
    """Print a slow step and add it to vr_debug.log."""
    line = f"slow step: {step} took {seconds * 1000:.0f} ms"
    print(f"\n{line}")
    with open(HERE / "vr_debug.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%H:%M:%S.%f}"[:12] + "  " + line + "\n")


@contextmanager
def timed(step):
    """Time one step of the control loop. It is noted even if the step fails (a stall usually ends in an error)."""
    start = time.monotonic()
    if watchdog:
        watchdog.step = step   # so a stall stop can say which step it caught
    try:
        yield
    finally:
        if watchdog:
            watchdog.step = "between steps"
        took = time.monotonic() - start
        if took > SLOW_STEP:
            note_slow(step, took)


def hand_to_arm(dx, dy, dz):
    """Turn a hand move in VR (meters; x = right, y = up, -z = forward) into an arm move
    (mm; X = forward, Y = left, Z = up). Face the same way as the arm's front when you enter VR."""
    return -dz * 1000, -dx * 1000, dy * 1000


def curve(move):
    """Curved response: small hand moves stay small (precise), big ones grow (range)."""
    distance = math.hypot(*move)
    gain = FINE + (FAST - FINE) * min(distance / FAR, 1) ** 2
    return [m * gain for m in move]


def keep_safe(x, y, z):
    """Pull a target back inside the safe workspace. Also returns which limit it hit ("" = none)."""
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise SafetyError("Non-finite movement target.")
    limit = ""
    if not FLOOR <= z <= CEILING:
        z, limit = min(max(z, FLOOR), CEILING), "height limit"
    if x < FRONT:
        x, limit = FRONT, "front limit"
    out = math.hypot(x, y)   # how far out from the base's center line
    farthest = math.sqrt(REACH ** 2 - z ** 2)   # higher up, the arm can't reach as far out
    if out < NEAR:
        x, y, limit = x * NEAR / out, y * NEAR / out, "reach limit"
    elif out > farthest:
        # Shrinking radially can push X behind FRONT. In that case, stay on
        # the front plane and shrink Y to the intersection with the reach circle.
        k = farthest / out
        x, y, limit = x * k, y * k, "reach limit"
        if x < FRONT:
            x = FRONT
            y = math.copysign(math.sqrt(max(0.0, farthest ** 2 - FRONT ** 2)), y)
    return [x, y, z], limit


def camera_loop():
    """Keep only the newest D435 color picture in `camera`, plus its depth picture. The color stays raw
    (no JPEG): everything is on this one PC, so skipping compression saves time on both ends."""
    if sys.platform == "darwin":
        from camera_bridge import receive_camera
        receive_camera(camera, new_picture, camera_stop, CAM_W, CAM_H, CAM_FPS,
                       admin="--camera-admin" in sys.argv)
        return
    try:
        import pyrealsense2 as rs
    except ImportError:
        print("\nNo pyrealsense2 here, so VR shows no camera.")
        return
    config = rs.config()
    config.enable_stream(rs.stream.color, CAM_W, CAM_H, rs.format.rgb8, CAM_FPS)
    config.enable_stream(rs.stream.depth, CAM_W, CAM_H, rs.format.z16, CAM_FPS)
    align = rs.align(rs.stream.color)   # line the depth picture up with the color picture, pixel for pixel
    while True:   # if the camera hiccups, turn it off and on again
        pipeline = rs.pipeline()
        try:
            profile = pipeline.start(config)
            to_mm = profile.get_device().first_depth_sensor().get_depth_scale() * 1000   # depth units -> mm
            lens = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
            camera["intr"] = (lens.fx, lens.fy, lens.ppx, lens.ppy)   # focal lengths and picture center (pixels)
            count, t0 = 0, time.time()
            while True:
                frames = align.process(pipeline.wait_for_frames(2000))
                picture = frames.get_color_frame()
                camera["depth"] = np.asanyarray(frames.get_depth_frame().get_data()) * np.float32(to_mm)
                with new_picture:
                    camera["data"] = bytes(picture.get_data())
                    camera["id"] += 1
                    new_picture.notify_all()   # wake up Chrome's waiting request
                count += 1
                if time.time() - t0 >= 1:
                    camera["fps"], count, t0 = count, 0, time.time()
        except RuntimeError as e:
            camera["fps"] = 0
            print(f"\nCamera problem ({e}). Trying again in 2 s...")
            try:
                pipeline.stop()
            except RuntimeError:
                pass
            time.sleep(2)


def depth_picture(depth):
    """The depth picture (mm) as raw RGB bytes, the same format as a color picture. No reading (0 mm) = black."""
    step = np.clip((depth - DEPTH_NEAR) * (255 / (DEPTH_FAR - DEPTH_NEAR)), 0, 255).astype(np.uint8)
    rgb = DEPTH_LUT[step]
    rgb[depth == 0] = 0
    return rgb.tobytes()


def tool_pose():
    """The tool's pose now: x, y, z (mm), roll, pitch, yaw (deg). Dry run: where it would be."""
    return list(arm.position) if arm else [*target, 180.0, 0.0, yaw]


def calibrate(step, msg):
    """The calibration steps (see Lesson 5). Each returns {"ok": ..., "say": what to tell the user}."""
    global T_tool_cam, calib_info
    pairs = calibration["pairs"]
    if step == "touch":   # the gripper tip is touching the dot: remember where the dot is (base coordinates)
        calibration["mark"], calibration["pairs"] = tool_pose()[:3], []
        return {"ok": True, "say": "Touch recorded. Now click the dot from 4 or more spots."}
    if step == "click":   # the dot, seen by the camera from where the arm is now
        if calibration["mark"] is None:
            return {"ok": False, "say": "Record a touch first."}
        if camera["depth"] is None:
            return {"ok": False, "say": "No camera picture yet."}
        d = calib.depth_at(camera["depth"], msg["u"], msg["v"])
        if not d:
            return {"ok": False, "say": "No depth there. Lift the arm a little and click again."}
        in_cam = calib.deproject(msg["u"], msg["v"], d, camera["intr"])
        in_tool = (np.linalg.inv(calib.pose_matrix(*tool_pose())) @ [*calibration["mark"], 1])[:3]
        pairs.append((in_cam, in_tool))
        return {"ok": True, "say": f"Point {len(pairs)} saved ({d:.0f} mm away). Move and click again."}
    if step == "solve":
        try:
            T, rms = calib.solve(pairs)
        except (ValueError, np.linalg.LinAlgError) as exc:
            return {"ok": False, "say": f"Rejected: {exc} The saved calibration is kept."}
        info = calib.save(CALIB_FILE, T, rms, len(pairs))
        T_tool_cam, calib_info = T, info
        return {"ok": True, "say": f"Calibrated from {len(pairs)} points. Error {rms:.1f} mm."}
    if step == "reset":
        calibration.update(mark=None, pairs=[])
        return {"ok": True, "say": "Cleared. The saved calibration is kept."}
    return {"ok": False, "say": f"Unknown step {step}."}


def connect_arm(factory=None, confirm=input):
    """Connect, ask the spotter, then turn on the arm with its own fence and speed cap.
    Returns the command connection, stop connection, and old safety settings."""
    if factory is None:
        from xarm.wrapper import XArmAPI   # only needed when the arm really moves
        factory = XArmAPI
    arm = stop_arm = old = None
    try:
        # Disable the SDK's implicit pause/queue waits. The watchdog has its own
        # command socket, so an SDK response timeout cannot block a stop request.
        arm = factory(ARM_IP, check_is_pause=False, check_cmdnum_limit=False)
        stop_arm = factory(ARM_IP, enable_report=False, check_is_pause=False, check_cmdnum_limit=False)
        stop_arm.set_timeout(COMMAND_TIMEOUT)
        print("\nLIVE: the arm WILL move, but only while motion is armed and the grip is held.")
        confirm("SPOTTER: hand on the E-stop and workspace clear? Press Enter to set up the arm (Ctrl+C = quit)...")
        checked(stop_arm.set_state(4), "Stop before setup")
        x, y, z = reading(arm.get_position(), "Read start position")[:3]
        if keep_safe(x, y, z)[1]:
            raise SafetyError("Tool is outside the safe workspace. Move it inside first (Lesson 5).")
        if arm.collision_sensitivity == 0:
            print("WARNING: collision detection is OFF on the arm. Turn it on in UFactory Studio.")
        old = reading(arm.get_reduced_states(), "Read old safety settings")
        if len(old) < 7:
            old = None
            raise SafetyError("The controller did not return complete safety settings.")
        checked(arm.clean_error(), "Clear old arm error")
        checked(stop_arm.set_state(4), "Keep arm stopped during setup")
        checked(arm.set_reduced_max_tcp_speed(ARM_MAX_SPEED), "Set speed cap")
        checked(arm.set_reduced_tcp_boundary(FENCE), "Set fence boundary")
        checked(arm.set_reduced_mode(True), "Enable reduced mode")
        checked(arm.set_fence_mode(True), "Enable fence")
        current = reading(arm.get_reduced_states(), "Verify safety settings")
        if (len(current) < 7 or current[0] != 1 or current[5] != 1
                or list(current[1]) != FENCE or not math.isclose(current[2], ARM_MAX_SPEED)):
            raise SafetyError("The controller's safety settings do not match the requested fence and speed cap.")
        checked(arm.motion_enable(True), "Enable motors")
        checked(arm.set_mode(7), "Select teleop mode")
        checked(stop_arm.set_state(4), "Keep arm stopped until a fresh grip")
        checked(arm.set_gripper_mode(0), "Set gripper mode")
        checked(arm.set_gripper_enable(True), "Enable gripper")
        checked(arm.set_gripper_speed(GRIPPER_SPEED), "Set gripper speed")
        time.sleep(0.5)   # allow the report stream to reflect the new mode
        if arm.mode != 7:
            raise SafetyError("The arm did not enter teleop mode.")
        arm.set_timeout(COMMAND_TIMEOUT)
        return arm, stop_arm, old
    except BaseException:
        if stop_arm:
            try:
                checked(stop_arm.set_state(4), "Stop failed setup")
                if old is not None:
                    restore(stop_arm, old)
            except Exception as exc:
                print(f"Could not restore setup: {exc} Check UFactory Studio; keep the E-stop ready.")
        if arm:
            arm.disconnect()
        if stop_arm:
            stop_arm.disconnect()
        raise


def restore(arm, old):
    """Restore safety settings while leaving the arm stopped, never ready to resume."""
    checked(arm.set_state(4), "Stop before restoring settings")
    steps = [(arm.set_mode, 0, "Restore position mode"), (arm.set_fence_mode, bool(old[5]), "Restore fence switch"),
             (arm.set_reduced_tcp_boundary, old[1], "Restore fence boundary"),
             (arm.set_reduced_max_tcp_speed, old[2], "Restore speed cap"),
             (arm.set_reduced_mode, bool(old[0]), "Restore reduced-mode switch")]
    for method, value, action in steps:
        code = method(value)
        if code in (1, [1]):   # the arm's own error blocks settings: clear it (the arm stays stopped), then retry
            print("\nCleared the arm's error so its safety settings could be restored.")
            checked(arm.clean_error(), "Clear arm error")
            checked(arm.set_state(4), "Stop before restoring settings")
            code = method(value)
        checked(code, action)



def main():
    global arm, target, yaw, report, watchdog
    server = None
    stop_arm = old = None
    camera_stop.clear()
    try:
        try:
            server = Server(("127.0.0.1", PORT), partial(Handler, directory=HERE))
        except OSError:
            print(f"Port {PORT} is busy: close the other copy of vr_teleop.py first.")
            return 1
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Thread(target=camera_loop, daemon=True).start()
        print(f"Open http://localhost:{PORT} in Chrome on this PC. Press Ctrl+C here to quit.")
        if SLOW_TEST:
            print(f"SLOW TEST: tool speed {SPEED} mm/s, near-floor speed {SLOW_SPEED} mm/s, controller cap {ARM_MAX_SPEED} mm/s.")
        if MOVE_ARM:
            arm, stop_arm, old = connect_arm()
            watchdog = ArmWatchdog(arm, stop_arm, hands)
            watchdog.start()
        start = reading(arm.get_position(), "Read start pose") if arm else [300, 0, 300, 180, 0, 0]
        target, yaw, limit = start[:3], start[5], ""
        hand0 = arm0 = hand_epoch = None
        arm_yaw0 = twist = last_hand_yaw = 0.0
        gripper = "open" if not arm or reading(arm.get_gripper_position(), "Read gripper") > GRIPPER_OPEN / 2 else "closed"
        last_clicks = last_clears = arm_error = None
        grip_open, last_grip_read, holding, tick = (1.0 if gripper == "open" else 0.0), None, False, 0
        print(f"Step timer on: any loop step over {SLOW_STEP * 1000:.0f} ms is printed here and in vr_debug.log.")
        print("LIVE: release the grip, then press A to arm motion.\n" if arm else "DRY RUN: the arm will not move.\n")
        last_loop = time.monotonic()
        while True:
            time.sleep(1 / 30)
            loop_time = time.monotonic()
            if loop_time - last_loop > SLOW_STEP + 1 / 30:   # the whole loop, minus its 1/30 s nap, was slow
                note_slow("whole loop", loop_time - last_loop - 1 / 30)
            last_loop = loop_time
            try:
                if watchdog:
                    watchdog.pulse()
                arm_error = None   # this tick passed the arm's error check
                hand = hands.snapshot()
                last_clears = hand["clears"] if hand["fresh"] else None
                grip, pos, hand_yaw = hand["grip"], hand["pos"], hand["yaw"]
                motion_on, status, epoch = hand["motion"], hand["status"], hand["epoch"]
                if hand0 is not None and (not grip or epoch != hand_epoch):
                    if watchdog:
                        with timed("stop on let go"):
                            watchdog.stop()   # stay stopped; only a NEW valid grip can make the arm ready again
                    hand0 = None
                if hand["fresh"]:
                    if motion_on and last_clicks is not None and hand["clicks"] > last_clicks:
                        wanted = "closed" if gripper == "open" else "open"
                        if watchdog:
                            with timed("move gripper"):
                                watchdog.command(epoch, "Move gripper", arm.set_gripper_position,
                                                 GRIPPER_CLOSED if wanted == "closed" else GRIPPER_OPEN,
                                                 wait=False, grip=False)
                        gripper = wanted
                    last_clicks = hand["clicks"]
                else:
                    last_clicks = None
                first = False   # True on the first move after a fresh grip
                if grip:
                    if hand0 is None:
                        first = True
                        with timed("read tool pose"):
                            now = reading(arm.get_position(), "Read tool pose") if arm else [*target, 0, 0, yaw]
                        if watchdog:
                            with timed("ready for fresh grip"):
                                watchdog.command(epoch, "Ready for fresh grip", arm.set_state, 0)
                        hand0, arm0, hand_epoch = pos, now[:3], epoch
                        arm_yaw0, twist, last_hand_yaw = now[5], 0.0, hand_yaw
                    move = curve(hand_to_arm(*(p - p0 for p, p0 in zip(pos, hand0))))
                    target, limit = keep_safe(*(a + m for a, m in zip(arm0, move)))
                    twist += (hand_yaw - last_hand_yaw + 180) % 360 - 180
                    last_hand_yaw = hand_yaw
                    yaw = arm_yaw0 + twist
                    if abs(yaw) > YAW_LIMIT:
                        yaw, limit = math.copysign(YAW_LIMIT, yaw), "rotation limit"
                        twist = yaw - arm_yaw0
                    if watchdog:
                        speed = SLOW_SPEED if target[2] < FLOOR + SLOW_ZONE else SPEED
                        with timed("first move" if first else "move tool"):
                            watchdog.command(epoch, "Move tool", arm.set_position,
                                             *target, start[3], start[4], yaw, speed=speed, wait=False,
                                             allow=FIRST_MOVE_ALLOW if first else HEADSET_TIMEOUT)
                else:
                    limit = ""
                tick += 1
                if tick % 6 == 0:
                    with timed("read gripper"):
                        result = arm.get_gripper_position() if arm else (0, GRIPPER_OPEN if gripper == "open" else GRIPPER_CLOSED)
                    value = reading(result, "Read gripper opening")
                    if watchdog:
                        watchdog.check()
                    if value is not None:
                        holding = gripper == "closed" and value > 30 and last_grip_read is not None and abs(value - last_grip_read) < 5
                        grip_open, last_grip_read = value / GRIPPER_OPEN, value
                landing = tip_px = None
                if T_tool_cam is not None and camera["depth"] is not None:
                    with timed("depth landing point"):
                        landing = calib.landing_point(T_tool_cam, camera["depth"], camera["intr"])
                        tip_px = calib.tip_pixel(T_tool_cam, camera["intr"])
                tool = arm.position if arm else [*target, 0, 0, yaw]
                report = {"live": bool(arm), "status": status, "limit": limit, "gripper": gripper, "motion": motion_on,
                          "grip_open": round(grip_open, 2), "holding": holding,
                          "landing": [round(landing[0]), round(landing[1]), round(landing[2])] if landing else None,
                          "tip_px": [round(tip_px[0]), round(tip_px[1])] if tip_px else None,
                          "calib": {"done": T_tool_cam is not None, "rms": calib_info["rms_mm"] if calib_info else None,
                                    "dot": calibration["mark"] is not None, "points": len(calibration["pairs"])},
                          "tool": [round(t) for t in tool[:3]], "target": [round(t) for t in target],
                          "yaw": round(tool[5]), "target_yaw": round(yaw),
                          "joints": [round(a, 1) for a in arm.angles[:6]] if arm else None}
                print(f"\r{'ARMED' if motion_on else 'off':5} {status:20} tool x, y, z (mm): {report['tool']}  turn {report['yaw']:4}°  gripper {gripper:6} {limit:14} camera: {camera['fps']} fps   ", end="")
            except CommandCancelled:
                # Letting go during an SDK reply is normal. Stop, discard that
                # grip's target, and wait for fresh input instead of exiting.
                if watchdog:
                    watchdog.stop()
                hand0 = None
                last_clicks = None
            except Stalled as exc:
                # The arm is already stopped. A slow reply isn't worth a restart: let go, press A, and carry on.
                watchdog.recover()
                hand0 = last_clicks = None
                print(f"\n{exc} The arm is stopped. Let go, then press A to carry on.")
            except ArmError as exc:
                # The arm stopped itself (collision, joint limit, fence...). It stays stopped until someone
                # looks at it and holds B for 2 s in VR. After that: let go, then press A.
                hand0 = last_clicks = None
                hands.disarm("motion off")
                if arm_error is None:
                    watchdog.stop()
                    print(f"\n{exc} The arm is stopped. Look at it, then hold B for 2 s in VR to clear the error.")
                arm_error = str(exc)
                hand = hands.snapshot()
                if hand["fresh"] and last_clears is not None and hand["clears"] > last_clears:
                    try:
                        watchdog.clear_error()
                        print("\nArm error cleared. The arm stays stopped: let go, then press A.")
                    except SafetyError as failed:
                        print(f"\nCould not clear the arm error: {failed} Check the E-stop and UFactory Studio.")
                last_clears = hand["clears"] if hand["fresh"] else None
                report = dict(report, motion=False, status="arm error", error=arm_error)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"\nStopped: {exc}")
        return 1
    finally:
        report = dict(report, motion=False, status="stopped")
        # Stop before waiting for the web server or restoring settings. Do not
        # clear a watchdog fault or re-enable the arm during shutdown.
        if stop_arm:
            try:
                checked(stop_arm.set_state(4), "Stop on exit")
            except Exception as exc:
                print(f"\nSTOP NOT CONFIRMED: {exc} Use the E-stop.")
        if arm:
            try:
                arm.disconnect()   # cancel pending commands before stopping the watchdog
            except Exception as exc:
                print(f"\nCould not close the command connection: {exc} Use the E-stop.")
        if watchdog:
            watchdog.close()
        camera_stop.set()
        if stop_arm:
            try:
                restore(stop_arm, old)
                print("\nSafety settings restored; arm remains stopped.")
            except Exception as exc:
                print(f"\nCould not restore settings: {exc} Check UFactory Studio.")
            finally:
                stop_arm.disconnect()
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    sys.exit(main())
