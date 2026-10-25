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
    ~/venvs/xarm/Scripts/python.exe vr_teleop.py --live   (the arm moves)
Then open http://localhost:8000 in Chrome on this PC. Press Ctrl+C here to quit.
"""
import json
import math
import sys
import threading
import time
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARM_IP = "192.168.1.217"  # from the label on our control box
MOVE_ARM = "--live" in sys.argv   # without --live, the arm is never touched

# Curved response: arm move = hand move x gain, and the gain grows the farther you reach from where you gripped.
FINE = 0.5      # gain for small moves (precise): 2 cm of hand = 1 cm of arm
FAST = 3.0      # gain for big moves (range): 30 cm of hand = 90 cm of arm
FAR = 300       # mm of hand movement where the gain reaches FAST
SPEED = 150     # mm/s: the fastest this script lets the tool move

# Safe workspace for the tool tip, in the arm's coordinates (mm): X = forward, Y = left, Z = up, 0 = base.
FLOOR = -75     # lowest the tip may go (our table is below the base's zero)
SLOW_ZONE = 75  # within this many mm above the floor, the tool slows down...
SLOW_SPEED = 50 # ...to this speed (mm/s), so touching down on a block is gentle
CEILING = 450   # highest
REACH = 560     # farthest from the base (full reach is about 700 mm; we keep a margin)
NEAR = 200      # closest to the base's center line, so the arm can't fold into itself
FRONT = 100     # X stays above this: the arm stays in front of its base, away from the operator
# Second layer, checked by the arm's own controller even if this script has a bug:
FENCE = [650, 50, 650, -650, 520, -105]   # x_max, x_min, y_max, y_min, z_max, z_min (mm): leaving it = arm stops
ARM_MAX_SPEED = 250   # mm/s: the controller refuses to go faster than this while teleop runs
GRIPPER_OPEN, GRIPPER_CLOSED = 850, 0   # xArm Gripper positions: 850 = wide open, 0 = closed (it stops on the block)
GRIPPER_SPEED = 3000
YAW_LIMIT = 170   # degrees: the gripper's turn stays within -170..170, so it never spins the long way around

CAM_W, CAM_H, CAM_FPS = 640, 360, 30   # camera picture in VR: low quality on purpose, so it stays light and smooth
PORT = 8000
HERE = Path(__file__).resolve().parent
MEDIA = HERE.parents[1] / "media"   # this week's media/ folder

latest = {"grip": False, "pos": None, "yaw": 0.0, "clicks": 0, "arm_clicks": 0, "time": 0.0}   # newest message from the headset
lock = threading.Lock()   # stops two threads from using `latest` at the same moment
report = {}   # what the VR page shows (status and live coordinates), rebuilt 30 times a second
camera = {"data": None, "id": 0, "fps": 0}   # newest D435 picture (raw RGB bytes) and its number
new_picture = threading.Condition()   # lets the web server wait until a newer picture arrives


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
        after = int(self.path.partition("after=")[2] or 0)   # the picture number Chrome already has
        with new_picture:   # wait (up to 1 s) for a newer picture, so Chrome never gets the same one twice
            new_picture.wait_for(lambda: camera["id"] > after, timeout=1)
            data, number = camera["data"], camera["id"]
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
            with lock:
                latest.update(grip=msg["grip"], pos=msg["pos"], yaw=msg.get("yaw") or 0.0,
                              clicks=msg.get("clicks", 0), arm_clicks=msg.get("arm_clicks", 0), time=time.time())
            reply = json.dumps(report).encode()   # answer with the live coordinates for the VR display
        elif self.path in ("/video.mp4", "/video.webm", "/d435.mp4", "/d435.webm"):   # headset mirror or D435 view
            MEDIA.mkdir(exist_ok=True)
            name = "d435" if self.path.startswith("/d435") else "vr"
            out = MEDIA / f"{name}_{datetime.now():%Y-%m-%d_%H%M%S}{Path(self.path).suffix}"
            out.write_bytes(body)
            print(f"\nSaved video: {out} ({len(body) / 1e6:.1f} MB)")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass   # don't print a line for every message


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
    limit = ""
    if not FLOOR <= z <= CEILING:
        z, limit = min(max(z, FLOOR), CEILING), "height limit"
    out = math.hypot(x, y)   # how far out from the base's center line
    farthest = math.sqrt(REACH ** 2 - z ** 2)   # higher up, the arm can't reach as far out
    if out < 1:
        x, y, out = NEAR, 0.0, NEAR
    if not NEAR <= out <= farthest:
        k = min(max(out, NEAR), farthest) / out
        x, y, limit = x * k, y * k, "reach limit"
    if x < FRONT:
        x, limit = FRONT, "front limit"
    return [x, y, z], limit


def camera_loop():
    """Keep only the newest D435 color picture in `camera`. It stays raw (no JPEG): everything is on
    this one PC, so skipping compression saves time on both ends."""
    try:
        import pyrealsense2 as rs
    except ImportError:
        print("\nNo pyrealsense2 here, so VR shows no camera.")
        return
    config = rs.config()
    config.enable_stream(rs.stream.color, CAM_W, CAM_H, rs.format.rgb8, CAM_FPS)
    while True:   # if the camera hiccups, turn it off and on again
        pipeline = rs.pipeline()
        try:
            pipeline.start(config)
            count, t0 = 0, time.time()
            while True:
                picture = pipeline.wait_for_frames(2000).get_color_frame()
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


def connect_arm():
    """Connect, ask the spotter, then turn on the arm with its own fence and speed cap.
    Returns the arm and its old safety settings (so we can put them back at the end)."""
    from xarm.wrapper import XArmAPI   # only needed when the arm really moves
    try:
        arm = XArmAPI(ARM_IP)
    except Exception:
        print("Could not connect. Run 01_hello_arm.py first to check the connection.")
        sys.exit(1)
    print("\nLIVE: the arm WILL move, but only while the grip is held.")
    try:
        input("SPOTTER: hand on the E-stop and workspace clear? Press Enter to turn on the arm (Ctrl+C = quit)...")
    except KeyboardInterrupt:
        arm.disconnect()
        sys.exit(0)
    x, y, z = arm.get_position()[1][:3]
    if keep_safe(x, y, z)[1]:
        print(f"The tool (x {x:.0f}, y {y:.0f}, z {z:.0f}) is outside the safe workspace. Move it inside first (Lesson 5).")
        arm.disconnect()
        sys.exit(1)
    if arm.collision_sensitivity == 0:
        print("WARNING: collision detection is OFF on the arm. Turn it on in UFactory Studio.")
    old = arm.get_reduced_states()[1]   # the arm's safety settings before we change them
    arm.clean_error()
    arm.motion_enable(True)
    arm.set_reduced_max_tcp_speed(ARM_MAX_SPEED)
    arm.set_reduced_tcp_boundary(FENCE)
    arm.set_reduced_mode(True)   # turns on the speed cap and the fence values
    arm.set_fence_mode(True)     # the arm stops itself if the tool leaves FENCE
    arm.set_mode(7)   # mode 7 = online planning: each new target smoothly replaces the last one
    arm.set_state(0)
    arm.set_gripper_mode(0)
    arm.set_gripper_enable(True)
    arm.set_gripper_speed(GRIPPER_SPEED)
    time.sleep(0.5)
    return arm, old


def stop_here(arm):
    """Let go = stop now: drop the rest of the move, then get ready for the next grip."""
    arm.set_state(4)   # state 4 = stop
    arm.set_mode(7)
    arm.set_state(0)


def restore(arm, old):
    """Put the arm back the way we found it."""
    arm.set_mode(0)   # back to normal position control
    arm.set_state(0)
    arm.set_fence_mode(bool(old[5]))
    arm.set_reduced_tcp_boundary(old[1])
    arm.set_reduced_max_tcp_speed(old[2])
    arm.set_reduced_mode(bool(old[0]))


try:
    server = Server(("127.0.0.1", PORT), partial(Handler, directory=HERE))   # 127.0.0.1 = this PC only
except OSError:
    print(f"Port {PORT} is busy: vr_teleop.py is probably already running in another window. Close that one first.")
    sys.exit(1)
# Serve the page and camera right away, so the operator can get into VR while the spotter gets ready.
threading.Thread(target=server.serve_forever, daemon=True).start()
threading.Thread(target=camera_loop, daemon=True).start()
print(f"Open http://localhost:{PORT} in Chrome on this PC. Press Ctrl+C here to quit.")
arm, old = connect_arm() if MOVE_ARM else (None, None)
start = arm.get_position()[1] if arm else [300, 0, 300, 180, 0, 0]   # x, y, z (mm), roll, pitch, yaw (deg)
target, yaw, limit = start[:3], start[5], ""   # yaw = which way the gripper is turned (degrees)
hand0 = arm0 = last_pos = None   # where the hand and the tool were when the grip was pressed; the last hand spot
arm_yaw0 = twist = last_hand_yaw = 0.0   # gripper turn at grip start; how far the hand has twisted since; last hand reading
gripper = "open" if not arm or arm.get_gripper_position()[1] > GRIPPER_OPEN / 2 else "closed"
last_clicks = None   # the page counts left-trigger clicks; each new click flips the gripper
motion_on, last_arm_clicks = False, None   # A button arms/disarms motion; it always starts disarmed
print("LIVE: the arm is on. Hold the grip to move it.\n" if arm else "DRY RUN: the arm will not move.\n")

try:
    while True:
        time.sleep(1 / 30)   # 30 updates per second
        with lock:
            grip, pos, hand_yaw, clicks = latest["grip"], latest["pos"], latest["yaw"], latest["clicks"]
            arm_clicks = latest["arm_clicks"]
            age = time.time() - latest["time"]
        if arm and arm.error_code:
            print(f"\nThe arm reported error {arm.error_code}. Stopping. Look it up in UFactory Studio, then restart.")
            break
        status = "following" if grip else "let go"
        if age > 0.3:
            grip, status = False, "waiting for headset"   # dead-man: no message for 0.3 s = act as if you let go
            last_clicks = last_arm_clicks = None   # the page may reload and count clicks from 0 again
            motion_on = False   # lost contact = disarm; press A again once you're back
        elif grip and last_pos and math.dist(pos, last_pos) > 0.25:
            grip, status = False, "tracking glitch"   # a 25 cm jump between two messages isn't a real hand move
        last_pos = pos
        if age <= 0.3:   # A button: each new press arms or disarms motion (never on old or missing messages)
            if last_arm_clicks is not None and arm_clicks != last_arm_clicks:
                motion_on = not motion_on
            last_arm_clicks = arm_clicks
        if not motion_on and age <= 0.3:
            grip, status = False, "motion off"   # disarmed: the grip, twist, and gripper do nothing
        if age <= 0.3:   # left trigger: each new click flips the gripper (never on old or missing messages)
            if motion_on and last_clicks is not None and clicks != last_clicks:
                gripper = "closed" if gripper == "open" else "open"
                if arm:
                    arm.set_gripper_position(GRIPPER_CLOSED if gripper == "closed" else GRIPPER_OPEN, wait=False)
            last_clicks = clicks
        if not grip:
            if hand0 is not None and arm:
                stop_here(arm)   # just let go: stop where the arm is now
            hand0 = None
        else:
            if hand0 is None:   # grip just pressed: remember where the hand and the tool are right now
                if arm and arm.mode != 7:
                    print(f"\nThe arm left teleop mode (mode {arm.mode}). Stopping, so moves can't pile up. Restart.")
                    break
                now = arm.get_position()[1] if arm else [*target, 0, 0, yaw]
                hand0, arm0, arm_yaw0, twist, last_hand_yaw = pos, now[:3], now[5], 0.0, hand_yaw
            move = curve(hand_to_arm(*(p - p0 for p, p0 in zip(pos, hand0))))
            target, limit = keep_safe(*(a + m for a, m in zip(arm0, move)))
            # Twist your hand and the gripper turns the same amount (1:1). It keeps pointing straight down.
            # Add up small steps (each one -180..180), so turning past "behind you" can't flip to the other side.
            twist += (hand_yaw - last_hand_yaw + 180) % 360 - 180
            last_hand_yaw = hand_yaw
            yaw = arm_yaw0 + twist
            if abs(yaw) > YAW_LIMIT:   # hold at the limit; twisting back moves it again right away
                yaw, limit = math.copysign(YAW_LIMIT, yaw), "rotation limit"
                twist = yaw - arm_yaw0
            if arm:
                speed = SLOW_SPEED if target[2] < FLOOR + SLOW_ZONE else SPEED   # gentle near the table
                code = arm.set_position(*target, start[3], start[4], yaw, speed=speed, wait=False)
                if code != 0:
                    print(f"\nThe arm answered code {code} (error {arm.error_code}). Stopping. Look the error up in UFactory Studio.")
                    break
        if not grip:
            limit = ""
        tool = arm.position if arm else [*target, 0, 0, yaw]   # where the tool really is (dry run: where it would be)
        report = {"live": bool(arm), "status": status, "limit": limit, "gripper": gripper, "motion": motion_on,
                  "tool": [round(t) for t in tool[:3]], "target": [round(t) for t in target],
                  "yaw": round(tool[5]), "target_yaw": round(yaw),
                  "joints": [round(a, 1) for a in arm.angles[:6]] if arm else None}
        print(f"\r{'ARMED' if motion_on else 'off':5} {status:20} tool x, y, z (mm): {report['tool']}  turn {report['yaw']:4}°  gripper {gripper:6} {limit:14} camera: {camera['fps']} fps   ", end="")
except KeyboardInterrupt:
    pass
finally:
    server.shutdown()
    if arm:
        restore(arm, old)
        print("\nArm settings restored. Error code (0 = no error):", arm.error_code)
        arm.disconnect()
