# Lesson 6: Starting Our VLA Project (No Headset Needed)

**Where we are:** Lesson 3 explained what a VLA is. On 2026-10-25 we ran SmolVLA once (`code/04_smolvla_first_look.py`). It predicted moves in about 1 second, but the numbers meant nothing for our arm, because it had only ever seen SO-100 hobby arms.
**This lesson:** what we do to teach it *our* arm, and why each step matters. The Quest headset isn't needed until much later.

---

## Core idea 1: A VLA is a copycat, so the data is 80% of the result
A VLA learns like an apprentice cook watching a chef. In each situation, it copies what the chef did.
- If the chef is sloppy, the apprentice is sloppy.
- If the chef did it two different ways, the apprentice gets confused about which to copy.
- If the chef only ever cooked in one kitchen, the apprentice is lost in a new kitchen.

The model, the code, and the GPU are mostly done for us (LeRobot and SmolVLA). **What we control is the demonstrations.** Good demos are the 20% of effort that gives 80% of the result.

## Core idea 2: The loop
```
1. Pick ONE task  →  2. Record ~50 demos  →  3. Check the data  →  4. Fine-tune  →  5. Test on the arm
        ↑                                                                               │
        └──────────── record more demos of whatever it got wrong ◄──────────────────────┘
```
| Step | What we do | Why |
|---|---|---|
| 1. Pick one task | One sentence, for example "Put the block in the box." | One task is learnable from ~50 demos. Many tasks need far more. |
| 2. Record demos | Do the task ~50 times while the computer records | This is the model's only "textbook" |
| 3. Check the data | Replay a few episodes and look at them | Bad data means a bad model, no matter how long we train (same lesson as checking labels in Lesson 4) |
| 4. Fine-tune | Train SmolVLA on our episodes, on the PC's GPU in Ubuntu | Turns the generic model into one that knows our arm, camera, and table |
| 5. Test | Let the model drive the arm, slowly, with a hand on the E-stop | Shows what it hasn't learned yet. Record more demos of those situations. |

## Core idea 3: What gets recorded
About 15 times a second, the recorder saves one snapshot with 4 parts:

| Part | What it is | Example |
|---|---|---|
| **Image** | What the D435 sees | `d435_first_color.png` |
| **State** | Where the arm is now: 6 joint angles + how open the gripper is | `[6.3, -13.8, -46.1, -2.4, 57.4, 21.9, 850]` |
| **Action** | Where the arm goes next | Usually the state one snapshot later |
| **Task** | The instruction, the same for the whole episode | "Put the block in the box." |

One full try, from start to finish, is an **episode**. Fifty episodes make a **dataset**.
We record **joint angles** (not x, y, z) because that's the kind of numbers SmolVLA learned with.

## Core idea 4: Five rules for good demos (the 20% that matters)
1. **Freeze the scene.** Clamp or tape the camera down and never move it between recording and testing. Keep the same table and lighting. Move the camera, and the model's "kitchen" has been rearranged.
2. **Vary only what you want it to handle.** Put the block on 5 marked spots and record 10 demos at each (the Hugging Face recipe from Lesson 3).
3. **Be consistent.** Approach the block the same way every time, at the same speed. Two different styles can blur into a bad in-between, like the corner-order trap in Lesson 4.
4. **Finish every episode cleanly.** If a demo goes wrong, throw it away. Don't keep it. The model copies mistakes too.
5. **Check before you train.** Replay a few episodes first. It's much cheaper than finding out after hours of training.

## Core idea 5: Driving the arm without the headset
To record demos, a person has to drive the arm somehow. Three ways that work today:

| Method | How it works | Good | Bad |
|---|---|---|---|
| **Hand-guiding (teach mode)** (our pick) | The arm goes limp (`set_mode(2)`) and you push it. A key opens and closes the gripper. | Fastest and smoothest, and the arm already knows how to do it | Your hands can show up in the camera picture, but not when the model runs alone, so the pictures don't match |
| Keyboard teleop | Keys move the gripper: arrows = forward/back/left/right, W/S = up/down, Q/E = turn | No hands in the picture. Its code gets reused for the Quest later. | Slower and jerkier, and more code to write |
| Scripted | Code picks up the block from known spots | No human effort | The model learns to copy a script, not a person |

**Why hand-guiding (decided 2026-10-25):** it's the quickest way to get smooth, natural demos, and no driving code is needed. Its two weak spots, and how we handle them:
- **Hands in the picture:** keep your hands out of the camera's view. Hold the arm farther back, not near the lens. If that isn't enough, use the record-then-replay trick (Extra).
- **Both hands are busy:** the gripper opens and closes with a key, so a teammate presses it, or you let go with one hand. The arm stays put when you let go.

## Core idea 6: How the work splits across our computer
Windows' Smart App Control blocks PyTorch, and Ubuntu (WSL) can't see USB cameras. So each side does what it can:
```
WINDOWS  (eyes + hands)                         UBUNTU in WSL  (brain)
D435 camera ─┐                                  convert episodes to LeRobot format
             ├─► recorder ─► episode files ───► fine-tune SmolVLA on the RTX 5070 Ti
xArm 6 ──────┘   (~/venvs/xarm)                 (~/venvs/lerobot)
```
- **Recording** needs only eyes and hands, so it runs on Windows, where the arm and camera scripts already work.
- **Training** needs only the brain and the episode files, so it runs in Ubuntu.
- **Testing** needs eyes and brain together, so we'll connect them at that step. Ubuntu can already reach the arm (tested 2026-10-25).

## Our first task
Our arm has UFactory's **xArm Gripper**. On 2026-10-25 it reported its position (840 out of 850, which means almost fully open), and the controller's tool settings (172 mm long, 0.82 kg) match it. So the plan is:

> **"Pick up the wooden block and put it in the box."** The block starts on one of 5 taped spots, and the box stays in one taped spot.

If it turns out no gripper is attached, the fallback is "Push the block onto the target square."

## Build order
- [ ] **Try teach mode** (`code/05_teach_mode.py`): feel how the arm moves, and check that it stays still when you let go
- [ ] **Recorder**: teach mode + camera + a key for the gripper. Saves image + state + action + task, one folder per episode.
- [ ] Record 3 test episodes and replay one to check the data
- [ ] Convert the episodes to a LeRobot dataset (Ubuntu)
- [ ] Record the real 50 (5 spots × 10)
- [ ] Fine-tune SmolVLA on the PC's GPU. Not tested yet whether 12 GB of GPU memory is enough.
- [ ] Connect camera and model, then let the model drive the arm at low speed, hand on the E-stop

## Safety
- Every new script that moves the arm: clear the workspace, hand on the E-stop, low speed first.
- When the **model** drives, expect mistakes: speed limit and safety box on, a spotter on the E-stop, and nobody within reach.

---

## Extra (optional)
- **Record-then-replay:** guide the arm by hand while the robot records only the joint angles, then let the robot replay that motion alone while the camera records. That gives hand-guided smoothness with no hand in the picture, but each demo takes twice as long.
- **Game controller:** analog sticks give smoother demos than keys, if the club has one.
- **A second camera** on the wrist: SmolVLA can use up to 3 cameras. One is enough to start.
- **Camera in Ubuntu:** a tool called `usbipd` can pass USB devices into WSL. It needs an admin to install, and it may not work well with the D435.

## Check yourself
1. Why is the data "80% of the result" for a VLA?
2. What 4 parts are saved in each snapshot?
3. Why must the camera never move between recording and testing?
4. Why throw away a bad demo instead of keeping it?
5. What are the two weak spots of hand-guiding, and how do we handle each one?
