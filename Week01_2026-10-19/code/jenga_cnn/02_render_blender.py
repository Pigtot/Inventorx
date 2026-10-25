"""
02_render_blender.py: Make fake Jenga photos in Blender, with perfect labels.

Each picture shows a TARGET block in the middle, resting on one of its 3 face types (the category),
often with up to 8 more blocks scattered around it, like a real pile.
Everything is random: spin, spot, camera angle, focus blur, wood, table, and lighting.
Blender knows exactly where the target's 4 top corners land in the picture,
so the labels come free: no clicking. The label is always the middle block.
Labels: its category, its 4 top corners, all 8 box corners, and its exact 3D pose
(position and rotation from the camera), plus the camera's lens and which way is "up".

Version 2 (after the real-photo test): neighbor blocks, steeper camera (up to 60 degrees),
dark wood, and focus blur, because real photos have all of these.

Run it like this (Blender runs in the background, no window opens):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P 02_render_blender.py -- 12000
The number at the end is how many images you want in total (default 12, for a quick test).
Every picture has its own random seed, so running it again re-computes ALL labels (fast)
but only renders the pictures that are missing. Delete a picture to make it again.
Output: ~/arm_data/jenga/images/*.jpg and ~/arm_data/jenga/labels.csv
"""
import csv
import math
import random
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Quaternion, Vector

