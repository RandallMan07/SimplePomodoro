"""Bounded Hyprland opening placement and per-widget-cycle restoration."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
import re
import shutil
import subprocess
import sys
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
    if _hyprland_available():
        _DESKTOP_WORKER.submit(place_window, width, height)


# One queue orders initial placement, snapshot, and remap restoration.
_DESKTOP_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pomodoro-desktop")


def _hyprland_available():
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"))


def _request(run, *arguments):
    return run(["hyprctl", *arguments], capture_output=True, text=True, timeout=0.5, check=True).stdout


def _main_client(run, pid):
    for _ in range(10):
        clients = json.loads(_request(run, "-j", "clients"))
        client = next((item for item in clients if item.get("pid") == pid and item.get("class") == APP_ID and item.get("mapped", True)), None)
        if client is not None:
            if not re.fullmatch(r"0x[0-9a-fA-F]+", client.get("address", "")):
                raise ValueError("invalid window address")
            return client
        time.sleep(0.05)
    raise ValueError("the application window was not registered")


@dataclass(frozen=True)
class WindowState:
    floating: bool
    width: int
    height: int
    x: int
    y: int
    workspace: int | None


def capture_window(run=None, pid=None):
    run = run or subprocess.run
    try:
        client = _main_client(run, os.getpid() if pid is None else pid)
        width, height = client["size"]
        x, y = client["at"]
        if any(type(value) is not int for value in (width, height, x, y)) or not (1 <= width <= 32768 and 1 <= height <= 32768):
            raise ValueError("invalid window geometry")
        if type(client["floating"]) is not bool:
            raise ValueError("invalid floating state")
        workspace = client.get("workspace", {}).get("id")
        workspace = workspace if type(workspace) is int and workspace > 0 else None
        return WindowState(client["floating"], width, height, x, y, workspace)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def restore_window(state, width, height, run=None, pid=None):
    run = run or subprocess.run
    if state is None:
        place_window(width, height, run=run, pid=pid)
        return
    try:
        client = _main_client(run, os.getpid() if pid is None else pid)
        selector = f"address:{client['address']}"
        commands = []
        if state.workspace is not None:
            commands.append(f"dispatch movetoworkspacesilent {state.workspace},{selector}")
        commands.append(f"dispatch {'setfloating' if state.floating else 'settiled'} {selector}")
        if state.floating:
            commands.extend([
                f"dispatch resizewindowpixel exact {state.width} {state.height},{selector}",
                f"dispatch movewindowpixel exact {state.x} {state.y},{selector}",
            ])
        commands.append(f"dispatch focuswindow {selector}")
        response = _request(run, "--batch", "; ".join(commands))
        if any(line.strip() != "ok" for line in response.splitlines() if line.strip()):
            raise ValueError(response.strip())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        print(f"SimplePomodoro: restoring window placement unavailable ({error}).", file=sys.stderr)


def capture_for_widget(callback):
    if not _hyprland_available():
        callback(None)
        return
    future = _DESKTOP_WORKER.submit(capture_window)
    future.add_done_callback(lambda result: callback(result.result()))


def restore_after_widget(state, width, height):
    if _hyprland_available():
        _DESKTOP_WORKER.submit(restore_window, state, width, height)
