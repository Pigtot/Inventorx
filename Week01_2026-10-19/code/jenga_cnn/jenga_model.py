"""
jenga_model.py: The pieces shared by the training, predicting, and visualizing scripts.

- JengaNet:      pretrained ResNet-18 body + two heads
                 head A: 3 category scores; head B: 8 heat maps (one per box corner) -> 8 corners
- box_loss:      scores the 8 corners, allowing for the block's symmetry
- solve_pose:    8 corners + known block size + lens -> 3D position and rotation (PnP)
- solve_pose_on_table: the same, but knowing the block lies on a table (only spin is free) -> also the category
- category_from_pose: which way the block is turned -> flat / side / standing
- describe:      4 top corners -> center, angle, length, width
- crop_square:   cut one block out of a bigger photo
"""
import math
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models

DATA = Path.home() / "arm_data/jenga"
MODEL_PATH = DATA / "models/jenga_resnet18.pt"
CATEGORIES = ["flat", "side", "standing"]
RENDER_SIZE = 256   # labels are in pixels of the 256 x 256 renders
IMG = 224           # ResNet's favorite picture size
HEAT = 56           # each corner heat map is a 56 x 56 grid
SENSOR_MM = 36.0    # the camera sensor width our renders use (Blender's default)
# The block's 8 corners in its own frame (cm): x along the 7.5 cm length, y the 2.5 cm width, z the 1.5 cm height.
# Same order as the renderer's labels b1..b8.
BOX_POINTS = np.array([(sx * 3.75, sy * 1.25, sz * 0.75) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
_corner = lambda ix, iy, iz: 4 * ix + 2 * iy + iz
# A block looks the same after turning 180 degrees around any of its 3 axes, so these 4 corner orders are all correct
SYMMETRIES = [[_corner(ix ^ a, iy ^ b, iz ^ c) for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)]
              for a, b, c in [(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0)]]
MIRROR_X = [_corner(1 - ix, iy, iz) for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)]   # relabel after a mirror flip
POSE_CATEGORY = ["standing", "side", "flat"]   # which block axis points up: the 7.5, 2.5, or 1.5 cm one
# The box's 12 edges: pairs of corners that differ along just one axis
EDGES = [(i, j) for i in range(8) for j in range(i + 1, 8) if bin(i ^ j).count("1") == 1]
# ResNet was pretrained on photos scaled with these averages, so we scale ours the same way
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def zoom_up(c_in, c_out):
    """Double the map's size (7 -> 14 -> 28 -> 56) while mixing its channels."""
    return nn.Sequential(nn.ConvTranspose2d(c_in, c_out, 4, stride=2, padding=1, bias=False),
                         nn.BatchNorm2d(c_out), nn.ReLU(inplace=True))


def with_position(f):
    """Add 2 channels that say where each square is (x and y, from -1 to 1), so 'the middle' is easy to find."""
    b, _, h, w = f.shape
    ys = torch.linspace(-1, 1, h, device=f.device).view(1, 1, h, 1).expand(b, 1, h, w)
    xs = torch.linspace(-1, 1, w, device=f.device).view(1, 1, 1, w).expand(b, 1, h, w)
    return torch.cat([f, xs, ys], dim=1)


def soft_argmax(heat):
    """4 heat maps -> 4 corners. Each corner = the average spot of its map, weighted by how hot each square is."""
    b, k, h, w = heat.shape
    p = heat.flatten(2).softmax(dim=-1).view(b, k, h, w)    # each map's heat adds up to 1
    grid = (torch.arange(w, device=heat.device, dtype=heat.dtype) + 0.5) / w   # square centers, 0-1
    x = (p.sum(dim=2) * grid).sum(dim=-1)
    y = (p.sum(dim=3) * grid).sum(dim=-1)
    return torch.stack([x, y], dim=-1).view(b, 2 * k)      # x1, y1, ... x4, y4 as 0-1 fractions


class JengaNet(nn.Module):
    def __init__(self, pretrained=True):
        super().__init__()
        resnet = models.resnet18(weights=models.ResNet18_Weights.DEFAULT if pretrained else None)
        resnet.fc = nn.Identity()               # remove its old "1000 kinds of objects" answer layer
        self.body = resnet                      # turns a picture into 512 maps of 7 x 7 squares
        self.drop = nn.Dropout(0.2)             # while training, randomly hide 20% of features so no head leans on one
        self.category_head = nn.Linear(512, 3)  # head A: one score per category
        # head B: zoom the 7 x 7 maps back up to 56 x 56 and paint 8 heat maps, one per box corner
        self.corner_head = nn.Sequential(zoom_up(512 + 2, 256), zoom_up(256, 128), zoom_up(128, 64),
                                         nn.Conv2d(64, 8, kernel_size=1))

    def forward(self, x):
        b = self.body
        maps = b.layer4(b.layer3(b.layer2(b.layer1(b.maxpool(b.relu(b.bn1(b.conv1(x))))))))
        features = maps.mean(dim=(2, 3))        # average each map: the 512 "features"
        scores = self.category_head(self.drop(features))
        corners = soft_argmax(self.corner_head(with_position(maps)))
        return scores, corners


