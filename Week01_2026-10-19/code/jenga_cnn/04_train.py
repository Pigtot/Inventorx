"""
04_train.py: Teach a pretrained ResNet-18 two things about a Jenga photo:
  head A: is the middle block flat, on its side, or standing?      (3 scores)
  head B: where are its 8 box corners in the picture?               (8 heat maps -> 16 numbers)
Then PnP turns the 8 corners into the block's 3D position and rotation, and the rotation
tells us flat / side / standing a second way, from geometry alone. We score two PnP versions:
"free" (any 3D rotation) and "on the table" (the block rests on a face, so only its spin is free).
Final pose = head A picks the face, then PnP on the table finds the spin and position (this worked best).

Run it like this (about 15 minutes per 4,000 pictures on the M1 Max):
    ~/venvs/vision/bin/python 04_train.py
To re-score the saved network without training again (for example after changing PnP):
    ~/venvs/vision/bin/python 04_train.py --test-only
Output: ~/arm_data/jenga/models/jenga_resnet18.pt (the trained network)
        ../../media/jenga_training_curves.png
"""
import csv
import json
import math
import random
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
from torchvision.io import decode_image
from torchvision.transforms import v2

from jenga_model import (CATEGORIES, DATA, IMG, MIRROR_X, MODEL_PATH, RENDER_SIZE, JengaNet, angle_diff, box_error_px,
                         box_loss, camera_matrix, category_from_pose, corner_error_px, describe, prepare,
                         rotation_error_deg, solve_pose, solve_pose_on_table, top_face)

MEDIA = Path(__file__).resolve().parents[2] / "media"
EPOCHS = 20
BATCH = 64
LEARNING_RATE = 5e-4
WEIGHT_DECAY = 0.01  # gently pulls every weight toward zero, a guard against memorizing (v1 and v2 used 0.0001)
CORNER_WEIGHT = 10   # how much the corner score counts compared with the category score
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"   # mps = the Mac's GPU
random.seed(0)
torch.manual_seed(0)


def load_dataset():
    rows = list(csv.DictReader(open(DATA / "labels.csv")))
    resize = v2.Resize((IMG, IMG), antialias=True)
    num = lambda r, keys: [float(r[k]) for k in keys]
    d = dict(
        files=[r["file"] for r in rows],
        images=torch.stack([resize(decode_image(str(DATA / "images" / r["file"]))) for r in rows]),
        categories=torch.tensor([CATEGORIES.index(r["category"]) for r in rows]),
        # corners as fractions of the picture (0-1), so they don't change when we resize
        box=torch.tensor([num(r, [f"b{a}{i}" for i in range(1, 9) for a in "xy"]) for r in rows]) / RENDER_SIZE,
        top=torch.tensor([num(r, [f"{a}{i}" for i in range(1, 5) for a in "xy"]) for r in rows]) / RENDER_SIZE,
        lens=np.array([float(r["lens_mm"]) for r in rows]),
        up=np.array([num(r, ["up_x", "up_y", "up_z"]) for r in rows]),
        rot=np.array([num(r, ["rot_x", "rot_y", "rot_z"]) for r in rows]),
        pos=np.array([num(r, ["pos_x_cm", "pos_y_cm", "pos_z_cm"]) for r in rows]),
    )
    return d


jitter = v2.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.05)


def turn_and_flip(img, corners):
    """Turn the picture 0/90/180/270 degrees and maybe mirror it. The 8 corners move exactly with it."""
    c = corners.view(8, 2)
    k = random.randrange(4)
    img = torch.rot90(img, k, dims=(1, 2))                   # each turn is 90 degrees counterclockwise
    for _ in range(k):
        c = torch.stack([c[:, 1], 1 - c[:, 0]], dim=1)       # so (x, y) moves to (y, 1 - x)
    if random.random() < 0.5:
        img = torch.flip(img, dims=[2])                      # mirror left-right: x becomes 1 - x
        # a mirrored block only matches the 3D model if we also swap its corner numbering end-for-end
        c = torch.stack([1 - c[:, 0], c[:, 1]], dim=1)[MIRROR_X]
    return img, c.reshape(16)


