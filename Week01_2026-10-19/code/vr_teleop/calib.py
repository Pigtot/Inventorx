"""
calib.py: where the D435 sits on the gripper ("hand-eye calibration"), and where the gripper will land in the picture.

Three coordinate frames, all in mm:
    base  = the arm's base (X forward, Y left, Z up). The arm reports the tool pose in this frame.
    tool  = at the gripper tip. Its z axis points out of the gripper (straight down when the gripper points down).
    cam   = the D435 color camera. z points straight out of the lens, x = right in the picture, y = down.

The calibration is one 4x4 matrix, T_tool_cam. It turns a point the camera measures into tool coordinates:
    point_in_tool = T_tool_cam @ point_in_cam
How we find it: touch the gripper tip to a dot (so we know the dot in base coordinates), then look at the dot
from several arm poses. Each look gives the same dot twice: once from the camera (pixel + depth) and once
from the arm (base -> tool). The Kabsch method finds the rotation and shift that best match all the pairs.
"""
import json
import math

import numpy as np

MIN_POINTS = 4
MIN_SPREAD_MM = 5.0   # a repeated point or an almost straight line cannot determine rotation reliably
MAX_RMS_MM = 5.0


def pose_matrix(x, y, z, roll, pitch, yaw):
    """The arm's tool pose (mm, degrees) as a 4x4 matrix: tool coordinates -> base coordinates.
    xArm angles work like this: R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    r, p, w = map(math.radians, (roll, pitch, yaw))
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rz = np.array([[math.cos(w), -math.sin(w), 0], [math.sin(w), math.cos(w), 0], [0, 0, 1]])
    T = np.eye(4)
    T[:3, :3] = Rz @ Ry @ Rx
    T[:3, 3] = (x, y, z)
    return T


def deproject(u, v, depth_mm, intr):
    """A pixel (u, v) plus its depth -> a 3D point in camera coordinates (mm). intr = (fx, fy, cx, cy)."""
    fx, fy, cx, cy = intr
    return np.array([(u - cx) * depth_mm / fx, (v - cy) * depth_mm / fy, depth_mm])


def project(point, intr):
    """A 3D point in camera coordinates -> its pixel (u, v). The reverse of deproject."""
    fx, fy, cx, cy = intr
    return fx * point[0] / point[2] + cx, fy * point[1] / point[2] + cy


def depth_at(depth, u, v, r=3):
    """Depth (mm) at pixel (u, v): the median of good readings in a small square around it (0 = no reading)."""
    h, w = depth.shape
    u, v = int(round(u)), int(round(v))
    if not (0 <= u < w and 0 <= v < h):
        return 0.0
    patch = depth[max(v - r, 0):v + r + 1, max(u - r, 0):u + r + 1]
    good = patch[patch > 0]
    return float(np.median(good)) if good.size else 0.0


def solve(pairs):
    """Kabsch method: the rotation R and shift t that best fit tool = R @ cam + t for all (cam, tool) pairs.
    Returns T_tool_cam (4x4) and the leftover error (RMS, mm). Rejects poor or degenerate samples."""
    if len(pairs) < MIN_POINTS:
        raise ValueError(f"Need at least {MIN_POINTS} points from different arm poses (have {len(pairs)}).")
    C = np.array([c for c, _ in pairs], dtype=float)
    P = np.array([t for _, t in pairs], dtype=float)
    if C.shape != (len(pairs), 3) or P.shape != C.shape or not np.isfinite([C, P]).all():
        raise ValueError("Every point must contain three finite coordinates.")
    for points in (C, P):
        # Two independent directions are enough; a planar set is valid.
        spread = np.linalg.svd(points - points.mean(axis=0), compute_uv=False) / math.sqrt(len(pairs))
        if spread[1] < MIN_SPREAD_MM:
            raise ValueError("Points are too close together or nearly in a line. Move sideways as well as up.")
    c0, p0 = C.mean(axis=0), P.mean(axis=0)
    U, _, Vt = np.linalg.svd((C - c0).T @ (P - p0))
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])   # rules out a mirror-image answer
    R = Vt.T @ D @ U.T
    t = p0 - R @ c0
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, t
    rms = float(np.sqrt(np.mean(np.sum((C @ R.T + t - P) ** 2, axis=1))))
    if not math.isfinite(rms) or rms > MAX_RMS_MM:
        raise ValueError(f"Fit error {rms:.1f} mm exceeds {MAX_RMS_MM:g} mm. Start over and collect better points.")
    return T, rms


def landing_point(T_tool_cam, depth, intr, longest=500, step=4):
    """Follow the gripper's axis (tool z) out from the tip until it reaches a surface the camera sees.
    Returns (u, v, clearance_mm): the pixel where the gripper will land and how far the tip is from it.
    Returns None if the axis leaves the picture or never meets a surface."""
    T_cam_tool = np.linalg.inv(T_tool_cam)
    tip, axis = T_cam_tool[:3, 3], T_cam_tool[:3, 2]
    for s in range(0, longest, step):
        p = tip + s * axis
        if p[2] <= 10:   # too close to (or behind) the lens to see
            continue
        u, v = project(p, intr)
        d = depth_at(depth, u, v, 1)
        if d and p[2] >= d:   # the axis has gone past the surface the camera sees here
            return u, v, float(s)
    return None


def tip_pixel(T_tool_cam, intr):
    """Where the gripper tip itself is in the picture (it may be outside the picture)."""
    tip = np.linalg.inv(T_tool_cam)[:3, 3]
    return project(tip, intr) if tip[2] > 10 else None


def load(path):
    """Read a saved calibration: returns (T_tool_cam, info) or (None, None) if there isn't one yet."""
    try:
        saved = json.loads(path.read_text())
        return np.array(saved["T_tool_cam"]), saved
    except (FileNotFoundError, KeyError, ValueError):
        return None, None


def save(path, T, rms, count):
    info = {"T_tool_cam": T.round(4).tolist(), "rms_mm": round(rms, 2), "points": count}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(info, indent=2, allow_nan=False))
    temporary.replace(path)   # keep the previous calibration intact if writing fails
    return info
