"""Hardware-independent input checks and a stop timer for VR control.

The stop connection is separate from the command connection: a stuck command must
not hold up a stop. A watchdog fault ends the session; only a restart can clear it.
"""
import math
import threading
import time

HEADSET_TIMEOUT = 0.3
COMMAND_TIMEOUT = 0.15


class SafetyError(RuntimeError):
    pass


class CommandCancelled(SafetyError):
    """A normal grip change cancelled this command; stop and read a fresh hand pose."""


def checked(code, action):
    if code != 0:
        raise SafetyError(f"{action} failed (SDK code {code}).")


def reading(result, action):
    code, value = result
    checked(code, action)
    return value


class HandInput:
    """Remember valid hand data. Tracking faults require release, then a fresh A press."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.message = dict(grip=False, pos=None, yaw=0.0, clicks=0, arm_clicks=0)
        self.received = None
        self.motion = False
        self.needs_release = False
        self.reason = "waiting for headset"
        self.previous_pos = None
        self.arm_clicks = None
        self.epoch = 0

    def _disarm(self, reason):
        self.motion = False
        self.needs_release = True
        self.reason = reason
        self.previous_pos = None
        self.epoch += 1

    def _expire(self, now):
        if self.received is not None and now - self.received > HEADSET_TIMEOUT:
            if self.motion or self.reason != "waiting for headset":
                self._disarm("waiting for headset")
            self.arm_clicks = None

    def update(self, msg):
        with self.lock:
            now = self.clock()
            self._expire(now)
            pos = msg.get("pos")
            yaw = msg.get("yaw", 0.0)
            valid = (isinstance(pos, (list, tuple)) and len(pos) == 3
                     and all(type(p) in (int, float) and math.isfinite(p) for p in pos)
                     and type(yaw) in (int, float) and math.isfinite(yaw))
            counters = all(type(msg.get(k)) is int and msg[k] >= 0 for k in ("clicks", "arm_clicks"))
            if type(msg.get("grip")) is not bool or not counters:
                self._disarm("tracking glitch")
                return
            grip, clicks = msg["grip"], msg["arm_clicks"]
            pressed_a = self.arm_clicks is not None and clicks > self.arm_clicks
            restarted = self.arm_clicks is not None and clicks < self.arm_clicks
            self.arm_clicks = clicks
            jumped = (valid and grip and self.motion and self.previous_pos is not None
                      and math.dist(pos, self.previous_pos) > 0.25)
            if grip != self.message["grip"]:
                self.epoch += 1   # also catches a release/re-grip between two control-loop ticks
            self.message = dict(grip=grip, pos=list(pos) if valid else None, yaw=yaw if valid else 0.0,
                                clicks=msg["clicks"], arm_clicks=clicks)
            self.received = now
            if not valid or jumped or restarted:
                self._disarm("tracking glitch")
                return
            self.previous_pos = list(pos)
            if self.needs_release:
                if not grip:
                    self.needs_release = False
                    self.reason = "motion off"
                return   # releasing and pressing A together cannot clear a fault and arm
            if not self.motion:
                self.reason = "motion off"
            if pressed_a:
                if self.motion:
                    self._disarm("motion off")
                elif not grip:
                    self.motion = True
                    self.reason = "let go"
                    self.epoch += 1

    def snapshot(self):
        with self.lock:
            self._expire(self.clock())
            fresh = self.received is not None and self.clock() - self.received <= HEADSET_TIMEOUT
            motion = self.motion and fresh and not self.needs_release
            grip = motion and self.message["grip"]
            status = ("following" if grip else "let go") if motion else self.reason
            return dict(self.message, grip=grip, motion=motion, status=status, epoch=self.epoch,
                        time=self.received, fresh=fresh)


class ArmWatchdog:
    """Stop independently if the loop stalls, contact expires, or arm mode/state changes."""
    def __init__(self, arm, stop_arm, hands, clock=time.monotonic):
        self.arm, self.stop_arm, self.hands, self.clock = arm, stop_arm, hands, clock
        self.progress = clock()
        self.active = False
        self.fault = None
        self.closed = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def pulse(self):
        self.check()
        self.progress = self.clock()

    def check(self):
        if self.fault:
            raise SafetyError(self.fault)
        if not self.arm.connected or not self.stop_arm.connected:
            raise SafetyError("Arm connection lost. Restart the program.")
        if self.arm.error_code or self.arm.mode != 7 or self.arm.state == 3:
            raise SafetyError("Arm error, pause, or mode change. Restart the program.")
        if self.active and self.clock() - self.progress > HEADSET_TIMEOUT:
            raise SafetyError("Control loop stalled. Restart the program.")

    def permit(self, epoch, grip=True):
        self.check()
        hand = self.hands.snapshot()
        if hand["epoch"] != epoch or not hand["motion"] or (grip and not hand["grip"]):
            raise CommandCancelled("Hand command expired or changed while an SDK call was running.")

    def command(self, epoch, action, method, *args, grip=True, **kwargs):
        self.permit(epoch, grip)
        if grip:
            self.active = True   # arm the timer BEFORE a call that can move the arm
        code = method(*args, **kwargs)
        self.permit(epoch, grip)   # never follow a delayed call with another stale command
        checked(code, action)

    def stop(self):
        checked(self.stop_arm.set_state(4), "Stop arm")
        self.active = False

    def poll(self):
        """One watchdog tick, also used by the fake-hardware regression tests."""
        if self.fault:
            self.stop()   # keep it stopped until the command connection has been closed
            return
        try:
            self.check()
            hand = self.hands.snapshot()
            if self.active and (not hand["fresh"] or self.clock() - self.progress > HEADSET_TIMEOUT):
                raise SafetyError("Stop timer expired. Restart the program.")
            if self.active and not hand["grip"]:
                self.stop()   # a normal release also stops through the independent connection
        except SafetyError as exc:
            self.fault = str(exc)
            self.stop()

    def _run(self):
        while not self.closed.wait(0.02):
            try:
                self.poll()
            except Exception as exc:
                self.fault = f"Could not confirm the stop ({exc}). Use the E-stop."

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=1)
