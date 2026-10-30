import json
import numpy as np
import pyrealsense2 as rs

rs.log_to_console(rs.log_severity.warn)
print('Starting camera-only probe; no robot SDK is loaded.', flush=True)
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 15)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15)
started = False
try:
    profile = pipeline.start(config)
    started = True
    device = profile.get_device()
    print('Camera:', device.get_info(rs.camera_info.name), flush=True)
    print('USB:', device.get_info(rs.camera_info.usb_type_descriptor), flush=True)
    align = rs.align(rs.stream.color)
    for i in range(10):
        frames = align.process(pipeline.wait_for_frames(15000))
        if i == 0: print('First frame arrived', flush=True)
    color = np.asanyarray(frames.get_color_frame().get_data())
    depth = np.asanyarray(frames.get_depth_frame().get_data())
    print(json.dumps({'ok': True, 'color_shape': list(color.shape), 'depth_shape': list(depth.shape),
                      'valid_depth_pixels': int((depth > 0).sum()), 'total_pixels': int(depth.size)}), flush=True)
finally:
    if started: pipeline.stop()
