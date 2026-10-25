"""
01_download_assets.py: Download the "ingredients" for our fake Jenga photos from Poly Haven.

- Light wood textures  -> the block's surface
- Table/floor textures -> what the block sits on
- Indoor HDRIs         -> 360-degree photos that light the 3D scene like a real room

Everything on Poly Haven is CC0 (free for any use, no credit needed). We still log it.
No login needed. About 50 MB total.
Run it like this:
    ~/venvs/vision/bin/python 01_download_assets.py
"""
import json
import random
import urllib.request
from pathlib import Path

OUT = Path.home() / "arm_data/jenga/assets"   # big files live outside OneDrive
API = "https://api.polyhaven.com"
N_TABLES = 35
N_HDRIS = 12
random.seed(0)  # same "random" picks every time, so results can be repeated

# Pale, plain woods that look like real Jenga blocks
BLOCK_WOODS = [
    "ash_veneer", "white_maple_veneer", "white_oak_veneer", "oak_veneer_01", "oak_veneer_02",
    "oak_veneer_03", "oak_veneer_04", "oak_veneer_05", "bamboo_veneer", "fine_grained_wood",
    "plywood", "coated_pine", "coated_pine_02", "japanese_sycamore", "okoume_veneer",
    "olive_veneer", "silver_oak_veneer_01", "angli_veneer",
]
TABLE_CATEGORIES = ["floor", "fabric", "plaster-concrete", "indoor", "tiles", "leather", "metal"]
TABLE_EXTRAS = ["wood_table", "wood_table_001", "wood_table_worn", "kitchen_wood", "laminate_floor"]
# Poly Haven blocks Python's default name tag, so we introduce ourselves
HEADERS = {"User-Agent": "ArmLearnClub-JengaCNN/1.0"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS)) as r:
        return r.read()


def get_json(url):
    return json.loads(fetch(url))


def download(url, path):
    if path.exists():
        return  # already have it: skip
    print("  downloading", path.name)
    path.write_bytes(fetch(url))


def table_candidates():
    """Our must-have tables first, then the rest in shuffled order."""
    names = set()
    for cat in TABLE_CATEGORIES:
        names |= set(get_json(f"{API}/assets?t=textures&c={cat}"))
    others = sorted(names - set(BLOCK_WOODS) - set(TABLE_EXTRAS))
    random.shuffle(others)
    return TABLE_EXTRAS + others


def main():
    for sub in ["wood", "table", "hdri"]:
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    credits = []

    def grab(kind, name):
        files = get_json(f"{API}/files/{name}")
        if kind == "hdri":
            url = files["hdri"]["1k"]["hdr"]["url"]       # 1k = 1024 px wide: plenty for lighting
            path = OUT / kind / f"{name}.hdr"
        elif "Diffuse" in files:
            url = files["Diffuse"]["1k"]["jpg"]["url"]    # Diffuse = the color photo of the surface
            path = OUT / kind / f"{name}.jpg"
        else:
            return False  # a few textures have no plain color photo: skip them
        download(url, path)
        credits.append(f"{kind},{name},https://polyhaven.com/a/{name},CC0")
        return True

    for name in BLOCK_WOODS:
        grab("wood", name)
    n_tables = 0
    for name in table_candidates():
        if n_tables == N_TABLES:
            break
        n_tables += grab("table", name)
    for name in random.sample(sorted(get_json(f"{API}/assets?t=hdris&c=indoor")), N_HDRIS):
        grab("hdri", name)

    (OUT / "credits.csv").write_text("kind,name,source,license\n" + "\n".join(credits) + "\n")
    print(f"Done: {len(credits)} files in {OUT}")


if __name__ == "__main__":
    main()
