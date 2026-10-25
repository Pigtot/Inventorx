# Week 1 (Oct 19 – Oct 25, 2026)

We worked three days: **Friday** (set up and learned the basics), **Saturday** (trained a Jenga-block detector on fake pictures), and **Sunday** (connected the real arm and camera, then drove the arm in VR).

## Top 3 things learned (the 20% that mattered)
1. **For live control, the arm must chase your *latest* hand position, not work through a list.** In normal mode the arm finishes every target in its queue, so our first VR test lagged and kept moving after we let go. Mode 7 replaces the old target with each new one, so letting go really means stop.
2. **Fake training pictures only help if they look like the real thing.** The Jenga network scored 98% on Blender pictures and still failed on real photos, because real photos have many blocks crowded together. Test on real data early.
3. **For a VLA, the data is 80% of the result.** SmolVLA runs on our PC, but out of the box it only knows a different robot arm. It learns *our* arm, camera, and table from about 50 good demonstrations.

## Scoreboard: what works, what was tested
✅ = works on the real hardware · 🖥️ = works, but only on the computer · ❌ = didn't work · ⬜ = not tested yet

| Thing | Status | What happened |
|---|---|---|
| PC ↔ arm over the Ethernet cable | ✅ | The arm answered at 192.168.1.217 (firmware v2.5.1) |
| `01_hello_arm.py` (read the arm's position) | ✅ | Read all 6 joint angles from the Windows PC |
| `02_first_move.py` (lift 50 mm and back) | ⬜ | No result written down |
| `05_teach_mode.py` (push the arm by hand) | ⬜ | Written, but no result written down |
| D435 camera (`03_d435_snapshot.py`) | ✅ | Color and depth pictures saved over USB 3.2 |
| Gripper reports its position | ✅ | 840 of 850 (almost wide open) |
| Gripper opens and closes from VR | ⬜ | No result written down |
| VR teleop, version 1 | ❌ | Moved the arm, but lagged and **kept moving after we let go** |
| VR teleop, version 2 | 🖥️ | Passed fake-hand tests on the PC only |
| VR teleop, version 4 | ✅ | Drove the real arm smoothly, including gripper twist, no errors |
| VR teleop, version 5 (current) | ✅ | Works on the real arm. A button turns motion on and off, and the 3D twin follows the arm. |
| Grabbing a Jenga block with teleop | ⬜ | Not tried yet |
| Quest Pro on the Link cable | ✅ but drops | Works, but dropped every 1–4 min while USB power saving was on. Not confirmed yet whether turning power saving off fixed it. |
| Quest over school Wi-Fi / Air Link | ❌ | Doesn't work, so we connect everything by cable now |
| Recording videos to `media/` | ✅ | 6 headset videos and 1 D435 video saved |
| SmolVLA (AI model) runs | 🖥️ | Predicts 50 moves in about 1.1 s on the RTX 5070 Ti, but the numbers are for a different arm. **Never sent to our arm.** |
| Fine-tuning SmolVLA on our demos | ⬜ | Need demos first |
| Jenga CNN v1 (one block per picture) | 🖥️ | 98.3% correct on Blender pictures. Real photos: 8 of 18. |
| Jenga CNN v2 (crowded scenes) | 🖥️ | Real photos: corners good on 12 of 21, but it overfit |
| Jenga CNN v3 (3D box + 3D position) | 🖥️ | About 95% correct on Blender pictures, about 3.3 cm 3D position miss, overfitting mostly fixed |
| Jenga CNN on our own blocks and camera | ⬜ | Not tried yet |
| Notebook on GitHub | ✅ | github.com/Pigtot/Inventorx |

## Big numbers of the week
| What | Number |
|---|---|
| Jenga v1, Blender test: category right | 98.3% (393 of 400) |
| Jenga v1, Blender test: corner miss | 6.0 px |
| Jenga v1 → v2, real photos: corners good / rough / wrong | 7/12/2 → **12/9/0** |
| Jenga v3, Blender validation: category right | about 95% (read off the chart) |
| Jenga v3: 3D position miss | about 3.3 cm (read off the chart) |
| SmolVLA: load / predict 50 steps | about 8 s / about 1.1 s |
| Teleop: stop after letting go | within about 20 ms |
| Teleop: top speed | 150 mm/s (code), 250 mm/s (arm's own cap) |

## Still broken / open questions
- **The Link cable dropped** every 1–4 minutes. Did turning off USB power saving fix it?
- **Jenga flat vs. side** is still hard on real photos (v2 got 5 of 18). Does v3 do better? Not tested on real photos yet.
- **Nothing has been tested with our own Jenga blocks** in front of our own D435.
- **Can our GPU's 12 GB of memory fine-tune SmolVLA?** Not tested yet.
- **The demo recorder** (teach mode + camera + gripper key) isn't built yet.

## Words to know
| Word | Meaning |
|---|---|
| **SDK** | Software Development Kit: the Python library that lets our code talk to the arm |
| **E-stop** | Emergency stop: the big red button that stops the arm instantly |
| **TCP** | Tool Center Point: the tip of the tool (gripper) the arm is moving |
| **Teleop** | Teleoperation: you move your hand and the arm copies you |
| **Mode 7** | The arm's "online planning" mode: each new target replaces the last, so moves don't pile up |
| **Queue** | A waiting line. Moves in a queue run one after another, even old ones. |
| **CNN** | Convolutional Neural Network: an AI that finds patterns in pictures |
| **Overfitting** | Memorizing the practice pictures instead of learning, like memorizing one practice test |
| **PnP** | Perspective-n-Point: math that turns corner positions in a picture into a real 3D position |
| **VLA** | Vision-Language-Action model: sees a camera picture, reads an instruction, outputs arm moves |
| **Fine-tune** | Teach an already-trained model a new, specific job using your own examples |
| **Demo / episode** | One full recorded try of a task, from start to finish |
| **WSL** | Windows Subsystem for Linux: Ubuntu running inside Windows |

## Daily logs
- [2026-10-23 (Fri): Notebook set up and the first three lessons](2026-10-23_Fri.md)
- [2026-10-24 (Sat): Jenga CNN trained on Blender pictures](2026-10-24_Sat.md)
- [2026-10-25 (Sun): First real arm connection, and VR teleop drives the arm](2026-10-25_Sun.md)
