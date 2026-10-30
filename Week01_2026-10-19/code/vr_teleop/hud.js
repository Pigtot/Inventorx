// hud.js: the heads-up display drawn over the D435 picture.
// The same canvas is shown on the PC page, used as the camera window in VR, and recorded.
// Picture coordinates: (u, v) = pixel in the camera's own picture. View coordinates: pixel on the HUD canvas.

const HUD = {
  accent: "#4fd8ff", white: "#f2f4f7", dim: "rgba(242, 244, 247, 0.45)", amber: "#ffb347",
  plate: "rgba(10, 12, 16, 0.62)",   // the rounded backing behind text
  floor: -75, ceiling: 450,          // same as FLOOR and CEILING in vr_teleop.py (mm)
  depthNear: 150, depthFar: 700,     // same as DEPTH_NEAR and DEPTH_FAR in vr_teleop.py (mm)
};
const HUD_TITLES = {
  following: "Following your hand", "let go": "Holding position", "waiting for headset": "Waiting for headset",
  "tracking glitch": "Tracking lost · Release, then press A", "motion off": "Motion off · Press A", stopped: "Stopped",
  "arm error": "Arm error · Look at it, then hold B 2 s",
};

// The picture is turned by `turns` quarter turns (clockwise) and scaled by s to fill the canvas.
function hudTransform(W, H, camW, camH, turns) {
  const s = turns % 2 ? W / camH : W / camW;
  const a = turns * Math.PI / 2, c = Math.cos(a), n = Math.sin(a);
  return {
    s, a,
    toView(u, v) {   // camera pixel -> HUD canvas pixel
      const x = (u - camW / 2) * s, y = (v - camH / 2) * s;
      return [W / 2 + x * c - y * n, H / 2 + x * n + y * c];
    },
    toCam(px, py) {  // HUD canvas pixel -> camera pixel (for clicks)
      const x = px - W / 2, y = py - H / 2;
      return [(x * c + y * n) / s + camW / 2, (-x * n + y * c) / s + camH / 2];
    },
  };
}