def augment(batch, corners):
    """Random turns, mirrors, color, blur, and noise, so the network can't memorize its pictures."""
    imgs, cs = [], []
    for img, c in zip(batch, corners):
        img, c = turn_and_flip(jitter(img), c)
        if random.random() < 0.3:
            img = v2.functional.gaussian_blur(img, kernel_size=5, sigma=random.uniform(0.3, 1.5))
        imgs.append(img)
        cs.append(c)
    x = prepare(torch.stack(imgs).to(DEVICE))
    return x + torch.randn_like(x) * random.uniform(0, 0.1), torch.stack(cs).to(DEVICE)   # noise: like a grainy camera


def clockwise(points):
    """Sort 4 (x, y) points clockwise on screen, starting from the top one (the same order as the labels)."""
    cx, cy = points[:, 0].mean(), points[:, 1].mean()
    p = sorted(points.tolist(), key=lambda q: math.atan2(q[1] - cy, q[0] - cx))
    start = min(range(4), key=lambda i: p[i][1])
    return p[start:] + p[:start]


@torch.no_grad()
def evaluate(model, d, idx):
    """Score the network on some pictures: its two heads directly, and the 3D pose that PnP gets from its corners."""
    model.eval()
    scores, guesses = [], []
    for i in range(0, len(idx), BATCH):
        s, g = model(prepare(d["images"][idx[i:i + BATCH]].to(DEVICE)))
        scores.append(s.cpu())
        guesses.append(g.cpu())
    scores, guesses = torch.cat(scores), torch.cat(guesses)
    cats, box = d["categories"][idx], d["box"][idx]
    loss = (F.cross_entropy(scores, cats) + CORNER_WEIGHT * box_loss(guesses, box)).item()

    pnp_cats, pos_err, rot_err, tops, free_cats, free_rot = [], [], [], [], [], []
    for j, i in enumerate(idx):
        px = (guesses[j] * RENDER_SIZE).view(8, 2).numpy()
        K = camera_matrix(d["lens"][i])
        free_rvec, _ = solve_pose(px, K)                                # free PnP: any 3D rotation
        free_cats.append(CATEGORIES.index(category_from_pose(free_rvec, d["up"][i])))
        free_rot.append(rotation_error_deg(free_rvec, d["rot"][i]))
        cat, _, _, _ = solve_pose_on_table(px, K, d["up"][i])           # geometry alone picks the face
        pnp_cats.append(CATEGORIES.index(cat))
        head_cat = CATEGORIES[int(scores[j].argmax())]                  # final pose: head A picks the face,
        _, rvec, tvec, _ = solve_pose_on_table(px, K, d["up"][i], only=[head_cat])   # PnP finds spin + position
        pos_err.append(np.linalg.norm(tvec - d["pos"][i]))
        rot_err.append(rotation_error_deg(rvec, d["rot"][i]))
        tops.append(clockwise(px[top_face(rvec, tvec, d["up"][i])]))   # the network's 4 top corners
    tops = torch.tensor(tops).view(-1, 8) / RENDER_SIZE
    true_top = d["top"][idx]
    angles = [angle_diff(describe((t * RENDER_SIZE).tolist())["angle"], describe((u * RENDER_SIZE).tolist())["angle"])
              for t, u in zip(tops, true_top)]
    return dict(loss=loss,
                accuracy=(scores.argmax(1) == cats).float().mean().item(),
                pnp_accuracy=float(np.mean(np.array(pnp_cats) == cats.numpy())),
                free_pnp_accuracy=float(np.mean(np.array(free_cats) == cats.numpy())),
                free_rotation_deg_median=float(np.median(free_rot)),
                box_px=box_error_px(guesses, box).mean().item(),
                corner_px=corner_error_px(tops, true_top).mean().item(),   # top-face corners, comparable to v1/v2
                angle_deg=float(np.mean(angles)),
                position_cm=float(np.mean(pos_err)), position_cm_median=float(np.median(pos_err)),
                rotation_deg=float(np.mean(rot_err)), rotation_deg_median=float(np.median(rot_err)),
                predicted=scores.argmax(1), pnp_predicted=torch.tensor(pnp_cats), tops=tops)


