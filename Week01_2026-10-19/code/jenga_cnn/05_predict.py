"""
05_predict.py: Show the trained network any photo with a Jenga block in the middle.

Prints the category and draws the block's 3D box (all 8 corners) on a copy of the photo.
If you also give the camera's horizontal field of view, PnP works out how far away the block is.
Run it like this:
    ~/venvs/vision/bin/python 05_predict.py some_photo.jpg
    ~/venvs/vision/bin/python 05_predict.py some_photo.jpg --fov 69      (69 degrees = the D435 color camera)
Works best when the block fills about a quarter to half of the photo, like our training images.
"""
import argparse
import math
from pathlib import Path

import cv2
import numpy as np
import torch

from jenga_model import CATEGORIES, DATA, EDGES, IMG, load_model, prepare, solve_pose

parser = argparse.ArgumentParser()
parser.add_argument("photo", type=Path)
parser.add_argument("--fov", type=float, help="camera's horizontal field of view in degrees (turns on 3D distance)")
args = parser.parse_args()
img = cv2.imread(str(args.photo))
if img is None:
    raise SystemExit(f"Could not read {args.photo}")

# Crop the middle square (the network was trained on square pictures), then shrink to 224 x 224
h, w = img.shape[:2]
side = min(h, w)
x0, y0 = (w - side) // 2, (h - side) // 2
square = cv2.resize(img[y0:y0 + side, x0:x0 + side], (IMG, IMG), interpolation=cv2.INTER_AREA)
rgb = torch.from_numpy(square[:, :, ::-1].copy()).permute(2, 0, 1).unsqueeze(0)   # OpenCV is BGR; ResNet wants RGB

model, _ = load_model()
with torch.no_grad():
    scores, corners = model(prepare(rgb))
probs = scores.softmax(dim=1)[0]
# corners come out as 0-1 fractions of the square; turn them into pixels of the original photo
box = np.array([(x0 + u * side, y0 + v * side) for u, v in corners[0].view(8, 2).tolist()])

print(f"Category: {CATEGORIES[probs.argmax()]}  ("
      + ", ".join(f"{c} {p:.0%}" for c, p in zip(CATEGORIES, probs.tolist())) + ")")
print("Box corners (x, y):", [(round(x), round(y)) for x, y in box])
if args.fov:
    f = (w / 2) / math.tan(math.radians(args.fov) / 2)          # focal length in pixels
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])
    rvec, tvec = solve_pose(box, K)
    print(f"3D (PnP): the block's middle is {np.linalg.norm(tvec):.1f} cm from the camera "
          f"({tvec[0]:+.1f} cm right, {tvec[1]:+.1f} cm down, {tvec[2]:.1f} cm ahead)")

thick = max(2, side // 250)
for i, j in EDGES:
    cv2.line(img, tuple(np.int32(box[i])), tuple(np.int32(box[j])), (214, 120, 42), thick, cv2.LINE_AA)
cv2.putText(img, CATEGORIES[probs.argmax()], (x0 + 10, y0 + 40), cv2.FONT_HERSHEY_SIMPLEX, side / 400,
            (214, 120, 42), thick, cv2.LINE_AA)
out = DATA / "predictions" / f"{args.photo.stem}_guess.jpg"
out.parent.mkdir(exist_ok=True)
cv2.imwrite(str(out), img)
print("Saved", out)
