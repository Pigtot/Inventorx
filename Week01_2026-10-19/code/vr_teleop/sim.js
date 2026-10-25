// sim.js: a live 3D twin of our xArm 6, built from UFACTORY's official CAD parts (meshes/) and posed
// with the real arm's joint angles. It draws into the #simview canvas; index.html also shows that canvas in VR.
import * as THREE from "three";
import { STLLoader } from "./lib/STLLoader.js";

// Where each joint sits on the part before it (meters) and how it's tilted (radians), from UFACTORY's
// xarm6 kinematics file. Every joint turns about its own z axis. We checked: the real arm agrees within 3 mm.
const JOINTS = [
  { xyz: [0, 0, 0.267], rpy: [0, 0, 0] },
  { xyz: [0, 0, 0], rpy: [-Math.PI / 2, 0, 0] },
  { xyz: [0.0535, -0.2845, 0], rpy: [0, 0, 0] },
  { xyz: [0.0775, 0.3425, 0], rpy: [-Math.PI / 2, 0, 0] },
  { xyz: [0, 0, 0], rpy: [Math.PI / 2, 0, 0] },
  { xyz: [0.076, 0.097, 0], rpy: [-Math.PI / 2, 0, 0] },
];
const FLOOR = -0.075;   // the floor limit in vr_teleop.py (meters)

const canvas = document.getElementById("simview");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setSize(canvas.width, canvas.height, false);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x04070b);   // HUD look: near-black blue with cyan lines
// Camera: behind and to the right of the arm, about where the operator stands. The arm's z is "up".
const camera = new THREE.PerspectiveCamera(40, canvas.width / canvas.height, 0.01, 10);
camera.up.set(0, 0, 1);
camera.position.set(-1.05, -1.3, 0.85);
camera.lookAt(0.2, -0.02, 0.12);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.3));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(1, -1, 2);
scene.add(sun);
const floorGrid = new THREE.GridHelper(1.4, 14, 0x4fd8ff, 0x12404f);
floorGrid.rotation.x = Math.PI / 2;   // GridHelper lies in x-z; turn it into the arm's x-y floor
floorGrid.position.z = FLOOR;
scene.add(floorGrid);

const metal = new THREE.MeshStandardMaterial({ color: 0xd9dee4, metalness: 0.25, roughness: 0.45 });
const dark = new THREE.MeshStandardMaterial({ color: 0x3b434d, metalness: 0.3, roughness: 0.6 });
const loader = new STLLoader();
function addPart(file, parent, material) {
  loader.load(`meshes/${file}.stl`, (geometry) => {
    geometry.computeVertexNormals();
    parent.add(new THREE.Mesh(geometry, material));
    draw();
  });
}

// Build the chain: base -> joint1 -> link1 -> joint2 -> link2 ... -> link6 -> gripper.
const base = new THREE.Group();
scene.add(base);
addPart("link_base", base, dark);
const spins = [];   // the part of each joint that turns
let parent = base;
JOINTS.forEach((j, i) => {
  const mount = new THREE.Group();   // fixed: where the joint sits on the part before it
  mount.position.set(...j.xyz);
  mount.rotation.set(j.rpy[0], j.rpy[1], j.rpy[2], "ZYX");
  const spin = new THREE.Group();    // turns about z by the joint angle
  mount.add(spin);
  parent.add(mount);
  addPart(`link${i + 1}`, spin, metal);
  spins.push(spin);
  parent = spin;
});
addPart("gripper_base", spins[5], dark);   // the xArm Gripper bolts straight onto link6

// Blue dot: where the arm is heading (shown only while you hold the grip).
const targetDot = new THREE.Mesh(new THREE.SphereGeometry(0.012, 16, 12), new THREE.MeshBasicMaterial({ color: 0x4fd8ff }));
targetDot.visible = false;
scene.add(targetDot);

function draw() { renderer.render(scene, camera); }

// Called with each answer from the PC: {joints: [6 degrees], target: [x, y, z mm], status}.
function update(info) {
  if (info.joints) info.joints.forEach((deg, i) => (spins[i].rotation.z = deg * Math.PI / 180));
  targetDot.visible = info.status === "following" && !!info.target;
  if (targetDot.visible) targetDot.position.set(info.target[0] / 1000, info.target[1] / 1000, info.target[2] / 1000);
  draw();
}

draw();
window.sim = { canvas, update };
