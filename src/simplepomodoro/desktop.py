"""One-time Hyprland placement; never enforces state after opening."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

APP_ID = "io.github.simplepomodoro.App"


def opening_geometry(width, height, monitor):
    """Center the content size in the monitor's usable logical coordinates."""
    scale = monitor.get("scale", 1) or 1
    physical_width, physical_height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        physical_width, physical_height = physical_height, physical_width
    left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
    usable_width = int(physical_width / scale) - left - right
    usable_height = int(physical_height / scale) - top - bottom
    width = max(1, min(width, usable_width - 32))
    height = max(1, min(height, usable_height - 32))
    x = monitor["x"] + left + (usable_width - width) // 2
    y = monitor["y"] + top + (usable_height - height) // 2
    return width, height, x, y


def place_window(width, height, run=None, pid=None):
    """Address only this process's main window, with bounded IPC waits."""
    run = run or subprocess.run
    pid = os.getpid() if pid is None else pid

    def request(*arguments):
        result = run(["hyprctl", *arguments], capture_output=True, text=True, timeout=0.5, check=True)
        return result.stdout

    try:
        # The GTK map signal can precede Hyprland's client registration.
        for _ in range(10):
            clients = json.loads(request("-j", "clients"))
            client = next((item for item in clients if item.get("pid") == pid and item.get("class") == APP_ID and item.get("mapped", True)), None)
            if client:
                break
            time.sleep(0.1)
        else:
            raise ValueError("the application window was not registered")
        address = client["address"]
        if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            raise ValueError("invalid window address")
        monitors = json.loads(request("-j", "monitors"))
        monitor = next(item for item in monitors if item["id"] == client["monitor"])
        width, height, x, y = opening_geometry(width, height, monitor)
        selector = f"address:{address}"
        response = request("--batch", "; ".join([
            f"dispatch setfloating {selector}",
            f"dispatch resizewindowpixel exact {width} {height},{selector}",
            f"dispatch movewindowpixel exact {x} {y},{selector}",
            f"dispatch alterzorder top,{selector}",
        ]))
        if any(line.strip() != "ok" for line in response.splitlines() if line.strip()):
            raise ValueError(response.strip())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration, TypeError) as error:
        print(f"SimplePomodoro: opening placement unavailable ({error}). You can float the window with Win+T.", file=sys.stderr)


def open_floating(width, height):
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        threading.Thread(target=place_window, args=(width, height), daemon=True).start()
