# Club Engineering Notebook: UFactory xArm 6

This folder is our club's **engineering notebook** for learning the **UFactory xArm 6** (a 6-joint robot arm).
Claude reads this file at the start of every session. These are the standing rules.

## 1. How to teach me
- Explain things the way you would to a **high-school student**: plain words, define any jargon the first time, one quick analogy if it helps.
- Use the **80/20 rule**: start with the 20% of ideas/commands that get 80% of the result. Label anything else **"Extra (optional)"**. Skip edge cases unless I ask.
- Keep steps short and numbered. Show the smallest piece of code that works, then explain it line by line.
- **Safety first** whenever the real arm moves: clear the workspace, keep a hand near the E-stop (emergency stop), and run new motions at low speed first.

## 2. Folder layout
```
Arm_learn/
├── CLAUDE.md                 ← these rules
├── README.md                 ← table of contents: one line per week
├── _templates/daily_log.md   ← copy this for each workday
└── WeekNN_YYYY-MM-DD/        ← one folder per week (date = that week's Monday)
    ├── week_summary.md       ← the week in a few bullets
    ├── YYYY-MM-DD_Day.md     ← one log per workday, e.g. 2026-10-23_Fri.md
    ├── LessonNN_Topic.md     ← lesson notes written that week
    ├── code/                 ← scripts written that week
    └── media/                ← photos, videos, screenshots
```
- Week 1 starts Monday 2026-10-19. A new week folder starts each Monday (Week02_2026-10-26, Week03_2026-11-02, …).
- Only create a week folder when we actually work that week. Number weeks in order of work, not calendar weeks.

## 3. Hardware and network
- Our arm's control box IP is **192.168.1.217** (from its label). The scripts use it as `ARM_IP`.
- The Mac reaches the arm through a USB-C Ethernet adapter set manually to 192.168.1.100 / 255.255.255.0 with no router. School Wi-Fi (10.205.x.x) stays on for internet.
- Also on hand: Intel RealSense D435 depth camera, Meta Quest Pro headset (for a future teleop project).
- Mac: Apple M1 Max, 64 GB memory, macOS 26.
- Quest developer mode needs an account holder aged 18+, so an adult must set it up. Our teleop plan uses WebXR in the Quest Browser so it doesn't need developer mode (Lesson 2).
- Goal path: teleop → record ~50 demos → fine-tune SmolVLA (LeRobot) on a cloud GPU → run on the Mac (Lesson 3). The community `lerobot-robot-xarm` plugin targets the Lite 6: its connect code hardcodes IP 192.168.1.184 and it uses a Lite 6 model file and gripper, so it must be adapted for the xArm 6.

## 4. Software setup (Mac, Apple Silicon)
- xArm Python SDK (`xarm-python-sdk` 1.18.4) is installed in a virtual environment at `~/venvs/xarm`, kept outside OneDrive so OneDrive doesn't sync it. Run scripts with `~/venvs/xarm/bin/python`.
- Connecting to an IP with no arm makes `XArmAPI(ip)` raise an exception, so scripts wrap it in try/except.
- `set_position(...)` without `relative=True` fills in any missing values from the *last commanded* position, not the current one. Pass all six values, or use `relative=True`.
- No ROS 2 for now. Decided 2026-10-23: use the SDK until a project needs vision and path planning (see Week 1 Lesson 1).

## 5. End-of-workday routine
When I say something like **"end of day"**, **"wrap up"**, or **"log today"**, do all of this:
1. Make or update today's log in the current week folder, using `_templates/daily_log.md`. Fill it from what we did in the session; ask me only for what you can't know (who was there, what happened on the real arm, photos).
2. Move today's scripts into that week's `code/` and any images into `media/`. Don't leave loose files in the root.
3. Update `week_summary.md`: top 3 things learned (the 20% that mattered), what works now, what's still broken.
4. Update `README.md` so the week's line is current.
5. Tell me in 2–3 lines what you logged.

Never make up results. If I didn't say whether something worked on the arm, write "not tested yet."