// depth = the picture is the depth view, not color.
function drawHUD(c, W, H, raw, camW, camH, turns, info, pcOk, depth) {
  const tf = hudTransform(W, H, camW, camH, turns);
  // 1. The camera picture, turned and scaled to fill.
  c.save();
  c.fillStyle = "#000";
  c.fillRect(0, 0, W, H);
  if (raw) {
    c.translate(W / 2, H / 2);
    c.rotate(tf.a);
    c.scale(tf.s, tf.s);
    c.drawImage(raw, -camW / 2, -camH / 2);
  }
  c.restore();
  // 2. A soft dark edge so the readouts stand out.
  const edge = c.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.4, W / 2, H / 2, Math.max(W, H) * 0.75);
  edge.addColorStop(0, "rgba(0, 0, 0, 0)");
  edge.addColorStop(1, "rgba(0, 0, 0, 0.5)");
  c.fillStyle = edge;
  c.fillRect(0, 0, W, H);

  c.save();
  const S = Math.min(W, H) / 540;   // size unit, so text and lines scale with the canvas
  c.lineWidth = 2 * S;
  c.lineCap = "round";
  c.textBaseline = "middle";
  const font = (px) => `600 ${Math.round(px * S)}px -apple-system, "Segoe UI", system-ui, sans-serif`;
  const ink = (color) => { c.strokeStyle = color; c.fillStyle = color; };
  // Text on a rounded plate, so it reads over any picture. (x, y) = the plate's left, center, or right edge middle.
  const label = (text, x, y, color, px = 15, align = "left") => {
    c.font = font(px);
    const pad = px * S * 0.75, w = c.measureText(text).width + 2 * pad, h = px * S * 1.9;
    const left = align === "left" ? x : align === "right" ? x - w : x - w / 2;
    c.fillStyle = HUD.plate;
    c.beginPath(); c.roundRect(left, y - h / 2, w, h, h / 2); c.fill();
    c.fillStyle = color;
    c.textAlign = "left";
    c.fillText(text, left + pad, y);
  };

  // 3. Top: status (left) and camera calibration (right). Below them, a limit warning. Near the bottom, the depth key.
  const title = !pcOk ? "PC link lost" : (info.live === false ? "Dry run · " : "") + (HUD_TITLES[info.status] ?? "Starting");
  label(title, 20 * S, 32 * S, !pcOk || info.error ? HUD.amber : info.motion ? HUD.accent : HUD.white, 17);
  if (info.error && pcOk) label(info.error, W / 2, 120 * S, HUD.amber, 14, "center");   // which arm error
  label(info.calib?.done ? `Calibrated ±${info.calib.rms} mm` : "Not calibrated", W - 20 * S, 32 * S,
        info.calib?.done ? HUD.dim : HUD.amber, 13, "right");
  if (info.limit && pcOk) label(`At ${info.limit}`, W / 2, 76 * S, HUD.amber, 16, "center");
  if (depth) label(`Depth · red ${HUD.depthNear / 10} cm → blue ${HUD.depthFar / 10} cm`, W / 2, H - 64 * S, HUD.white, 13, "center");

  // 4. Landing ring: where the gripper will touch down (needs the calibration).
  if (info.landing) {
    const [x, y] = tf.toView(info.landing[0], info.landing[1]);
    const r = 26 * S;
    ink(info.holding ? HUD.amber : info.landing[2] < 40 ? HUD.white : HUD.accent);
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.stroke();
    c.beginPath(); c.arc(x, y, 3 * S, 0, 2 * Math.PI); c.fill();
    label(`↓ ${info.landing[2]} mm${info.holding ? " · Holding" : ""}`, x + r + 10 * S, y, HUD.white, 14);
  } else {
    ink(HUD.dim);   // no calibration or no surface: a dashed ring in the middle
    c.setLineDash([6 * S, 6 * S]);
    c.beginPath(); c.arc(W / 2, H / 2, 30 * S, 0, 2 * Math.PI); c.stroke();
    c.setLineDash([]);
    label(info.calib?.done ? "No surface below" : "Calibrate the camera", W / 2, H / 2 + 52 * S, HUD.dim, 12, "center");
  }
  if (info.tip_px) {   // the gripper tip itself, if it's in the picture
    const [x, y] = tf.toView(info.tip_px[0], info.tip_px[1]);
    if (x > 0 && x < W && y > 0 && y < H) {
      ink(HUD.accent);
      c.beginPath(); c.moveTo(x, y - 7 * S); c.lineTo(x + 7 * S, y); c.lineTo(x, y + 7 * S); c.lineTo(x - 7 * S, y); c.closePath(); c.stroke();
    }
  }
  if (!info.tool) {   // no answer from the PC yet
    c.restore();
    return;
  }

  // 5. Left: height scale from the floor limit (amber) to the ceiling, with a marker at the tool.
  const x0 = 30 * S, top = H * 0.27, bottom = H * 0.73;
  const zy = (z) => bottom - (z - HUD.floor) / (HUD.ceiling - HUD.floor) * (bottom - top);
  ink(HUD.dim);
  c.beginPath(); c.moveTo(x0, top); c.lineTo(x0, bottom); c.stroke();
  for (let z = 0; z <= HUD.ceiling; z += 100) { c.beginPath(); c.moveTo(x0, zy(z)); c.lineTo(x0 + 8 * S, zy(z)); c.stroke(); }
  ink(HUD.amber);
  c.beginPath(); c.moveTo(x0 - 6 * S, bottom); c.lineTo(x0 + 14 * S, bottom); c.stroke();
  const zMark = zy(Math.min(Math.max(info.tool[2], HUD.floor), HUD.ceiling));
  ink(HUD.accent);
  c.beginPath(); c.arc(x0, zMark, 5 * S, 0, 2 * Math.PI); c.fill();
  label(`Z ${info.tool[2]}`, x0 + 12 * S, zMark, HUD.white, 13);

  // 6. Right: how open the gripper is (arc), and which way it's turned (needle).
  const cx = W - 62 * S, cy = H * 0.38, r = 30 * S;
  ink(HUD.dim);
  c.beginPath(); c.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25); c.stroke();
  ink(info.holding ? HUD.amber : HUD.accent);
  c.lineWidth = 5 * S;
  c.beginPath(); c.arc(cx, cy, r, Math.PI * 0.75, Math.PI * (0.75 + 1.5 * (info.grip_open ?? 1))); c.stroke();
  c.lineWidth = 2 * S;
  c.font = font(13);
  c.textAlign = "center";
  ink(HUD.white);
  c.fillText(`${Math.round((info.grip_open ?? 1) * 100)}%`, cx, cy);
  c.fillText(info.holding ? "Holding" : info.gripper === "closed" ? "Closed" : "Open", cx, cy + r + 16 * S);
  const ky = H * 0.64, kr = 24 * S, a = -(info.yaw ?? 0) * Math.PI / 180 - Math.PI / 2;
  ink(HUD.dim);
  c.beginPath(); c.arc(cx, ky, kr, 0, 2 * Math.PI); c.stroke();
  ink(HUD.accent);
  c.beginPath(); c.moveTo(cx, ky); c.lineTo(cx + Math.cos(a) * kr, ky + Math.sin(a) * kr); c.stroke();
  ink(HUD.white);
  c.fillText(`Turn ${info.yaw ?? 0}°`, cx, ky + kr + 16 * S);
  c.textAlign = "left";

  // 7. Bottom: where the tool is, and the joint angles.
  const xyz = `X ${info.tool[0]}   Y ${info.tool[1]}   Z ${info.tool[2]} mm`;
  const joints = info.joints ? "   ·   " + info.joints.map((j, i) => `J${i + 1} ${Math.round(j)}°`).join("  ") : "";
  label(xyz + joints, W / 2, H - 28 * S, HUD.white, 13, "center");
  c.restore();
}
