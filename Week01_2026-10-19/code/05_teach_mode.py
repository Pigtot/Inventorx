"""
05_teach_mode.py: Turn on teach mode (hand-guiding). The arm goes "floppy" so you can push it by hand,
and it stays where you leave it. The screen shows the joint angles live while you move it.

SAFETY: clear the workspace. A spotter keeps a hand on the E-stop.
Hold the arm with both hands and move it slowly.
Run it like this:
    ~/venvs/xarm/Scripts/python.exe 05_teach_mode.py   (Windows)
    ~/venvs/xarm/bin/python 05_teach_mode.py           (Mac)
Press Ctrl+C to leave teach mode. The arm locks in place again.
"""
import sys
import time

from xarm.wrapper import XArmAPI

ARM_IP = "192.168.1.217"  # from the label on our control box

try:
    arm = XArmAPI(sys.argv[1] if len(sys.argv) > 1 else ARM_IP)
except Exception:
    print("Could not connect. Run 01_hello_arm.py first to check the connection.")
    sys.exit(1)

input("Spotter on the E-stop and your hands on the arm? Press Enter to turn on teach mode...")

arm.clean_error()
arm.motion_enable(True)
arm.set_mode(2)   # mode 2 = teach mode: the motors only hold up the arm's weight, so you can push it
arm.set_state(0)
print("Teach mode ON. Push the arm gently. Press Ctrl+C to stop.\n")

try:
    while True:
        code, angles = arm.get_servo_angle()
        code, pos = arm.get_position()
        print(f"\rJ1-J6 (deg): {[round(a, 1) for a in angles[:6]]}   tip x, y, z (mm): {[round(p) for p in pos[:3]]}   ", end="")
        time.sleep(0.2)
except KeyboardInterrupt:
    pass
finally:
    arm.set_mode(0)   # back to normal position control: the arm locks where it is
    arm.set_state(0)
    print("\nTeach mode OFF. Error code (0 = no error):", arm.error_code)
    arm.disconnect()
