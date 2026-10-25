"""
06_export_viz.py: Build the interactive web page that shows the network "thinking".

Runs the trained network on 12 rendered test pictures, plus the real photo crops
(if 08_test_real.py has been run), and records for each:
  - its guess (category, 8 box corners, and for Blender pictures the PnP 3D pose) and the truth we know
  - how strongly a few neurons in each ResNet layer fired ("activations"),
    plus a small map of WHERE in the picture each one fired
  - the two heads' weights, so the page can show which features pushed each answer
Then pours that data into viz_template.html.
Run it like this (after 04_train.py):
    ~/venvs/vision/bin/python 06_export_viz.py
Output: ../../media/jenga_net_explorer.html (open it in any browser, no internet needed)
"""
import base64
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision.io import decode_image
from torchvision.transforms import v2

from jenga_model import (CATEGORIES, DATA, IMG, box_error_px, camera_matrix, crop_square, describe, load_model, prepare,
                         rotation_error_deg, solve_pose_on_table, top_face)

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "media/jenga_net_explorer.html"
LAYERS = ["layer1", "layer2", "layer3", "layer4"]   # ResNet-18's 4 stages
NODES = [8, 8, 8, 12]   # how many neurons to show per layer (layer 4's are the 512 "features")
PER_CATEGORY = 4

model, ckpt = load_model()
rows = {r["file"]: r for r in csv.DictReader(open(DATA / "labels.csv"))}
test_files = sorted(ckpt["test_files"])
resize = v2.Resize((IMG, IMG), antialias=True)

# A "hook" lets us peek at each layer's output while the picture passes through
seen = {}
for name in LAYERS:
    getattr(model.body, name).register_forward_hook(lambda mod, inp, out, name=name: seen.__setitem__(name, out))
model.corner_head.register_forward_hook(lambda mod, inp, out: seen.__setitem__("heat", out))


def run(x):
    with torch.no_grad():
        scores, corners = model(prepare(x))
    # head B's 4 corner heat maps -> one picture: each map scaled so its hottest square is 1, then overlaid
    p = seen["heat"].flatten(2).softmax(-1).view_as(seen["heat"])
    heat = (p / p.amax(dim=(2, 3), keepdim=True)).amax(dim=1, keepdim=True)
    return scores.softmax(1), corners, heat, {k: seen[k].clone() for k in LAYERS}


# 1. Run all test images to learn each neuron's typical range
probs, means = [], {k: [] for k in LAYERS}
for i in range(0, len(test_files), 50):
    p, _, _, a = run(torch.stack([resize(decode_image(str(DATA / "images" / f))) for f in test_files[i:i + 50]]))
    probs.append(p)
    for k in LAYERS:
        means[k].append(a[k].mean(dim=(2, 3)))       # one number per neuron: its average firing
probs = torch.cat(probs)
means = {k: torch.cat(v) for k, v in means.items()}
strongest = {k: means[k].max(0).values for k in LAYERS}   # each neuron's strongest firing on any test image

# 2. Choose neurons to show: in layers 1-3, the ones that change most between pictures;
#    in layer 4, the features that matter most to the category head
weights = model.category_head.weight.detach()
chosen = {}
for k, n in zip(LAYERS, NODES):
    importance = weights.abs().sum(0) * means[k].std(0) if k == "layer4" else means[k].std(0)
    chosen[k] = importance.argsort(descending=True)[:n].tolist()

