"""
03_check_labels.py: Draw the labels on 16 images so we can check them by eye.

The thin box shows all 8 labeled corners of the middle block; the dots mark its 4 top corners.
If they don't sit exactly on the block, training would learn garbage. So we ALWAYS look before we train.
Run it like this:
    ~/venvs/vision/bin/python 03_check_labels.py
Output: ../../media/jenga_label_check.png
"""
import csv
import random
from pathlib import Path

import cv2
import numpy as np

DATA = Path.home() / "arm_data/jenga"
OUT = Path(__file__).resolve().parents[2] / "media/jenga_label_check.png"
COLORS = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 220, 255)]  # corner 1-4: red, green, blue, yellow (BGR)

rows = list(csv.DictReader(open(DATA / "labels.csv")))
random.seed(1)
tiles = []
for row in random.sample(rows, min(16, len(rows))):
    img = cv2.imread(str(DATA / "images" / row["file"]))
    img = cv2.resize(img, None, fx=2, fy=2)          # bigger, so the dots are easy to see
    if "bx1" in row:   # all 8 box corners: draw the box's 12 edges
        box = [(round(float(row[f"bx{i}"]) * 2), round(float(row[f"by{i}"]) * 2)) for i in range(1, 9)]
        for a, b in [(i, j) for i in range(8) for j in range(i + 1, 8) if bin(i ^ j).count("1") == 1]:
            cv2.line(img, box[a], box[b], (255, 255, 0), 1, cv2.LINE_AA)
    pts = [(float(row[f"x{i}"]) * 2, float(row[f"y{i}"]) * 2) for i in range(1, 5)]
    cv2.polylines(img, [np.int32(pts)], True, (255, 255, 255), 1, cv2.LINE_AA)
    for (x, y), color in zip(pts, COLORS):
        cv2.circle(img, (round(x), round(y)), 5, color, -1, cv2.LINE_AA)
    cv2.putText(img, row["category"], (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, row["category"], (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    tiles.append(img)

while len(tiles) % 4:
    tiles.append(np.zeros_like(tiles[0]))
grid = np.vstack([np.hstack(tiles[r:r + 4]) for r in range(0, len(tiles), 4)])
OUT.parent.mkdir(exist_ok=True)
cv2.imwrite(str(OUT), grid)
print("Saved", OUT)
