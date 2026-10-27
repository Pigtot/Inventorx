"""
07_get_real_photos.py: Download real Jenga photos from Openverse to test our network.

Openverse (openverse.org) searches millions of Creative Commons photos, mostly from Flickr.
We skip "ND" (no-derivatives) licenses, because cropping and drawing on a photo changes it.
Every photo's creator and license go into credits.csv.
Reruns keep existing credits and photo numbers. Labeled crops use the permanent
source URL; a photo's position in search results cannot change its labels.

It also makes numbered "contact sheets" (grids of small pictures) so a person can
pick the photos that show a clear single block. Picks and crops go in real_crops.csv.
Run it like this:
    ~/venvs/vision/bin/python 07_get_real_photos.py
Output: ~/arm_data/jenga/real/photos/ and ~/arm_data/jenga/real/sheets/
"""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np

OUT = Path.home() / "arm_data/jenga/real"
SEARCHES = ["jenga block", "jenga blocks", "jenga piece", "jenga", "jenga wood"]
PAGES = 12              # 20 results per page
MAX_SIDE = 1280         # shrink big photos to save space
HEADERS = {"User-Agent": "ArmLearnClub-JengaCNN/1.0"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return r.read()


def search():
    found = {}
    for q in SEARCHES:
        for page in range(1, PAGES + 1):
            url = f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(q)}&page_size=20&page={page}"
            try:
                results = json.loads(fetch(url))["results"]
            except Exception:
                break   # no more pages
            for r in results:
                if "nd" not in r["license"]:
                    found[r["id"]] = r
    return list(found.values())


def update_credits(path, saved):
    """Keep old entries (including photos missing from today's search); append new numbers."""
    old = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    rows = {r["file"]: r for r in old}
    next_number = max((int(r["number"]) for r in old), default=-1) + 1
    for name, r in sorted(saved):
        number = rows[name]["number"] if name in rows else next_number
        if name not in rows:
            next_number += 1
        rows[name] = dict(number=number, file=name, title=r["title"], creator=r.get("creator"),
                          license=f"CC {r['license'].upper()} {r.get('license_version') or ''}".strip(),
                          source=r.get("foreign_landing_url"))
    ordered = sorted(rows.values(), key=lambda r: int(r["number"]))
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["number", "file", "title", "creator", "license", "source"])
        writer.writeheader()
        writer.writerows(ordered)
    temporary.replace(path)
    return ordered


def make_sheets(rows):
    """Grids of 30 numbered pictures, so we can pick the useful ones by eye."""
    (OUT / "sheets").mkdir(exist_ok=True)
    tiles = []
    for row in rows:
        img = cv2.imread(str(OUT / "photos" / row["file"]))
        if img is None:
            continue
        h, w = img.shape[:2]
        s = 200 / max(h, w)
        tile = np.full((220, 200, 3), 255, np.uint8)
        small = cv2.resize(img, (int(w * s), int(h * s)))
        tile[:small.shape[0], :small.shape[1]] = small
        cv2.putText(tile, str(row["number"]), (4, 216), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(tile)
    for start in range(0, len(tiles), 30):
        group = tiles[start:start + 30]
        group += [np.full_like(tiles[0], 255)] * (30 - len(group))
        sheet = np.vstack([np.hstack(group[r:r + 6]) for r in range(0, 30, 6)])
        cv2.imwrite(str(OUT / "sheets" / f"sheet_{start // 30:02d}.jpg"), sheet)


def main():
    (OUT / "photos").mkdir(parents=True, exist_ok=True)
    results = search()
    print(f"Found {len(results)} photos we're allowed to crop. Downloading...")
    saved = []
    for r in results:
        name = f"{r['id']}.jpg"
        path = OUT / "photos" / name
        if not path.exists():
            try:
                img = cv2.imdecode(np.frombuffer(fetch(r["url"]), np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                continue   # some links are dead
            if img is None:
                continue
            s = min(1.0, MAX_SIDE / max(img.shape[:2]))
            cv2.imwrite(str(path), cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
        saved.append((name, r))

    rows = update_credits(OUT / "credits.csv", saved)
    make_sheets(rows)
    print(f"Saved {len(saved)} photos in {OUT / 'photos'} and contact sheets in {OUT / 'sheets'}")


if __name__ == "__main__":
    main()