DATA = Path.home() / "arm_data/jenga"
N = int(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else 12
SIZE = 256                       # pictures are 256 x 256 pixels
BLOCK = (0.075, 0.025, 0.015)    # meters: a real Jenga block is 7.5 x 2.5 x 1.5 cm
N_EXTRA = 8                      # up to this many neighbor blocks around the target
# How to turn the block for each category. It starts lying flat.
POSES = {
    "flat":     Matrix.Identity(4),                     # big face up (7.5 x 2.5 cm)
    "side":     Matrix.Rotation(math.pi / 2, 4, "X"),   # rolled onto its long side (7.5 x 1.5 cm up)
    "standing": Matrix.Rotation(math.pi / 2, 4, "Y"),   # stood on its end (2.5 x 1.5 cm up)
}
CATEGORIES = list(POSES)


# ---------- small helpers for building Blender "node" materials ----------
def node(tree, kind, **settings):
    n = tree.nodes.new(kind)
    for key, value in settings.items():
        setattr(n, key, value)
    return n


def sock(sockets, name, kind=None):
    """Find a node's plug by name (and type, since some nodes reuse names)."""
    return next(s for s in sockets if s.name == name and (kind is None or s.type == kind))


def new_tree(datablock):
    if datablock.node_tree is None:
        datablock.use_nodes = True   # older Blender needs this; newer always has nodes
    datablock.node_tree.nodes.clear()
    return datablock.node_tree


def make_surface(name, coords):
    """Photo texture -> color tweak -> tint -> surface. Returns the nodes we randomize later."""
    mat = bpy.data.materials.new(name)
    t = new_tree(mat)
    texcoord = node(t, "ShaderNodeTexCoord")
    mapping = node(t, "ShaderNodeMapping")
    tex = node(t, "ShaderNodeTexImage", projection="BOX" if coords == "Object" else "FLAT")
    hsv = node(t, "ShaderNodeHueSaturation")
    mix = node(t, "ShaderNodeMix", data_type="RGBA")
    bsdf = node(t, "ShaderNodeBsdfPrincipled")
    out = node(t, "ShaderNodeOutputMaterial")
    t.links.new(texcoord.outputs[coords], mapping.inputs["Vector"])
    t.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    t.links.new(tex.outputs["Color"], hsv.inputs["Color"])
    t.links.new(hsv.outputs["Color"], sock(mix.inputs, "A", "RGBA"))
    t.links.new(sock(mix.outputs, "Result", "RGBA"), bsdf.inputs["Base Color"])
    t.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, dict(mapping=mapping, tex=tex, hsv=hsv, mix=mix, bsdf=bsdf)


# ---------- build the scene once ----------
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"        # fast, game-style renderer
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE_NEXT"   # its name in Blender 4.2-4.5
    scene.render.resolution_x = scene.render.resolution_y = SIZE
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.view_settings.view_transform = "Standard"  # plain colors; the default washes out bright wood

    # The target block: a box with slightly rounded edges, like the real thing
    bpy.ops.mesh.primitive_cube_add(size=1)
    block = bpy.context.object
    block.scale = BLOCK
    bpy.ops.object.transform_apply(scale=True)
    bevel = block.modifiers.new("round edges", "BEVEL")
    bevel.width, bevel.segments = 0.0008, 2
    wood_mat, wood = make_surface("wood", "Object")
    block.data.materials.append(wood_mat)
    # Neighbor blocks share the same shape and wood, like blocks from one set
    extras = []
    for _ in range(N_EXTRA):
        b = block.copy()
        scene.collection.objects.link(b)
        extras.append(b)

    # The table: a big flat plane (big enough for steep camera angles)
    bpy.ops.mesh.primitive_plane_add(size=6)
    table = bpy.context.object
    table_mat, tbl = make_surface("table", "UV")
    table.data.materials.append(table_mat)

    # The room lighting: an HDRI wrapped around everything, plus a sun for sharp shadows
    world = bpy.data.worlds.new("room")
    scene.world = world
    w = new_tree(world)
    w_coord = node(w, "ShaderNodeTexCoord")
    w_map = node(w, "ShaderNodeMapping")
    w_env = node(w, "ShaderNodeTexEnvironment")
    w_bg = node(w, "ShaderNodeBackground")
    w_out = node(w, "ShaderNodeOutputWorld")
    w.links.new(w_coord.outputs["Generated"], w_map.inputs["Vector"])
    w.links.new(w_map.outputs["Vector"], w_env.inputs["Vector"])
    w.links.new(w_env.outputs["Color"], w_bg.inputs["Color"])
    w.links.new(w_bg.outputs["Background"], w_out.inputs["Surface"])
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    scene.collection.objects.link(sun)

    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.dof.focus_object = block    # when blur is on, keep the target sharp

    load = lambda folder: [bpy.data.images.load(str(p)) for p in sorted((DATA / "assets" / folder).glob("*"))]
    assets = dict(wood=load("wood"), table=load("table"), hdri=load("hdri"))
    return dict(scene=scene, block=block, extras=extras, wood=wood, tbl=tbl, w_map=w_map, w_env=w_env,
                w_bg=w_bg, sun=sun, cam=cam, assets=assets)


# ---------- randomize everything for one picture ----------
def randomize_looks(s):
    u = random.uniform
    # Wood: random texture, random patch of it, then tint toward pale Jenga tan (or, sometimes, dark wood)
    dark = random.random() < 0.3
    s["wood"]["tex"].image = random.choice(s["assets"]["wood"])
    s["wood"]["mapping"].inputs["Location"].default_value = (u(0, 1), u(0, 1), u(0, 1))
    s["wood"]["mapping"].inputs["Rotation"].default_value = (0, 0, random.choice([0, math.pi / 2]))
    s["wood"]["mapping"].inputs["Scale"].default_value = (u(3, 8),) * 3
    s["wood"]["hsv"].inputs["Saturation"].default_value = u(0.7, 1.2)
    s["wood"]["hsv"].inputs["Value"].default_value = u(0.45, 0.9) if dark else u(0.75, 1.15)
    s["wood"]["mix"].inputs["Factor"].default_value = u(0.3, 0.7) if dark else u(0.1, 0.45)
    sock(s["wood"]["mix"].inputs, "B", "RGBA").default_value = (
        (u(0.30, 0.55), u(0.12, 0.25), u(0.03, 0.10), 1) if dark else (u(0.55, 0.75), u(0.38, 0.52), u(0.18, 0.30), 1))
    s["wood"]["bsdf"].inputs["Roughness"].default_value = u(0.35, 0.8)

    # Table: any texture, any size, any color shift
    s["tbl"]["tex"].image = random.choice(s["assets"]["table"])
    s["tbl"]["mapping"].inputs["Location"].default_value = (u(0, 1), u(0, 1), 0)
    s["tbl"]["mapping"].inputs["Rotation"].default_value = (0, 0, u(0, math.tau))
    s["tbl"]["mapping"].inputs["Scale"].default_value = (u(4.5, 15),) * 3
    s["tbl"]["hsv"].inputs["Hue"].default_value = u(0.4, 0.6)
    s["tbl"]["hsv"].inputs["Saturation"].default_value = u(0.3, 1.3)
    s["tbl"]["hsv"].inputs["Value"].default_value = u(0.4, 1.4)
    s["tbl"]["mix"].inputs["Factor"].default_value = 0.0
    s["tbl"]["bsdf"].inputs["Roughness"].default_value = u(0.3, 0.9)

    # Lighting: which room, which way it faces, how bright; sun direction and strength
    s["w_env"].image = random.choice(s["assets"]["hdri"])
    s["w_map"].inputs["Rotation"].default_value = (0, 0, u(0, math.tau))
    s["w_bg"].inputs["Strength"].default_value = u(0.4, 1.6)
    s["sun"].data.energy = random.choice([0, u(0.5, 3)])
    s["sun"].data.angle = u(0.05, 0.5)   # bigger angle = softer shadow edges
    s["sun"].rotation_euler = (u(0.2, 1.0), 0, u(0, math.tau))
    s["scene"].view_settings.exposure = u(-0.7, 0.5)


def place(obj, category, x=0.0, y=0.0):
    """Turn a block to a category pose, spin it, and set it on the table at (x, y). Returns its 8 corners."""
    turn = Matrix.Rotation(random.uniform(0, math.tau), 4, "Z") @ POSES[category]
    hx, hy, hz = (d / 2 for d in BLOCK)
    corners = [turn @ Vector((cx, cy, cz)) for cx in (-hx, hx) for cy in (-hy, hy) for cz in (-hz, hz)]
    lift = -min(c.z for c in corners)    # raise it so its lowest face touches the table
    obj.matrix_world = Matrix.Translation((x, y, lift)) @ turn
    return [c + Vector((x, y, lift)) for c in corners]


def footprint(corners):
    """The block's outline seen from above: its 4 lowest corners, in order around the middle."""
    low = sorted(corners, key=lambda c: c.z)[:4]
    mx, my = sum(c.x for c in low) / 4, sum(c.y for c in low) / 4
    return sorted([(c.x, c.y) for c in low], key=lambda p: math.atan2(p[1] - my, p[0] - mx))


def overlaps(a, b):
    """Two rectangles overlap unless some edge direction separates them (the 'separating axis' test)."""
    for poly in (a, b):
        for i in range(4):
            nx, ny = poly[i][1] - poly[(i + 1) % 4][1], poly[(i + 1) % 4][0] - poly[i][0]
            pa, pb = [nx * x + ny * y for x, y in a], [nx * x + ny * y for x, y in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def place_extras(s, target_corners):
    """Scatter neighbor blocks around the target, close together but never overlapping."""
    taken = [footprint(target_corners)]
    n = 0 if random.random() < 0.2 else random.randint(1, N_EXTRA)   # some pictures keep a lone block
    shown = 0
    for i, obj in enumerate(s["extras"]):
        obj.matrix_world = Matrix.Translation((0, 0, -10))   # park unused blocks out of sight
        obj.hide_render = True
        if i >= n:
            continue
        for _ in range(30):
            r, a = random.uniform(0.03, 0.14), random.uniform(0, math.tau)
            category = random.choices(CATEGORIES, weights=[0.5, 0.35, 0.15])[0]
            fp = footprint(place(obj, category, r * math.cos(a), r * math.sin(a)))
            if not any(overlaps(fp, t) for t in taken):
                taken.append(fp)
                obj.hide_render = False
                shown += 1
                break
        else:
            obj.matrix_world = Matrix.Translation((0, 0, -10))
    return shown


def corners_visible(s, top):
    """True if no neighbor block hides any of the target's 4 top corners from the camera."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eye = s["cam"].matrix_world.translation
    for c in top:
        d = c - eye
        hit, _, _, _, obj, _ = s["scene"].ray_cast(depsgraph, eye, d.normalized(), distance=d.length - 0.002)
        if hit and obj.name != s["block"].name:
            return False
    return True


def place_camera(s, corners, top):
    """Try random camera spots until the whole target fits in the picture and its top corners are visible."""
    u = random.uniform
    cam, scene = s["cam"], s["scene"]
    for _ in range(100):
        cam.data.lens = u(30, 50)                  # mm: zoom (smaller = wider view)
        dist, tilt, aim = u(0.16, 0.34), math.radians(u(0, 60)), u(0, math.tau)
        target = Vector((u(-0.015, 0.015), u(-0.015, 0.015), 0.01))   # keep the target near the middle
        cam.location = target + dist * Vector((math.sin(tilt) * math.cos(aim),
                                               math.sin(tilt) * math.sin(aim), math.cos(tilt)))
        look = (target - cam.location).to_track_quat("-Z", "Y")
        cam.rotation_euler = (look @ Quaternion((0, 0, 1), u(0, math.tau))).to_euler()
        bpy.context.view_layer.update()
        pts = [world_to_camera_view(scene, cam, c) for c in corners]
        if all(0.04 < p.x < 0.96 and 0.04 < p.y < 0.96 for p in pts) and corners_visible(s, top):
            return pts
    return None


def top_face_pixels(corners, pts):
    """Pick the 4 highest corners and list them clockwise, starting from the one nearest the top."""
    top = sorted(range(8), key=lambda i: -corners[i].z)[:4]
    xy = [(pts[i].x * SIZE, (1 - pts[i].y) * SIZE) for i in top]   # Blender's y goes up; images go down
    cx, cy = sum(p[0] for p in xy) / 4, sum(p[1] for p in xy) / 4
    xy.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))         # clockwise on screen
    start = min(range(4), key=lambda i: xy[i][1])
    return xy[start:] + xy[:start]


def pose_labels(s):
    """The target's exact 3D pose as seen from the camera, in OpenCV's camera convention
    (x right, y down, z forward), plus the lens and which way 'up' points."""
    cam = s["cam"]
    flip = Matrix.Diagonal((1, -1, -1))     # Blender's camera looks down -z with y up; OpenCV's looks down +z with y down
    to_cam = cam.matrix_world.inverted() @ s["block"].matrix_world
    axis, angle = (flip @ to_cam.to_3x3()).to_quaternion().to_axis_angle()
    t = flip @ to_cam.translation * 100     # meters -> cm
    up = flip @ (cam.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1)))
    return [cam.data.lens, *up, *(axis * angle), *t]


def main():
    s = build_scene()
    (DATA / "images").mkdir(parents=True, exist_ok=True)
    with open(DATA / "labels.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["file", "category"] + [f"{a}{i}" for i in range(1, 5) for a in "xy"] + ["neighbors", "lens_mm"]
                     + ["up_x", "up_y", "up_z"] + [f"b{a}{i}" for i in range(1, 9) for a in "xy"]
                     + ["rot_x", "rot_y", "rot_z", "pos_x_cm", "pos_y_cm", "pos_z_cm"])
        for i in range(N):
            name = f"img_{i:05d}.jpg"
            random.seed(i)                        # each picture's own seed, so it can be remade exactly
            category = CATEGORIES[i % 3]          # equal numbers of each category
            randomize_looks(s)
            corners = place(s["block"], category)
            top = sorted(corners, key=lambda c: -c.z)[:4]
            pts = None
            while pts is None:                    # crowded scenes can hide the target: re-scatter and retry
                shown = place_extras(s, corners)
                pts = place_camera(s, corners, top)
            cam = s["cam"].data
            cam.dof.use_dof = random.random() < 0.35            # sometimes blur what's out of focus
            cam.dof.aperture_fstop = random.uniform(1.2, 4.0)  # smaller number = more blur
            path = DATA / "images" / name
            if not path.exists():                 # only render pictures we don't have yet
                s["scene"].render.filepath = str(path)
                bpy.ops.render.render(write_still=True)
            box = [(p.x * SIZE, (1 - p.y) * SIZE) for p in pts]   # all 8 corners, in the renderer's corner order
            out.writerow([name, category] + [f"{v:.2f}" for p in top_face_pixels(corners, pts) for v in p] + [shown]
                         + [f"{v:.4f}" for v in pose_labels(s)[:4]] + [f"{v:.2f}" for p in box for v in p]
                         + [f"{v:.5f}" for v in pose_labels(s)[4:]])
            f.flush()
            if i % 500 == 0:
                print(f"[jenga] {i}/{N} done", flush=True)
    print(f"[jenga] Done: {N} images in {DATA / 'images'}")


main()
