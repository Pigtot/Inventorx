"""
01_hello_arm.py: Connect to the xArm 6 and READ where it is.
This script does NOT move the arm. It's the safe first test.

Run it like this:
    ~/venvs/xarm/bin/python 01_hello_arm.py
(It uses our arm's IP. For a different arm, add its IP at the end.)
"""
import sys
from xarm.wrapper import XArmAPI

ARM_IP = "192.168.1.217"  # from the label on our control box

ip = sys.argv[1] if len(sys.argv) > 1 else ARM_IP
try:
    arm = XArmAPI(ip)  # opens the connection to the control box
except Exception:
    print(f"Could not connect to {ip}. Check the Ethernet cable and your Mac's IP settings.")
    sys.exit(1)

# The SDK uses mm for distance and degrees for angles by default.
print("Firmware version:", arm.version)
print("State (1=moving, 2=sleeping/idle, 3=paused, 4=stopped):", arm.state)
print("Error code (0 = no error):", arm.error_code)

# Two ways to describe the same pose:
code, angles = arm.get_servo_angle()  # 1) the angle of each joint, J1 to J6
print("Joint angles (deg):", [round(a, 1) for a in angles[:6]])

code, pos = arm.get_position()        # 2) where the tool tip is: x, y, z (mm), roll, pitch, yaw (deg)
print("Tool position [x, y, z, roll, pitch, yaw]:", [round(p, 1) for p in pos])

arm.disconnect()
