"""
03_d435_snapshot.py: Take ONE color photo and ONE depth picture with the RealSense D435.
This script does NOT move the arm. It only uses the camera.

Run it like this:
    ~/venvs/xarm/bin/python 03_d435_snapshot.py           (Mac)
    ~/venvs/xarm/Scripts/python.exe 03_d435_snapshot.py   (Windows)
It saves two pictures in this week's media/ folder.
"""
import sys
from pathlib import Path

import numpy as np
import pyrealsense2 as rs
from PIL import Image

MEDIA = Path(__file__).resolve().parent.parent / "media"
WIDTH, HEIGHT, FPS = 640, 480, 30

# Ask for two streams: color (a normal photo) and depth (a distance for every pixel).
config = rs.config()
config.enable_stream(rs.stream.color, WIDTH, HEIGHT, rs.format.rgb8, FPS)
config.enable_stream(rs.stream.depth, WIDTH, HEIGHT, rs.format.z16, FPS)

pipeline = rs.pipeline()
try:
    profile = pipeline.start(config)  # turns the camera on
except RuntimeError as e:
    print("Could not start the D435:", e, "- check the USB cable.")
    sys.exit(1)

device = profile.get_device()
print("Camera:", device.get_info(rs.camera_info.name))
print("USB type (3.x = fast, 2.x = slow cable or port):", device.get_info(rs.camera_info.usb_type_descriptor))

# The first frames come out dark while auto-exposure adjusts, so skip about 1 second of them.
for _ in range(FPS):
    frames = pipeline.wait_for_frames()

color = np.asanyarray(frames.get_color_frame().get_data())
depth = frames.get_depth_frame()
# Depth is just numbers, so the colorizer paints them: blue = near, red = far, black = no reading.
depth_picture = np.asanyarray(rs.colorizer().colorize(depth).get_data())
middle_m = depth.get_distance(WIDTH // 2, HEIGHT // 2)  # meters to whatever is at the center pixel

Image.fromarray(color).save(MEDIA / "d435_first_color.png")
Image.fromarray(depth_picture).save(MEDIA / "d435_first_depth.png")
pipeline.stop()  # turns the camera off

print("Distance at the middle of the picture:", round(middle_m, 3), "m (0 = no reading)")
print("Saved d435_first_color.png and d435_first_depth.png in", MEDIA)
