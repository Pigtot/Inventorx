"""
02_first_move.py: The arm's first move: lift the tool 50 mm straight up, then come back down.

SAFETY: clear the space around the arm and keep a hand on the E-stop button.
Run it like this:
    ~/venvs/xarm/bin/python 02_first_move.py
(It uses our arm's IP. For a different arm, add its IP at the end.)
"""
import math
import sys

ARM_IP = "192.168.1.217"
SPEED = 50   # mm/s: start slowly
LIFT = 50    # mm


def checked(code, action):
    if code != 0:
        raise RuntimeError(f"{action} failed (SDK code {code}). No further move will be sent.")


def main(factory=None, confirm=input):
    if factory is None:
        from xarm.wrapper import XArmAPI
        factory = XArmAPI
    arm = None
    try:
        arm = factory(sys.argv[1] if len(sys.argv) > 1 else ARM_IP)
        confirm(f"Workspace clear and a spotter on the E-stop? Press Enter to lift {LIFT} mm and return...")
        checked(arm.set_state(4), "Stop before setup")
        checked(arm.clean_error(), "Clear old error")
        code, start = arm.get_position()
        checked(code, "Read start pose")
        if len(start) != 6 or not all(math.isfinite(v) for v in start):
            raise RuntimeError("The arm did not return a valid start pose.")
        checked(arm.motion_enable(True), "Enable motors")
        checked(arm.set_mode(0), "Select position control")
        checked(arm.set_state(0), "Ready arm")
        raised = list(start)
        raised[2] += LIFT
        # Pass all six coordinates. Only return after the entire lift succeeds.
        checked(arm.set_position(*raised, speed=SPEED, wait=True), "Lift")
        checked(arm.set_position(*start, speed=SPEED, wait=True), "Return to start")
        print("Lift and return finished successfully.")
        return 0
    except KeyboardInterrupt:
        return 1
    except Exception as exc:
        print(f"Stopped: {exc}")
        return 1
    finally:
        if arm:
            try:
                checked(arm.set_state(4), "Stop on exit")
            finally:
                arm.disconnect()


if __name__ == "__main__":
    sys.exit(main())
