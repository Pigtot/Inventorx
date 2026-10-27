"""
08_test_real.py: The real test. Run the network on real Jenga photos.

Each line of real_crops.csv picks one block in one Openverse photo (from 07_get_real_photos.py):
its square crop (center x, center y, side) and the category a person labeled BEFORE seeing the
network's answer ("unsure" if they couldn't tell).
Real photos have no exact corner labels, so we judge the network's 3D box by eye on the contact sheet.
Run it like this:
    ~/venvs/vision/bin/python 08_test_real.py
Output: ../../media/jenga_real_test.png and ~/arm_data/jenga/real/results.json
"""
import csv
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from jenga_model import CATEGORIES, DATA, EDGES, crop_square, load_model, prepare
from real_photos import load_crops

HERE = Path(__file__).resolve().parent
REAL = DATA / "real"
OUT = HERE.parents[1] / "media/jenga_real_test.png"
TILE = 256
BLUE = (214, 120, 42)   # OpenCV colors are BGR

picks, photo_info = load_crops(HERE / "real_crops.csv", REAL / "credits.csv")
squares = [crop_square(cv2.imread(str(REAL / "photos" / photo_info[p["source"]]["file"])), int(p["cx"]), int(p["cy"]), int(p["side"]))
           for p in picks]
x = torch.from_numpy(np.stack([s[:, :, ::-1] for s in squares]).copy()).permute(0, 3, 1, 2)   # BGR -> RGB

model, _ = load_model()
with torch.no_grad():
    scores, corners = model(prepare(x))
probs = scores.softmax(1)

results, tiles, right, labeled = [], [], 0, 0
for i, (p, sq) in enumerate(zip(picks, squares)):
    guess = CATEGORIES[probs[i].argmax()]
    px = (corners[i] * TILE).tolist()
    tile = cv2.resize(sq, (TILE, TILE))
    box = np.int32(np.reshape(px, (8, 2)))
    for a, b in EDGES:                     # draw the network's 3D box
        cv2.line(tile, tuple(box[a]), tuple(box[b]), BLUE, 2, cv2.LINE_AA)
    if p["label"] != "unsure":
        labeled += 1
        right += guess == p["label"]
    mark = "" if p["label"] == "unsure" else (" OK" if guess == p["label"] else " X")
    color = (255, 200, 120) if p["label"] == "unsure" else ((120, 230, 120) if guess == p["label"] else (130, 130, 255))
    tile[:46] = (tile[:46] * 0.35).astype(np.uint8)    # dark band so the text is readable
    cv2.putText(tile, f"#{i + 1} guess: {guess} {probs[i].max():.0%}{mark}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    cv2.putText(tile, f"label: {p['label']}", (6, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    tiles.append(tile)
    results.append(dict(number=i + 1, photo=int(p["photo"]), source=p["source"], label=p["label"], guess=guess,
                        probs=probs[i].tolist(), box=px, note=p["note"]))
    print(f"#{i + 1:2d} photo {p['photo']:>3}  label {p['label']:8s}  guess {guess:8s} "
          f"({', '.join(f'{c} {v:.0%}' for c, v in zip(CATEGORIES, probs[i].tolist()))})")

print(f"\nCategory correct on labeled crops: {right}/{labeled}")
while len(tiles) % 6:
    tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(str(OUT), np.vstack([np.hstack(tiles[r:r + 6]) for r in range(0, len(tiles), 6)]))
(REAL / "results.json").write_text(json.dumps(dict(right=right, labeled=labeled, crops=results), indent=1))
print("Saved", OUT)
