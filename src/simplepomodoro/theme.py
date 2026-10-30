"""Validated desktop palette loading, independent of GTK."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib

MAX_PALETTE_BYTES = 65536
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")


def rgb(color):
    return tuple(int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))


def luminance(color):
    channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb(color)]
    return sum(value * weight for value, weight in zip(channels, (0.2126, 0.7152, 0.0722)))


def readable_text(background):
    """Choose the higher-contrast black/white foreground."""
    value = luminance(background)
    return "#000000" if (value + 0.05) / 0.05 >= 1.05 / (value + 0.05) else "#ffffff"


def blend(background, foreground, amount):
    channels = [round((a * (1 - amount) + b * amount) * 255) for a, b in zip(rgb(background), rgb(foreground))]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


@dataclass(frozen=True)
class Palette:
    background: str = "#101317"
    foreground: str = "#edf1f1"
    surface: str = "#1b2127"
    border: str = "#2a343b"
    muted: str = "#9aa8ad"
    focus: str = "#a2e6cf"
    rest: str = "#b6b6f4"
    warning: str = "#f6c77b"
    control: str = "#252e36"
    input: str = "#10171d"
    primary_text: str = "#10251f"
    light: bool = False

    def definitions(self):
        return "\n".join(f"@define-color sp_{name} {value};" for name, value in vars(self).items() if name != "light") + "\n"


def parse_palette(data):
    """Only hex colors enter generated CSS; missing slots use derived/defaults."""
    default = Palette()

    def color(*names, fallback):
        for name in names:
            value = data.get(name)
            if isinstance(value, str) and COLOR_PATTERN.fullmatch(value):
                return value.lower()
        return fallback

    background = color("background", "bg", "color0", fallback=default.background)
    foreground = color("foreground", "fg", "color7", fallback=default.foreground)
    if (max(luminance(background), luminance(foreground)) + 0.05) / (min(luminance(background), luminance(foreground)) + 0.05) < 4.5:
        foreground = readable_text(background)
    focus = color("accent", "cyan", "green", "color4", fallback=default.focus)
    rest = color("magenta", "color5", fallback=default.rest)
    warning = color("yellow", "color3", fallback=default.warning)
    mode = data.get("mode")
    light = mode == "light" if mode in ("light", "dark") else luminance(background) > 0.4
    return Palette(background=background, foreground=foreground,
                   surface=blend(background, foreground, 0.06), border=blend(background, foreground, 0.20),
                   muted=blend(background, foreground, 0.68), focus=focus, rest=rest, warning=warning,
                   control=blend(background, foreground, 0.12), input=background,
                   primary_text=readable_text(focus), light=light)


class ThemeSource:
    """Poll metadata only; notice atomic rewrites and current-theme symlink swaps."""
    def __init__(self, path=None):
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.path = Path(path) if path is not None else config / "omarchy/current/theme/colors.toml"
        self.palette = Palette()
        self.signature = None
        self.reload(force=True)

    def reload(self, force=False):
        try:
            stat = self.path.stat()
            signature = (str(self.path.resolve()), stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None
        if not force and signature == self.signature:
            return False
        self.signature = signature
        self.palette = Palette()
        if signature is not None and stat.st_size <= MAX_PALETTE_BYTES:
            try:
                with self.path.open("rb") as stream:
                    contents = stream.read(MAX_PALETTE_BYTES + 1)
                if len(contents) <= MAX_PALETTE_BYTES:
                    self.palette = parse_palette(tomllib.loads(contents.decode("utf-8")))
            except (OSError, UnicodeError, tomllib.TOMLDecodeError):
                pass
        return True
