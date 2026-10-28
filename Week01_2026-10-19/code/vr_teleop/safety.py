"""Hardware-independent input checks and a stop timer for VR control.

The stop connection is separate from the command connection: a stuck command must
not hold up a stop. Most watchdog faults end the session; only a restart can clear them.
Two kinds don't: a stall (release, then press A) and the arm's own error (hold B in VR to clear it).
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


class Stalled(SafetyError):
    """The loop or an SDK reply was too slow. The arm is stopped; release and press A to carry on."""


class ArmError(SafetyError):
    """The arm's controller has its own error, so it stopped itself. Holding B in VR clears it."""


# The arm's error codes we expect to see (UFactory Studio shows the same "C" numbers).
ARM_ERRORS = {1: "E-stop pressed", 2: "emergency stop input", 3: "teach pendant E-stop", 22: "self-collision",
              23: "a joint reached its limit", 24: "too fast", 31: "collision detected", 35: "reached the fence"}


def checked(code, action):
    if isinstance(code, (list, tuple)) and code:   # SDK 1.18.4's set_fence_mode returns [code], not code
        code = code[0]
    if code == 1:   # SDK code 1 = "the arm has an uncleared error"
        raise ArmError(f"{action} failed: the arm has an error (SDK code 1).")
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
        self.message = dict(grip=False, pos=None, yaw=0.0, clicks=0, arm_clicks=0, clears=0)
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

    def disarm(self, reason):
        """Turn motion off from outside (after a stop): release, then press A to go again."""
        with self.lock:
            self._disarm(reason)

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
            clears = msg.get("clears", 0)   # B holds that ask to clear an arm error (older pages don't send it)
            counters = all(type(msg.get(k)) is int and msg[k] >= 0 for k in ("clicks", "arm_clicks"))
            if type(msg.get("grip")) is not bool or not counters or type(clears) is not int or clears < 0:
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
                                clicks=msg["clicks"], arm_clicks=clicks, clears=clears)
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
        self.recoverable = False      # True when the fault is only a stall
        self.allow = HEADSET_TIMEOUT  # how late the loop may be; longer only during a first move
        self.step = "between steps"   # what the control loop is doing now, named if it stalls
        self.lock = threading.Lock()  # a watchdog tick never runs in the middle of clearing an arm error
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
            raise (Stalled if self.recoverable else SafetyError)(self.fault)
        if not self.arm.connected or not self.stop_arm.connected:
            raise SafetyError("Arm connection lost. Restart the program.")
        if self.arm.error_code:
            code = self.arm.error_code
            raise ArmError(f"Arm error C{code} ({ARM_ERRORS.get(code, 'see the xArm manual')}).")
        if self.arm.mode != 7 or self.arm.state == 3:
            raise SafetyError("Arm pause or mode change. Restart the program.")
        late = self.clock() - self.progress
        if self.active and late > self.allow:
            raise Stalled(f"Control loop stalled ({self.step}, {late * 1000:.0f} ms since the last loop).")

    def permit(self, epoch, grip=True):
        self.check()
        hand = self.hands.snapshot()
        if hand["epoch"] != epoch or not hand["motion"] or (grip and not hand["grip"]):
            raise CommandCancelled("Hand command expired or changed while an SDK call was running.")

    def command(self, epoch, action, method, *args, grip=True, allow=HEADSET_TIMEOUT, **kwargs):
        """Send one SDK command. `allow` = how long it may take (longer only for the first move after ready)."""
        self.permit(epoch, grip)
        if grip:
            self.active = True   # arm the timer BEFORE a call that can move the arm
        self.allow = allow
        try:
            code = method(*args, **kwargs)
            self.permit(epoch, grip)   # never follow a delayed call with another stale command
            if allow > HEADSET_TIMEOUT:
                self.progress = self.clock()   # a slow but allowed reply: the loop did make progress
        finally:
            self.allow = HEADSET_TIMEOUT
        checked(code, action)

    def stop(self):
        code = self.stop_arm.set_state(4)
        if code != 1:   # 1 = the arm has its own error, and an error has already stopped it
            checked(code, "Stop arm")
        self.active = False

    def recover(self):
        """After a stall: stay stopped, then the operator must release and press A again. No restart needed."""
        self.stop()
        self.hands.disarm("motion off")   # also makes any late command from before the stall stale
        self.fault, self.recoverable = None, False

    def clear_error(self, settle=1.0):
        """Clear the arm's own error on purpose (B held in VR). The arm stays stopped: only a fresh grip readies it."""
        with self.lock:
            checked(self.arm.clean_error(), "Clear arm error")
            checked(self.arm.motion_enable(True), "Enable motors")
            checked(self.arm.set_mode(7), "Select teleop mode")
            checked(self.stop_arm.set_state(4), "Keep arm stopped")
            self.active = False
            end = time.monotonic() + settle   # let the report stream show the cleared error and the mode
            while (self.arm.error_code or self.arm.mode != 7) and time.monotonic() < end:
                time.sleep(0.05)

    def poll(self):
        """One watchdog tick, also used by the fake-hardware regression tests."""
        with self.lock:
            if self.fault:
                self.stop()   # keep it stopped until the main loop has handled the fault
                return
            try:
                self.check()
                hand = self.hands.snapshot()
                if self.active and (not hand["fresh"] or self.clock() - self.progress > self.allow):
                    raise Stalled("Stop timer expired.")
                if self.active and not hand["grip"]:
                    self.stop()   # a normal release also stops through the independent connection
            except ArmError:
                if self.active:
                    self.stop()   # the arm stopped itself; keep it stopped until the error is cleared on purpose
            except SafetyError as exc:
                self.fault = str(exc)
                self.recoverable = isinstance(exc, Stalled)
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