def plot_curves(history):
    """Four small charts side by side, one measurement each."""
    epochs = [h["epoch"] for h in history]
    ink, muted, grid, blue, orange = "#0b0b0b", "#898781", "#e1e0d9", "#2a78d6", "#eb6834"
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.4), facecolor="#fcfcfb")
    panels = [("Loss (lower is better)", [("train", "train_loss", blue, 1), ("validation", "val_loss", orange, 1)]),
              ("Category correct, validation (%)", [("head A", "val_accuracy", blue, 100),
                                                    ("from 3D pose", "val_pnp_accuracy", orange, 100)]),
              ("Top-corner miss, validation (pixels)", [("", "val_corner_px", blue, 1)]),
              ("3D position miss, validation (cm)", [("", "val_position_cm", blue, 1)])]
    for ax, (title, series) in zip(axes, panels):
        ax.set_facecolor("#fcfcfb")
        ends = []
        for label, key, color, scale in series:
            values = [h[key] * scale for h in history]
            ax.plot(epochs, values, color=color, linewidth=2, label=label or None)
            if label:
                ends.append((values[-1], label))
        # label each line at its end (pushed apart if the ends are close), so no one has to match colors
        ends.sort()
        for i, (value, label) in enumerate(ends):
            shift = (i - (len(ends) - 1) / 2) * 11 if len(ends) > 1 else 0
            ax.annotate(label, (epochs[-1], value), xytext=(5, shift), textcoords="offset points",
                        color=ink, fontsize=9, va="center")
        ax.set_title(title, color=ink, fontsize=10, loc="left")
        ax.set_xlabel("epoch (one pass through all training images)", color=muted, fontsize=8)
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))   # epochs are whole numbers
        ax.grid(color=grid, linewidth=0.6)
        ax.tick_params(colors=muted, labelsize=8)
        for side in ["top", "right"]:
            ax.spines[side].set_visible(False)
        for side in ["left", "bottom"]:
            ax.spines[side].set_color("#c3c2b7")
        if len(series) > 1:
            ax.legend(frameon=False, fontsize=8, labelcolor=ink)
    fig.tight_layout()
    fig.savefig(MEDIA / "jenga_training_curves.png", dpi=150)


def confusion_of(truth, guess):
    m = [[0] * 3 for _ in range(3)]
    for t, g in zip(truth.tolist(), guess.tolist()):
        m[t][g] += 1
    return m


