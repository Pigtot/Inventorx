"""Connect Quest Browser to the existing teleop dry run over USB. Never imports the robot SDK."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

URL = "http://localhost:8000/"


def find_adb():
    found = shutil.which("adb")
    if found:
        return found
    bundled = Path("/opt/homebrew/bin/adb")
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError("Install Android Platform Tools first: brew install --cask android-platform-tools")


def run(adb, *args):
    result = subprocess.run([adb, "-d", *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def connect(adb):
    # -d selects USB only and refuses multiple USB devices. Confirm the model before changing a mapping.
    model = run(adb, "shell", "getprop", "ro.product.model")
    if "quest" not in model.lower():
        raise RuntimeError(f"The USB device is {model!r}, not a Quest headset.")
    with urllib.request.urlopen(URL + "status", timeout=5) as response:
        status = json.load(response)
    if status.get("live") is not False:
        raise RuntimeError("Start teleop without --live before checking the controllers.")
    run(adb, "reverse", "tcp:8000", "tcp:8000")
    # Explicit package: use the headset's Browser rather than a Link or store URL handler.
    opened = run(adb, "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
                 "-d", URL, "-p", "com.oculus.browser")
    if "Status: ok" not in opened:
        raise RuntimeError("The USB connection is ready, but Quest Browser did not confirm opening. "
                           f"Open {URL} in the headset's Browser. {opened}")
    print(f"Connected {model}. Teleop is open in Quest Browser at {URL}", flush=True)
    print("Put on the headset, hold both controllers, and select Enter VR.", flush=True)
    print("Release the right grip, press A, then hold the grip and move your hand. This is a dry run.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=float, default=0, metavar="SECONDS",
                        help="wait this long for developer mode and USB authorization")
    args = parser.parse_args()
    try:
        adb = find_adb()
        deadline = time.monotonic() + max(0, args.wait)
        prompted = False
        while True:
            try:
                run(adb, "get-state")
                break
            except RuntimeError:
                if not prompted:
                    print("Waiting for Quest USB access. Complete setup in Meta Quest Developer Hub", flush=True)
                    print("or the Meta Horizon phone app, then allow USB debugging in the headset.", flush=True)
                    print("A verified adult developer account is required.", flush=True)
                    prompted = True
                if time.monotonic() >= deadline:
                    raise RuntimeError("Quest is not authorized over USB. Complete headset setup, then run this again.")
                time.sleep(min(2, max(0, deadline - time.monotonic())))
        connect(adb)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Could not connect: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
