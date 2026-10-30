"""Local sound choices and countdown cues, independent of GTK/GStreamer."""
from dataclasses import dataclass
import os
from pathlib import Path


SUPPORTED_EXTENSIONS = frozenset((".wav", ".ogg", ".mp3", ".flac", ".opus", ".m4a"))
BUILTIN_NAMES = {
    "warning": "Gentle heads-up",
    "phase": "Rising chime",
    "complete": "Three-note finish",
    "bell": "Soft bell",
    "double": "Double bell",
    "pip": "Short pip",
}
DEFAULT_SELECTIONS = {event: f"builtin:{event}" for event in ("warning", "phase", "complete")}
DEFAULT_SELECTIONS["countdown"] = "builtin:pip"


def default_sound_directory():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "simplepomodoro/sounds"


@dataclass(frozen=True)
class Sound:
    id: str
    title: str
    path: Path | None = None


class SoundLibrary:
    """Scan one folder. Downloader integrations add files then call refresh()."""

    def __init__(self, directory=None):
        self.directory = (Path(directory).expanduser() if isinstance(directory, (str, Path)) and str(directory) else default_sound_directory()).absolute()
        self.sounds = []
        self.error = None
        self.refresh()

    def refresh(self):
        self.sounds = [Sound(f"builtin:{name}", title) for name, title in BUILTIN_NAMES.items()]
        self.error = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            files = sorted(self.directory.iterdir(), key=lambda path: path.name.casefold())
            for path in files:
                if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file():
                    self.sounds.append(Sound(f"file:{path.name}", path.name, path))
        except OSError as error:
            self.error = f"Could not read sound folder: {error}"
        return self.sounds

    def resolve(self, sound_id, event="phase"):
        fallback = DEFAULT_SELECTIONS.get(event, DEFAULT_SELECTIONS["phase"])
        for sound in self.sounds:
            if sound.id == sound_id and (sound.path is None or sound.path.is_file()):
                return sound
        return next(sound for sound in self.sounds if sound.id == fallback)

    def selections(self, values):
        values = values if isinstance(values, dict) else {}
        return {event: self.resolve(values.get(event), event).id for event in DEFAULT_SELECTIONS}


class CountdownCues:
    """Emit only a current boundary cue; missed seconds are never replayed."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = None
        self.seen_seconds = set()

    def prime(self, timer):
        """Mark the current second on resume so it cannot sound twice."""
        if self.phase != timer.index:
            self.phase = timer.index
            self.seen_seconds.clear()
        seconds = timer.seconds_left
        if seconds <= 3:
            self.seen_seconds.update(range(seconds, 4))

    def observe(self, timer):
        if self.phase != timer.index:
            self.phase = timer.index
            self.seen_seconds.clear()
        if not timer.running or timer.finished:
            return None
        seconds = timer.seconds_left
        if seconds not in (1, 2, 3) or seconds in self.seen_seconds:
            return None
        self.seen_seconds.update(range(seconds, 4))
        # The GTK callback runs every 100 ms. Skip a cue if its boundary is stale.
        if seconds - timer.remaining > 0.35:
            return None
        return seconds
