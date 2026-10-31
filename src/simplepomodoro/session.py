"""Validated local session snapshots, independent of GTK and audio."""
import json
import math
import os
from pathlib import Path
import tempfile
import time

from .core import Config, Timer

SCHEMA_VERSION = 1
MAX_STATE_BYTES = 65536


def snapshot(timer, wall_clock=time.time):
    """Project a copy to now without consuming the live timer's alert events."""
    now_seconds = timer.clock()
    projected = Timer(timer.config, timer.warning_seconds, clock=lambda: now_seconds)
    for name in ("index", "remaining", "running", "finished", "warned", "deadline"):
        setattr(projected, name, getattr(timer, name))
    projected.tick()
    return {
        "version": SCHEMA_VERSION,
        "saved_at_seconds": wall_clock(),
        "config": {
            "work_minutes": projected.config.work_minutes,
            "rest_minutes": projected.config.rest_minutes,
            "repetitions": projected.config.repetitions,
        },
        "warning_seconds": projected.warning_seconds,
        "index": projected.index,
        "remaining_seconds": projected.remaining,
        "running": projected.running,
        "finished": projected.finished,
        "warned": projected.warned,
    }


def restore(data, wall_clock=time.time, clock=time.monotonic):
    """Restore state and silently catch up a running timer using elapsed wall time.

    Backward wall-clock changes count as zero elapsed time. Forward changes can
    finish the session, but can never add rounds or stretch its stored duration.
    """
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported session state version.")
    configuration = data.get("config")
    if not isinstance(configuration, dict):
        raise ValueError("Invalid saved configuration.")
    values = [configuration.get(key) for key in ("work_minutes", "rest_minutes", "repetitions")]
    if any(type(value) is not int for value in values):
        raise ValueError("Invalid saved configuration.")
    config = Config(*values)
    warning_seconds = data.get("warning_seconds")
    index = data.get("index")
    if type(warning_seconds) is not int or not 0 <= warning_seconds <= 60:
        raise ValueError("Invalid saved warning interval.")
    if type(index) is not int or not 0 <= index < config.repetitions * 2:
        raise ValueError("Invalid saved phase.")
    for key in ("running", "finished", "warned"):
        if type(data.get(key)) is not bool:
            raise ValueError("Invalid saved timer flags.")
    remaining_seconds = data.get("remaining_seconds")
    saved_at_seconds = data.get("saved_at_seconds")
    for value in (remaining_seconds, saved_at_seconds):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid saved timestamp or duration.")
    now_seconds = clock()
    timer = Timer(config, warning_seconds, clock=clock)
    timer.index = index
    timer.remaining = remaining_seconds
    timer.running = data["running"]
    timer.finished = data["finished"]
    timer.warned = data["warned"]
    if timer.finished:
        if timer.running or index != config.repetitions * 2 - 1 or remaining_seconds != 0:
            raise ValueError("Invalid completed session.")
    elif not 0 < remaining_seconds <= timer.duration:
        raise ValueError("Invalid remaining phase duration.")
    if timer.running:
        # The total session is bounded by configuration, so very long absences
        # need at most 24 phase transitions and never unbounded catch-up work.
        elapsed_seconds = min(max(0, wall_clock() - saved_at_seconds), config.total_minutes * 60)
        timer.deadline = now_seconds + remaining_seconds - elapsed_seconds
        timer.tick()  # Consume historical transitions and warnings without audio.
    return timer


class SessionStore:
    def __init__(self, path, wall_clock=time.time):
        self.path = Path(path)
        self.wall_clock = wall_clock
        self.error = None

    def load(self, clock=time.monotonic):
        self.error = None
        try:
            with self.path.open("rb") as source:
                contents = source.read(MAX_STATE_BYTES + 1)
            if len(contents) > MAX_STATE_BYTES:
                raise ValueError("Session state is too large.")
            return restore(json.loads(contents), self.wall_clock, clock)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeError, OverflowError, RecursionError) as error:
            self.error = f"Saved session could not be restored: {error}"
            return None

    def save(self, timer):
        self.error = None
        temporary_path = None
        try:
            data = json.dumps(snapshot(timer, self.wall_clock), allow_nan=False, indent=2) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix=".session-", delete=False) as output:
                temporary_path = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            temporary_path.replace(self.path)
            return True
        except (OSError, ValueError, OverflowError) as error:
            self.error = f"Session could not be saved: {error}"
            return False
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