# 3. Choose pictures: 4 rendered test pictures per category (a mistake goes last, if any)...
truth = [CATEGORIES.index(rows[f]["category"]) for f in test_files]
guess = probs.argmax(1).tolist()
items = []
for c in range(3):
    mine = [i for i in range(len(test_files)) if truth[i] == c]
    wrong = [i for i in mine if guess[i] != c][:1]
    right = [i for i in mine if guess[i] == c]
    step = max(1, len(right) // (PER_CATEGORY - len(wrong)))
    for i in right[::step][:PER_CATEGORY - len(wrong)] + wrong:
        f, r = test_files[i], rows[test_files[i]]
        num = lambda keys: [float(r[k]) for k in keys]
        items.append(dict(kind="rendered", jpeg=(DATA / "images" / f).read_bytes(),
                          x=resize(decode_image(str(DATA / "images" / f))), cat=truth[i], note="",
                          top=num([f"{a}{n}" for n in range(1, 5) for a in "xy"]),
                          box=num([f"b{a}{n}" for n in range(1, 9) for a in "xy"]),
                          lens=float(r["lens_mm"]), up=num(["up_x", "up_y", "up_z"]),
                          rot=num(["rot_x", "rot_y", "rot_z"]), pos=num(["pos_x_cm", "pos_y_cm", "pos_z_cm"])))

# ...plus every real photo crop from real_crops.csv (no exact corners for these)
real_csv, real_dir = HERE / "real_crops.csv", DATA / "real"
credits = []
if real_csv.exists() and (real_dir / "credits.csv").exists():
    photo_info = {int(r["number"]): r for r in csv.DictReader(open(real_dir / "credits.csv"))}
    files = {n: r["file"] for n, r in photo_info.items()}
    used = dict.fromkeys(int(p["photo"]) for p in csv.DictReader(open(real_csv)))
    # Creative Commons licenses require credit wherever the photos appear
    credits = [{k: photo_info[n][k] for k in ("title", "creator", "license", "source")} for n in used]
    for p in csv.DictReader(open(real_csv)):
        sq = crop_square(cv2.imread(str(real_dir / "photos" / files[int(p["photo"])])), int(p["cx"]), int(p["cy"]), int(p["side"]))
        items.append(dict(kind="real", jpeg=cv2.imencode(".jpg", cv2.resize(sq, (256, 256)), [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes(),
                          x=torch.from_numpy(sq[:, :, ::-1].copy()).permute(2, 0, 1),
                          cat=None if p["label"] == "unsure" else CATEGORIES.index(p["label"]), note=p["note"], top=None))


# 4. Run them and record everything the page needs
def encode(m):
    """A map of firing strengths (0-1) -> compact text the web page can turn back into pixels."""
    return base64.b64encode(m.clamp(0, 1).mul(255).byte().numpy().tobytes()).decode()


def clockwise(points):
    """4 (x, y) points sorted clockwise on screen, starting from the top one."""
    cx, cy = sum(p[0] for p in points) / 4, sum(p[1] for p in points) / 4
    p = sorted(points, key=lambda q: math.atan2(q[1] - cy, q[0] - cx))
    start = min(range(4), key=lambda i: p[i][1])
    return [v for q in p[start:] + p[:start] for v in q]


def pose_guess(box_px, it, head_cat):
    """For Blender pictures we know the lens and which way is up, so PnP can give the full 3D answer:
    head A picks the face, and PnP on the table finds the spin and position."""
    if it["top"] is None:
        return dict(box=box_px, top=None, desc=None, pose_cat=None, distance=None, rot_err=None, box_err=None)
    K = camera_matrix(it["lens"])
    geometry_cat, _, _, _ = solve_pose_on_table(box_px, K, it["up"])          # what geometry alone would say
    _, rvec, tvec, _ = solve_pose_on_table(box_px, K, it["up"], only=[head_cat])
    pts = np.reshape(box_px, (8, 2))
    top = clockwise([tuple(pts[k]) for k in top_face(rvec, tvec, it["up"])])
    return dict(box=box_px, top=top, desc=describe(top), pose_cat=CATEGORIES.index(geometry_cat),
                distance=float(np.linalg.norm(tvec)), rot_err=rotation_error_deg(rvec, it["rot"]),
                box_err=box_error_px(torch.tensor(box_px) / 256, torch.tensor(it["box"]) / 256).item())


p_all, c_all, h_all, acts = run(torch.stack([it["x"] for it in items]))
samples = []
for j, it in enumerate(items):
    guess = pose_guess((c_all[j] * 256).tolist(), it, CATEGORIES[int(p_all[j].argmax())])
    ladder_heat = dict(size=h_all.shape[-1], map=encode(h_all[j, 0]))   # head B's corner heat map
    layers, ladder = [], []
    for k in LAYERS:
        a = acts[k][j]                                   # this picture's maps in layer k
        avg = a.mean(dim=(1, 2))
        vals = [min(1.0, avg[ch].item() / strongest[k][ch].item()) for ch in chosen[k]]
        maps = [encode(a[ch] / max(acts[k][:, ch].max().item(), 1e-6)) for ch in chosen[k]]
        layers.append(dict(vals=vals, maps=maps, size=a.shape[-1]))
        # "ladder": the 4 neurons that fired most for THIS picture, to show the block getting more abstract
        top4 = avg.argsort(descending=True)[:4].tolist()
        ladder.append(dict(channels=top4, size=a.shape[-1], maps=[encode(a[ch] / max(a[ch].max().item(), 1e-6)) for ch in top4]))
    samples.append(dict(
        kind=it["kind"], note=it["note"],
        img="data:image/jpeg;base64," + base64.b64encode(it["jpeg"]).decode(),
        truth=dict(cat=it["cat"], box=it.get("box"), top=it["top"], desc=describe(it["top"]) if it["top"] else None,
                   distance=float(np.linalg.norm(it["pos"])) if it["top"] else None),
        guess=dict(cat=int(p_all[j].argmax()), probs=p_all[j].tolist(), **guess),
        layers=layers, ladder=ladder, heat=ladder_heat,
        features=[acts["layer4"][j, ch].mean().item() for ch in chosen["layer4"]],
    ))

real_results = real_dir / "results.json"
feat = chosen["layer4"]
data = dict(
    categories=CATEGORIES,
    layers=[dict(name=k, channels=chosen[k], total=int(means[k].shape[1])) for k in LAYERS],
    heads=dict(category=model.category_head.weight[:, feat].tolist()),
    samples=samples,
    history=ckpt["history"],
    results=ckpt["results"],
    real={k: v for k, v in json.loads(real_results.read_text()).items() if k != "crops"} if real_results.exists() else None,
    credits=credits,
)

page = (HERE / "viz_template.html").read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
OUT.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
               "</head>\n<body>\n" + page + "\n</body>\n</html>\n")
print(f"Saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): {len(samples)} pictures")
