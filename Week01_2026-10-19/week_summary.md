# Week 1: Oct 19 – 25, 2026

We worked three days this week.

- **Friday:** Set up this notebook, installed the arm's Python library, and wrote the first three lessons.
- **Saturday:** Trained a program to find Jenga blocks in pictures. We had no hardware, so it learned from fake pictures made in Blender (a 3D art program).
- **Sunday:** Connected the real arm and camera to the Windows PC, then controlled the arm with the VR headset.

## What we learned

1. **Live control needs the right arm mode.** In its normal mode, the arm lines up every target it gets and finishes them one by one. The headset sends about 30 targets a second, so the arm fell behind and kept moving after we let go. In mode 7, each new target replaces the old one, so the arm stops when you stop.
2. **Test on real photos early.** Our Jenga program scored 98% on Blender pictures but got only 8 of 18 real photos right. Real photos have many blocks crowded together, and our Blender pictures didn't.
3. **The AI model needs our own examples.** SmolVLA is an AI that looks at a camera picture, reads an instruction, and decides how the arm should move. It runs on our PC, but it was trained on a different, smaller arm. To work on ours, it needs about 50 recorded examples of our arm doing the task.

## What works

| What | Does it work? | Notes |
|---|---|---|
| PC talks to the arm over an Ethernet cable | Yes | The arm is at 192.168.1.217 |
| Reading the arm's joint angles | Yes | `01_hello_arm.py` |
| D435 camera takes color and depth pictures | Yes | `03_d435_snapshot.py` |
| Gripper reports its position | Yes | 840 out of 850, almost fully open |
| Controlling the arm with the VR headset | Yes | Version 5. The A button turns motion on and off. The last session (1:23 pm video, almost 7 minutes) was on the real arm. |
| Picking up a Jenga block with VR | Yes | In the 1:23 pm video, from 4:50 to 5:35, the gripper holds a block while the arm moves. At 6:00 it lets go. |
| Camera calibration math | On the computer only | On made-up test data, it found where the camera sits within about 2 mm and half a degree. Not done on the real arm yet. |
| Quest Pro connected to the PC by Link cable | Partly | It dropped every 1–4 minutes. We turned off USB power saving but haven't checked if that fixed it. |
| Quest Pro over school Wi-Fi | No | School Wi-Fi blocks it, so we use cables |
| Recording videos | Yes | 8 videos so far. Only the useful one is on GitHub (see below). |
| SmolVLA runs on the PC | On the computer only | Its answers are for a different arm, so we never sent them to ours |
| Jenga program on Blender pictures | On the computer only | Version 3 gets the block's type right 94% of the time and its position within about 1 cm |
| Jenga program on real photos | Not yet | It finds the right block in 19 of 21 photos, but gets its type right in only 8 of 18 |

## Not tested yet

- `02_first_move.py` (lift the tool 50 mm and back down) on the real arm
- `05_teach_mode.py` (move the arm by hand) on the real arm
- The newest VR features: the on-screen display (HUD), controller shake, and camera calibration. See the [VR teleop manual](Lesson05_VR_Teleop_Manual.md).
- The Jenga program on our own blocks with our own camera
- Training SmolVLA on our own examples, and whether our graphics card's 12 GB of memory is enough

## Still broken

- The Link cable kept dropping. We need to check if turning off USB power saving fixed it.
- In real photos, the Jenga program has trouble telling a block lying flat from one lying on its side, and its 3D boxes come out squashed.
- We haven't built the recorder for SmolVLA training examples yet.

## Videos

We only put a video on GitHub when it shows something worth seeing, like the arm picking up a block. The rest stay on the club PC in the `media/` folder.

| Video | What it shows |
|---|---|
| [vr_2026-10-25_132338.mp4](media/vr_2026-10-25_132338.mp4) | 1:23 pm, what the person in the headset saw. VR control of the real arm. The gripper picks up a block at 4:50 and lets go at 6:00. |

The other 7 videos from Sunday stay on the PC. Five are mostly recordings of the computer screen, one is a blank page, and the camera video shows a block that never moves. The 12:35 pm video does show the real arm, but it knocks a block over instead of picking it up.

To put a new video on GitHub, add a line for it at the bottom of the `.gitignore` file that starts with `!`.

## Lessons

- [Lesson 1: xArm 6 basics](Lesson01_xArm6_Core20.md)
- [Lesson 2: Setting up the Quest Pro](Lesson02_QuestPro_Teleop_Setup.md)
- [Lesson 3: VLA models (AI that controls robots)](Lesson03_VLA_Models.md)
- [Lesson 4: The Jenga block finder](Lesson04_Jenga_CNN.md)
- [Lesson 5: VR teleop manual](Lesson05_VR_Teleop_Manual.md)
- [Lesson 6: Plan for training an AI without VR](Lesson06_VLA_Plan_Without_VR.md)

## Daily logs

- [Friday, Oct 23: Notebook set up and the first three lessons](2026-10-23_Fri.md)
- [Saturday, Oct 24: Jenga program trained on Blender pictures](2026-10-24_Sat.md)
- [Sunday, Oct 25: Real arm connected and controlled with VR](2026-10-25_Sun.md)

## Words to know

| Word | Meaning |
|---|---|
| Teleop | Short for teleoperation. You move your hand and the arm copies you. |
| E-stop | The big red emergency stop button |
| Mode 7 | An arm setting where each new target replaces the old one |
| D435 | Our depth camera. It measures how far away each point in the picture is. |
| SmolVLA | The AI model we plan to train to control the arm |
| Blender | A free 3D program we used to make fake training pictures |
| Overfitting | When a program memorizes its practice pictures instead of learning from them |
| HUD | Heads-up display: information drawn on top of the camera picture, like in a fighter jet |
| Camera calibration | Measuring exactly where the camera sits on the gripper, so the program knows where the gripper will land in the picture |
