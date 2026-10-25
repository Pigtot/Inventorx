"""
02_first_move.py: The arm's first move: lift the tool 50 mm straight up, then come back down.

SAFETY: clear the space around the arm and keep a hand on the E-stop button.
Run it like this:
    ~/venvs/xarm/bin/python 02_first_move.py
(It uses our arm's IP. For a different arm, add its IP at the end.)
"""
import sys
from xarm.wrapper import XArmAPI

ARM_IP = "192.168.1.217"  # from the label on our control box
SPEED = 50      # mm per second (slow on purpose for a first test)
LIFT = 50       # mm to move up

try:
    arm = XArmAPI(sys.argv[1] if len(sys.argv) > 1 else ARM_IP)
except Exception:
    print("Could not connect. Run 01_hello_arm.py first to check the connection.")
    sys.exit(1)

# The 3-step "get ready" routine. Think of driving a car:
arm.clean_error()          # clear old warnings on the dashboard
arm.motion_enable(True)    # turn the key: power the joint motors
arm.set_mode(0)            # put it in drive: mode 0 = normal position control
arm.set_state(0)           # release the parking brake: state 0 = ready to move

input(f"Arm is ready. It will move UP {LIFT} mm and back. Workspace clear? Press Enter to go...")

# relative=True means "move this much from where you are now," not "go to this exact spot."
# wait=True means "finish this move before running the next line."
code = arm.set_position(z=LIFT, relative=True, speed=SPEED, wait=True)
print("Up move result code (0 = OK):", code)

code = arm.set_position(z=-LIFT, relative=True, speed=SPEED, wait=True)
print("Down move result code (0 = OK):", code)

if arm.error_code != 0:
    print("The arm reported error code", arm.error_code, "- look it up in UFactory Studio.")

arm.disconnect()