def prepare(images_uint8):
    """uint8 pictures (0-255) -> the scaled numbers ResNet expects."""
    x = images_uint8.float() / 255
    return (x - MEAN.to(x.device)) / STD.to(x.device)


def _shifted(target):
    """The same 4 corners, listed starting from each corner in turn (still clockwise)."""
    t = target.view(-1, 4, 2)
    return [t.roll(k, dims=1) for k in range(4)]


def box_loss(pred, target):
    """Average corner miss over the 8 box corners, using whichever of the 4 symmetric corner orders fits best."""
    p, t = pred.view(-1, 8, 2), target.view(-1, 8, 2)
    per_order = torch.stack([(p - t[:, s]).abs().mean(dim=(1, 2)) for s in SYMMETRIES], dim=1)
    return per_order.min(dim=1).values.mean()


def box_error_px(pred, target):
    """Average distance (pixels) between guessed and true box corners, best symmetric order."""
    p, t = pred.view(-1, 8, 2), target.view(-1, 8, 2)
    per_order = torch.stack([(p - t[:, s]).norm(dim=2).mean(dim=1) for s in SYMMETRIES], dim=1)
    return per_order.min(dim=1).values * RENDER_SIZE


def camera_matrix(lens_mm, size=RENDER_SIZE):
    """The lens settings PnP needs: focal length in pixels, and the picture's middle."""
    f = lens_mm / SENSOR_MM * size
    return np.array([[f, 0, size / 2], [0, f, size / 2], [0, 0, 1]])


def solve_pose(corners_px, K):
    """PnP: 8 corners in the picture + the block's real size + lens -> rotation and position (cm) from the camera."""
    pts = np.asarray(corners_px, dtype=np.float64).reshape(8, 2)
    _, rvec, tvec = cv2.solvePnP(BOX_POINTS, pts, K, None, flags=cv2.SOLVEPNP_SQPNP)
    rvec, tvec = cv2.solvePnPRefineLM(BOX_POINTS, pts, K, None, rvec, tvec)   # polish the answer
    return rvec.ravel(), tvec.ravel()


def _turn(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
            "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


# The 3 ways a block can rest on a table (same as the renderer's poses), and its 4 look-alike turns
RESTING = {"flat": np.eye(3), "side": _turn("x", 90), "standing": _turn("y", 90)}
FLIPS = [np.diag(d) for d in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1])]


def solve_pose_on_table(corners_px, K, up, step=2.0, only=None):
    """PnP that knows the block lies on a table, so it can only rest on one of 3 face types and spin.
    Try every resting pose x every spin angle; for each, the position comes from simple linear algebra;
    keep whichever fits the 8 corners best. Returns category, rotation, position (cm), and fit error (px).
    only = a list of categories to try (default: all 3)."""
    pts = np.asarray(corners_px, dtype=np.float64).reshape(8, 2)
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    up = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    # a "table" frame seen from the camera: z points up, x is any direction along the table
    helper = np.array([1.0, 0, 0]) if abs(up[2]) > 0.9 else np.array([0, 0, 1.0])
    tx = np.cross(up, helper)
    tx /= np.linalg.norm(tx)
    table = np.stack([tx, np.cross(up, tx), up], axis=1)
    # For a fixed rotation R, each corner gives 2 equations that are linear in the position t
    du, dv = pts[:, 0] - cx, pts[:, 1] - cy
    A = np.zeros((16, 3))
    A[0::2, 0], A[0::2, 2] = fx, -du
    A[1::2, 1], A[1::2, 2] = fy, -dv
    A_pinv = np.linalg.pinv(A)

    def fit(rotations):
        q = np.einsum("nij,kj->nki", rotations, BOX_POINTS)          # corners turned, before moving: (n, 8, 3)
        b = np.empty((len(rotations), 16))
        b[:, 0::2] = du * q[..., 2] - fx * q[..., 0]
        b[:, 1::2] = dv * q[..., 2] - fy * q[..., 1]
        t = b @ A_pinv.T                                              # best position for each rotation
        cam = q + t[:, None, :]
        proj = np.stack([fx * cam[..., 0] / cam[..., 2] + cx, fy * cam[..., 1] / cam[..., 2] + cy], axis=-1)
        err = np.linalg.norm(proj - pts, axis=-1).mean(axis=1)
        err[(cam[..., 2] <= 0).any(axis=1)] = np.inf                  # the block must be in front of the camera
        return t, err

    def candidates(spins):
        rots, names = [], []
        for name, P in RESTING.items():
            if only and name not in only:
                continue
            for F in FLIPS:
                for s in spins:
                    rots.append(table @ _turn("z", s) @ P @ F)
                    names.append((name, P @ F))
        return np.array(rots), names

    spins = np.arange(0, 360, step)
    rots, names = candidates(spins)                                    # coarse search
    t, err = fit(rots)
    i = int(np.argmin(err))
    best_name, best_rest = names[i]
    best_spin = spins[i % len(spins)]
    spins = best_spin + np.arange(-step, step, 0.05)                   # fine search around the best spin
    rots = np.array([table @ _turn("z", s) @ best_rest for s in spins])
    t, err = fit(rots)
    j = int(np.argmin(err))
    rvec = cv2.Rodrigues(rots[j])[0].ravel()
    return best_name, rvec, t[j], float(err[j])


