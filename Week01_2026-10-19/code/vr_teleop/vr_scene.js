// vr_scene.js: everything you see in VR, as one three.js scene (index.html runs it):
//   - the camera window: the HUD canvas from hud.js, ahead of you and turned to face you,
//   - the 3D twin of the arm (sim.js), beside the window on your right, turned so its forward is your forward,
//   - a ghost of each controller, and while you drive, a "rubber band" from where you gripped to your hand.
//     The longer the band, the farther the arm moves (bent by the curve in vr_teleop.py).
import * as THREE from "three";
import { addLights, makeTwin } from "./sim.js";

// Places, in meters from where your head was when VR started (x = right, y = up, -z = forward).
const WINDOW_SIZE = 1.0;                // the camera window's long side
const WINDOW_AT = [0, -0.05, -1.0];     // a little below eye level: easy on the neck
// The twin stands beside the window, at about its distance, so your eyes don't refocus between them. We checked every
// pose the arm can reach (any J1, up to the reach and height limits): none covers the window, either way B turns it.
// Bigger or closer, it covers the window; lower, it sits behind your right hand.
const TWIN_AT = [0.7, -0.2, -0.75];     // the twin's base
const TWIN_SCALE = 0.4;                 // 40% of real size, about 1 m away: looks as tall as a big monitor beside you
const ROOM = new THREE.Color(0x0d0f14); // the background all around you
const CYAN = 0x4fd8ff, AMBER = 0xffb347, WHITE = 0xe9f7ff;   // the HUD's colors

// A w x h rectangle (meters) with round corners of radius r, with the picture spread across it.
function roundedRect(w, h, r) {
  const shape = new THREE.Shape(), x = -w / 2, y = -h / 2;
  shape.moveTo(x + r, y);
  shape.lineTo(x + w - r, y);
  shape.quadraticCurveTo(x + w, y, x + w, y + r);
  shape.lineTo(x + w, y + h - r);
  shape.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  shape.lineTo(x + r, y + h);
  shape.quadraticCurveTo(x, y + h, x, y + h - r);
  shape.lineTo(x, y + r);
  shape.quadraticCurveTo(x, y, x + r, y);
  const geometry = new THREE.ShapeGeometry(shape, 8);
  const position = geometry.attributes.position, uv = geometry.attributes.uv;
  for (let i = 0; i < position.count; i++) uv.setXY(i, position.getX(i) / w + 0.5, position.getY(i) / h + 0.5);
  return geometry;
}

export function makeVRScene(hudCanvas) {
  const scene = new THREE.Scene();
  scene.background = ROOM;
  addLights(scene);

  // Camera window.
  const hud = new THREE.CanvasTexture(hudCanvas);
  hud.colorSpace = THREE.SRGBColorSpace;
  hud.generateMipmaps = false;   // the picture changes 30 times a second; rebuilding mipmaps each time is wasted work
  hud.minFilter = THREE.LinearFilter;
  let hudSize = "";
  const screen = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({ map: hud }));   // shaped by hudChanged()
  screen.position.set(...WINDOW_AT);
  screen.lookAt(0, 0, 0);
  scene.add(screen);

  // Twin. The arm's x (forward), y (left), z (up) become VR's -z, -x, +y, so it moves the way your hand does.
  const twin = makeTwin();
  twin.group.position.set(...TWIN_AT);
  twin.group.scale.setScalar(TWIN_SCALE);
  twin.group.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(
    new THREE.Vector3(0, 0, -1), new THREE.Vector3(-1, 0, 0), new THREE.Vector3(0, 1, 0)));
  scene.add(twin.group);

  // Controller ghosts: a capsule along each controller's handle.
  const ghost = () => {
    const mesh = new THREE.Mesh(new THREE.CapsuleGeometry(0.018, 0.06, 4, 12).rotateX(Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: WHITE, transparent: true, opacity: 0.4 }));
    mesh.matrixAutoUpdate = false;   // placed straight from the controller's pose
    scene.add(mesh);
    return mesh;
  };
  const hands = { left: ghost(), right: ghost() };

  // Rubber band: a dot where you gripped and a thin rod from there to your hand.
  const bandMaterial = new THREE.MeshBasicMaterial({ color: CYAN });
  const anchor = new THREE.Mesh(new THREE.SphereGeometry(0.008, 16, 12), bandMaterial);
  const band = new THREE.Mesh(new THREE.CylinderGeometry(0.0025, 0.0025, 1, 8), bandMaterial);
  scene.add(anchor, band);
  const grabbedAt = new THREE.Vector3(), hand = new THREE.Vector3(), UP = new THREE.Vector3(0, 1, 0);
  let wasGripping = false;

  return {
    scene,

    // Call after the HUD canvas is redrawn, so the window shows the new picture.
    hudChanged() {
      const size = `${hudCanvas.width}x${hudCanvas.height}`;
      if (size !== hudSize) {   // first picture, or B turned it: reshape the window and remake its texture
        hud.dispose();
        hudSize = size;
        const shape = hudCanvas.width / hudCanvas.height;
        screen.geometry.dispose();
        screen.geometry = shape >= 1 ? roundedRect(WINDOW_SIZE, WINDOW_SIZE / shape, 0.03) : roundedRect(WINDOW_SIZE * shape, WINDOW_SIZE, 0.03);
      }
      hud.needsUpdate = true;
    },

    // Once per frame. info = the newest answer from the PC; poses = {left, right} controller grip poses
    // (null when not tracked); grip = the right grip is pressed.
    update(info, poses, grip) {
      twin.update(info);
      for (const side of ["left", "right"]) {
        hands[side].visible = !!poses[side];
        if (poses[side]) hands[side].matrix.fromArray(poses[side].transform.matrix);
      }
      // The right ghost says what the arm will do: white = motion off, cyan = armed, bright = driving, amber = at a limit.
      const driving = info.status === "following";
      hands.right.material.color.setHex(!info.motion ? WHITE : driving && info.limit ? AMBER : CYAN);
      hands.right.material.opacity = driving ? 0.85 : 0.4;

      if (grip && !wasGripping && poses.right) grabbedAt.copy(poses.right.transform.position);
      wasGripping = grip;
      anchor.visible = band.visible = driving && grip && !!poses.right;
      if (band.visible) {
        hand.copy(poses.right.transform.position);
        bandMaterial.color.setHex(info.limit ? AMBER : CYAN);
        anchor.position.copy(grabbedAt);
        band.position.addVectors(grabbedAt, hand).multiplyScalar(0.5);   // a rod: centered between the two points,
        band.scale.y = Math.max(grabbedAt.distanceTo(hand), 1e-4);         // as long as the gap,
        band.quaternion.setFromUnitVectors(UP, hand.sub(grabbedAt).normalize());   // and pointing along it
      }
    },
  };
}
