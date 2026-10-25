// hud.js: the Iron Man-style heads-up display drawn over the D435 picture.
// The same canvas is shown on the PC page, used as the camera screen in VR, and recorded.
// Picture coordinates: (u, v) = pixel in the camera's own 640 x 360 picture. View coordinates: pixel on the HUD canvas.

const HUD = {
  cyan: "#4fd8ff", dim: "rgba(79, 216, 255, 0.35)", faint: "rgba(79, 216, 255, 0.12)",
  white: "#e9f7ff", amber: "#ffb347",
  floor: -75, ceiling: 450,   // same as FLOOR and CEILING in vr_teleop.py (mm)
};
const HUD_TITLES = {
  following: "TRACKING HAND", "let go": "HOLDING POSITION", "waiting for headset": "AWAITING HEADSET",
  "tracking glitch": "TRACKING GLITCH", "motion off": "MOTION SAFE · PRESS A",
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

function glow(c, color, blur = 8) { c.strokeStyle = color; c.fillStyle = color; c.shadowColor = color; c.shadowBlur = blur; }

function drawHUD(c, W, H, raw, camW, camH, turns, info, pcOk, t) {
  const tf = hudTransform(W, H, camW, camH, turns);
  // 1. The camera picture, turned and scaled to fill.
  c.save();
  c.fillStyle = "#04070b";
  c.fillRect(0, 0, W, H);
  if (raw) {
    c.translate(W / 2, H / 2);
    c.rotate(tf.a);
    c.scale(tf.s, tf.s);
    c.drawImage(raw, -camW / 2, -camH / 2);
  }
  c.restore();
  // 2. A soft dark edge so the readouts stand out.
  const edge = c.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.max(W, H) * 0.75);
  edge.addColorStop(0, "rgba(0,8,16,0)");
  edge.addColorStop(1, "rgba(0,8,16,0.65)");
  c.fillStyle = edge;
  c.fillRect(0, 0, W, H);

  c.save();
  c.lineWidth = 2;
  const S = Math.min(W, H) / 540;   // size unit, so text and lines scale with the canvas
  const font = (px, bold) => `${bold ? "600 " : ""}${Math.round(px * S)}px "Segoe UI", system-ui, sans-serif`;
  const mono = (px) => `${Math.round(px * S)}px Consolas, ui-monospace, monospace`;

  // 3. Corner brackets.
  glow(c, HUD.cyan, 6);
  const m = 14 * S, L = 34 * S;
  for (const [x, y, dx, dy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]]) {
    c.beginPath(); c.moveTo(x, y + dy * L); c.lineTo(x, y); c.lineTo(x + dx * L, y); c.stroke();
  }

  // 4. Top bar: title, status, calibration, clock.
  const armed = info.motion, live = info.live;
  c.font = font(13, true);
  c.fillText("XARM-6  //  TELEOP", 30 * S, 38 * S);
  c.font = font(20, true);
  glow(c, !pcOk ? HUD.amber : armed ? HUD.cyan : HUD.white, armed ? 12 : 4);
  c.fillText(!pcOk ? "PC LINK LOST" : (live === false ? "DRY RUN · " : "") + (HUD_TITLES[info.status] ?? "STANDBY"), 30 * S, 64 * S);
  glow(c, HUD.cyan, 4);
  c.font = mono(13);
  c.textAlign = "right";
  const cal = info.calib?.done ? `CAM CALIBRATED ±${info.calib.rms} mm` : "CAM NOT CALIBRATED";
  c.fillText(new Date().toLocaleTimeString(), W - 30 * S, 38 * S);
  c.fillStyle = info.calib?.done ? HUD.cyan : HUD.amber;
  c.fillText(cal, W - 30 * S, 58 * S);
  c.textAlign = "left";

  // 5. Limit warning (amber banner).
  if (info.limit && pcOk) {
    glow(c, HUD.amber, 10);
    c.font = font(18, true);
    c.textAlign = "center";
    c.fillText(`⚠  ${info.limit.toUpperCase()}`, W / 2, 96 * S);
    c.textAlign = "left";
  }

  // 6. Landing reticle: where the gripper will touch down (needs the calibration).
  const spin = (t / 1000) % (2 * Math.PI);
  if (info.landing) {
    const [x, y] = tf.toView(info.landing[0], info.landing[1]);
    const near = info.landing[2] < 40;
    glow(c, info.holding ? HUD.amber : near ? HUD.white : HUD.cyan, 10);
    const r = 26 * S;
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.stroke();
    for (let k = 0; k < 3; k++) {   // three spinning arc pieces
      c.beginPath(); c.arc(x, y, r + 10 * S, spin + k * 2.09, spin + k * 2.09 + 1.2); c.stroke();
    }
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {   // crosshair ticks
      c.beginPath(); c.moveTo(x + dx * r * 0.45, y + dy * r * 0.45); c.lineTo(x + dx * r * 1.7, y + dy * r * 1.7); c.stroke();
    }
    c.beginPath(); c.arc(x, y, 2.5 * S, 0, 2 * Math.PI); c.fill();
    c.font = mono(15);
    c.fillText(`LAND ↓ ${info.landing[2]} mm`, x + r + 16 * S, y - 6 * S);
    if (info.holding) c.fillText("HOLDING", x + r + 16 * S, y + 14 * S);
  } else {
    glow(c, HUD.dim, 0);   // no calibration yet: a plain dashed ring in the middle
    c.setLineDash([6 * S, 6 * S]);
    c.beginPath(); c.arc(W / 2, H / 2, 30 * S, 0, 2 * Math.PI); c.stroke();
    c.setLineDash([]);
    c.font = mono(12);
    c.textAlign = "center";
    c.fillText(info.calib?.done ? "NO SURFACE BELOW" : "CALIBRATE CAMERA", W / 2, H / 2 + 50 * S);
    c.textAlign = "left";
  }
  if (info.tip_px) {   // the gripper tip itself, if it's in the picture
    const [x, y] = tf.toView(info.tip_px[0], info.tip_px[1]);
    if (x > 0 && x < W && y > 0 && y < H) {
      glow(c, HUD.cyan, 6);
      c.beginPath(); c.moveTo(x, y - 7 * S); c.lineTo(x + 7 * S, y); c.lineTo(x, y + 7 * S); c.lineTo(x - 7 * S, y); c.closePath(); c.stroke();
    }
  }

  // 7. Height ladder on the left: floor to ceiling, marker at the tool's height.
  if (info.tool) {
    const x0 = 34 * S, top = H * 0.25, bottom = H * 0.75;
    const zy = (z) => bottom - (z - HUD.floor) / (HUD.ceiling - HUD.floor) * (bottom - top);
    glow(c, HUD.dim, 0);
    c.beginPath(); c.moveTo(x0, top); c.lineTo(x0, bottom); c.stroke();
    for (let z = 0; z <= HUD.ceiling; z += 50) { c.beginPath(); c.moveTo(x0, zy(z)); c.lineTo(x0 + (z % 100 ? 6 : 12) * S, zy(z)); c.stroke(); }
    glow(c, HUD.amber, 4);
    c.beginPath(); c.moveTo(x0 - 6 * S, bottom); c.lineTo(x0 + 18 * S, bottom); c.stroke();   // the floor limit
    glow(c, HUD.cyan, 8);
    const y = zy(Math.min(Math.max(info.tool[2], HUD.floor), HUD.ceiling));
    c.beginPath(); c.moveTo(x0 + 2 * S, y); c.lineTo(x0 + 14 * S, y - 7 * S); c.lineTo(x0 + 14 * S, y + 7 * S); c.closePath(); c.fill();
    c.font = mono(14);
    c.fillText(`Z ${info.tool[2]}`, x0 + 20 * S, y + 5 * S);
  }

  // 8. Right side: gripper opening arc and turn compass.
  if (info.tool) {
    const cx = W - 70 * S, cy = H * 0.36, r = 34 * S;
    glow(c, HUD.dim, 0);
    c.beginPath(); c.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25); c.stroke();
    glow(c, info.holding ? HUD.amber : HUD.cyan, 10);
    c.lineWidth = 5 * S;
    c.beginPath(); c.arc(cx, cy, r, Math.PI * 0.75, Math.PI * (0.75 + 1.5 * (info.grip_open ?? 1))); c.stroke();
    c.lineWidth = 2;
    c.font = mono(13);
    c.textAlign = "center";
    c.fillText(`${Math.round((info.grip_open ?? 1) * 100)}%`, cx, cy + 5 * S);
    c.fillText(info.holding ? "HOLDING" : info.gripper === "closed" ? "CLOSED" : "GRIP OPEN", cx, cy + r + 18 * S);
    // Turn compass: the needle shows the gripper's turn (yaw).
    const ky = H * 0.64, kr = 28 * S, a = -(info.yaw ?? 0) * Math.PI / 180 - Math.PI / 2;
    glow(c, HUD.dim, 0);
    c.beginPath(); c.arc(cx, ky, kr, 0, 2 * Math.PI); c.stroke();
    glow(c, HUD.cyan, 8);
    c.beginPath(); c.moveTo(cx, ky); c.lineTo(cx + Math.cos(a) * kr, ky + Math.sin(a) * kr); c.stroke();
    c.fillText(`TURN ${info.yaw ?? 0}°`, cx, ky + kr + 18 * S);
    c.textAlign = "left";
  }

  // 9. Bottom bar: position and joints.
  if (info.tool) {
    glow(c, HUD.faint, 0);
    c.fillStyle = "rgba(4, 12, 20, 0.55)";
    c.fillRect(0, H - 54 * S, W, 54 * S);
    glow(c, HUD.cyan, 6);
    c.beginPath(); c.moveTo(0, H - 54 * S); c.lineTo(W, H - 54 * S); c.stroke();
    c.font = mono(16);
    c.fillText(`X ${String(info.tool[0]).padStart(4)}   Y ${String(info.tool[1]).padStart(4)}   Z ${String(info.tool[2]).padStart(4)} mm`, 30 * S, H - 28 * S);
    if (info.joints) {
      c.font = mono(11);
      glow(c, HUD.dim, 0);
      c.fillStyle = HUD.cyan;
      c.fillText(info.joints.map((j, i) => `J${i + 1} ${Math.round(j)}°`).join("  "), 30 * S, H - 10 * S);
    }
    c.textAlign = "right";
    c.font = mono(14);
    glow(c, armed ? HUD.cyan : HUD.white, armed ? 10 : 0);
    c.fillText(armed ? "◉ MOTION ARMED" : "○ MOTION SAFE", W - 30 * S, H - 22 * S);
    c.textAlign = "left";
  }
  c.restore();
}