def category_from_pose(rvec, up):
    """Whichever of the block's 3 axes points most nearly 'up' decides flat / side / standing."""
    axes = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))[0]      # columns = block's axes, seen from the camera
    return POSE_CATEGORY[int(np.argmax(np.abs(axes.T @ np.asarray(up))))]


def top_face(rvec, tvec, up):
    """Indexes of the 4 corners that are highest above the table."""
    R = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))[0]
    heights = (BOX_POINTS @ R.T + tvec) @ np.asarray(up)
    return list(np.argsort(-heights)[:4])


def rotation_error_deg(rvec1, rvec2):
    """How far apart two rotations are, in degrees, counting symmetric turns of the block as the same."""
    R1, R2 = cv2.Rodrigues(np.asarray(rvec1, dtype=np.float64))[0], cv2.Rodrigues(np.asarray(rvec2, dtype=np.float64))[0]
    best = 180.0
    for flip in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]):   # the 180-degree turns that look identical
        cos = (np.trace(R1.T @ R2 @ np.diag(flip)) - 1) / 2
        best = min(best, math.degrees(math.acos(max(-1.0, min(1.0, cos)))))
    return best


def corner_error_px(pred, target):
    """Average distance (pixels) between guessed and true corners, best starting corner."""
    p = pred.view(-1, 4, 2)
    per_start = torch.stack([(p - t).norm(dim=2).mean(dim=1) for t in _shifted(target)], dim=1)
    return per_start.min(dim=1).values * RENDER_SIZE


def describe(corners_px):
    """4 corners in pixels [x1, y1, ... x4, y4] -> center, angle, length, width."""
    c = [(corners_px[2 * i], corners_px[2 * i + 1]) for i in range(4)]
    cx, cy = sum(p[0] for p in c) / 4, sum(p[1] for p in c) / 4
    edge = lambda i: (c[(i + 1) % 4][0] - c[i][0], c[(i + 1) % 4][1] - c[i][1])
    size = lambda e: math.hypot(*e)
    a = (size(edge(0)) + size(edge(2))) / 2      # average of the two opposite edges
    b = (size(edge(1)) + size(edge(3))) / 2
    ex, ey = edge(0) if a >= b else edge(1)      # the long edge sets the angle
    # minus ey because image y points down; % 180 because a block turned 180 degrees looks the same
    angle = math.degrees(math.atan2(-ey, ex)) % 180
    return dict(center=(cx, cy), angle=angle, length=max(a, b), width=min(a, b))


def crop_square(img, cx, cy, side):
    """Square crop centered on (cx, cy), shrunk to the network's 224 x 224 size."""
    x0, y0 = cx - side // 2, cy - side // 2
    return cv2.resize(img[y0:y0 + side, x0:x0 + side], (IMG, IMG), interpolation=cv2.INTER_AREA)


def angle_diff(a, b):
    d = abs(a - b) % 180
    return min(d, 180 - d)


def load_model(device="cpu"):
    ckpt = torch.load(MODEL_PATH, map_location=device)
    model = JengaNet(pretrained=False)
    model.load_state_dict(ckpt["weights"])
    return model.to(device).eval(), ckpt
