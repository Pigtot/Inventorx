"""
04_smolvla_first_look.py: Ask a real VLA model (SmolVLA) what it would do. The arm does NOT move.

It gives the model the three inputs from Lesson 3:
    Vision:   our D435 photo (media/d435_first_color.png)
    Language: an instruction, like "Pick up the wooden block."
    State:    6 numbers about the arm (we use our xArm's joint angles)
and prints the Actions it predicts: a "chunk" of 50 future steps, 6 numbers each.

The model is lerobot/smolvla_base. It learned on SO-100 arms (small hobby arms), not our xArm 6,
so its numbers are SO-100 motor positions. NEVER send them to the real arm.

It runs in Ubuntu (WSL) because Windows Smart App Control blocks PyTorch. From PowerShell in this folder:
    wsl -- '~/venvs/lerobot/bin/python' 04_smolvla_first_look.py "Pick up the wooden block."
The first run downloads the model (about 1-2 GB).
"""
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

MODEL = "lerobot/smolvla_base"
PHOTO = Path(__file__).resolve().parent.parent / "media" / "d435_first_color.png"
ARM_STATE = [6.3, -13.8, -46.1, -2.4, 57.4, 21.9]  # our J1..J6 in degrees, from 01_hello_arm.py on 2026-10-25
SO100_MOTORS = ["pan", "lift", "elbow", "w_flex", "w_roll", "grip"]  # what the model thinks the 6 numbers are
task = sys.argv[1] if len(sys.argv) > 1 else "Pick up the wooden block."

torch.manual_seed(0)  # the model starts from random noise; a fixed seed makes runs repeatable

start = time.time()
policy = SmolVLAPolicy.from_pretrained(MODEL).to("cuda").eval()
preprocess, postprocess = make_pre_post_processors(policy.config, MODEL)
print(f"Model loaded in {time.time() - start:.0f} s")

# Photo -> numbers: height x width x 3 colors (0-255) becomes 3 x height x width (0.0-1.0).
photo = torch.from_numpy(np.array(Image.open(PHOTO).convert("RGB"))).permute(2, 0, 1).float() / 255
observation = {
    "observation.images.camera1": photo,
    "observation.state": torch.tensor(ARM_STATE),
    "task": task,
}

start = time.time()
batch = preprocess(observation)                          # resize, turn words into tokens, move to the GPU
chunk = postprocess(policy.predict_action_chunk(batch))  # 50 steps x 6 numbers, back in robot units
print(f'Instruction: "{task}" -> {chunk.shape[1]} steps predicted in {time.time() - start:.2f} s')

actions = chunk[0].float().numpy()
print("Step " + "".join(f"{m:>8}" for m in SO100_MOTORS))
for step in [0, 1, 2, 10, 25, 49]:
    print(f"{step + 1:>4} " + "".join(f"{a:8.1f}" for a in actions[step]))
print("Change from step 1 to step 50:", np.round(actions[-1] - actions[0], 1))