def main():
    print("Loading images...")
    d = load_dataset()
    order = list(range(len(d["files"])))
    random.shuffle(order)
    n_val = n_test = len(order) // 10      # 80% train, 10% validation, 10% test
    test, val, train = order[:n_test], order[n_test:n_test + n_val], order[n_test + n_val:]
    print(f"{len(train)} train / {len(val)} validation / {len(test)} test images, device = {DEVICE}")

    model = JengaNet().to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    steps = EPOCHS * ((len(train) + BATCH - 1) // BATCH)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=LEARNING_RATE, total_steps=steps)

    history, best = [], float("inf")
    if "--test-only" in sys.argv:              # skip training: load the saved network and its test pictures
        ckpt = torch.load(MODEL_PATH, map_location="cpu")
        best_weights, history = ckpt["weights"], ckpt["history"]
        history_note = ckpt["results"].get("history_note", "During training, the 3D pose was scored with free PnP.")
        where = {f: i for i, f in enumerate(d["files"])}
        test = [where[f] for f in ckpt["test_files"]]
    for epoch in range(1, EPOCHS + 1) if "--test-only" not in sys.argv else []:
        model.train()
        random.shuffle(train)
        total = 0.0
        for i in range(0, len(train), BATCH):
            idx = train[i:i + BATCH]
            x, c = augment(d["images"][idx], d["box"][idx])
            scores, guesses = model(x)
            loss = F.cross_entropy(scores, d["categories"][idx].to(DEVICE)) + CORNER_WEIGHT * box_loss(guesses, c)
            optimizer.zero_grad()
            loss.backward()     # work out which way to nudge every weight
            optimizer.step()    # nudge them a little
            schedule.step()
            total += loss.item() * len(idx)

        v = evaluate(model, d, val)
        history.append(dict(epoch=epoch, train_loss=total / len(train), val_loss=v["loss"],
                            val_accuracy=v["accuracy"], val_pnp_accuracy=v["pnp_accuracy"], val_box_px=v["box_px"],
                            val_corner_px=v["corner_px"], val_angle_deg=v["angle_deg"],
                            val_position_cm=v["position_cm"], val_rotation_deg=v["rotation_deg"]))
        print(f"epoch {epoch:2d}  train loss {total / len(train):.3f}  val loss {v['loss']:.3f}  "
              f"category {v['accuracy']:.1%} (from pose {v['pnp_accuracy']:.1%})  top corners {v['corner_px']:.1f} px  "
              f"position {v['position_cm']:.2f} cm  rotation {v['rotation_deg']:.1f} deg", flush=True)
        if v["loss"] < best:    # keep the version that did best on images it never trained on
            best = v["loss"]
            best_weights = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}

    # Final exam: the test images, never used for training or for picking the best version
    model.load_state_dict(best_weights)
    t = evaluate(model, d, test)
    sizes = [(describe((g * RENDER_SIZE).tolist()), describe((c * RENDER_SIZE).tolist()))
             for g, c in zip(t["tops"], d["top"][test])]
    results = dict(accuracy=t["accuracy"], pnp_accuracy=t["pnp_accuracy"], free_pnp_accuracy=t["free_pnp_accuracy"],
                   free_rotation_deg_median=t["free_rotation_deg_median"], corner_px=t["corner_px"], box_px=t["box_px"],
                   angle_deg=t["angle_deg"], position_cm=t["position_cm"], position_cm_median=t["position_cm_median"],
                   rotation_deg=t["rotation_deg"], rotation_deg_median=t["rotation_deg_median"],
                   length_px=sum(abs(g["length"] - c["length"]) for g, c in sizes) / len(sizes),
                   width_px=sum(abs(g["width"] - c["width"]) for g, c in sizes) / len(sizes),
                   confusion=confusion_of(d["categories"][test], t["predicted"]),
                   pnp_confusion=confusion_of(d["categories"][test], t["pnp_predicted"]), n_test=len(test))
    if "--test-only" in sys.argv:
        results["history_note"] = history_note
    print("\nTEST RESULTS (images the network never saw):")
    print(f"  category correct: head A {results['accuracy']:.1%}; from 3D geometry alone: on the table "
          f"{results['pnp_accuracy']:.1%}, free PnP {results['free_pnp_accuracy']:.1%}")
    print(f"  top-corner miss:  {results['corner_px']:.1f} px (on a 256 px picture); all 8 corners {results['box_px']:.1f} px")
    print(f"  angle miss:       {results['angle_deg']:.1f} deg")
    print(f"  3D position miss: {results['position_cm']:.2f} cm (median {results['position_cm_median']:.2f})")
    print(f"  3D rotation miss: {results['rotation_deg']:.1f} deg (median {results['rotation_deg_median']:.1f}; "
          f"free PnP median {results['free_rotation_deg_median']:.1f})")
    print("  confusion, head A   (rows = truth, columns = guess, flat/side/standing):", results["confusion"])
    print("  confusion, 3D geometry alone:", results["pnp_confusion"])

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(dict(weights=best_weights, categories=CATEGORIES, history=history, results=results,
                    test_files=[d["files"][i] for i in test]), MODEL_PATH)
    (MODEL_PATH.parent / "results.json").write_text(json.dumps(dict(results=results, history=history), indent=1))
    plot_curves(history)
    print("Saved", MODEL_PATH)


if __name__ == "__main__":
    main()
