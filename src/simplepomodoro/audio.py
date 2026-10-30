"""Short generated chimes, played asynchronously through GStreamer."""
import math
import struct
import wave
from pathlib import Path
import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst


class Chimes:
    def __init__(self, cache_directory):
        Gst.init(None)
        self.player = Gst.ElementFactory.make("playbin", "chime")
        self.paths = {}
        self.error = None
        self.stop_source = 0
        directory = Path(cache_directory)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for name, notes in {"warning": [660], "phase": [660, 880], "complete": [660, 880, 1100],
                                "bell": [523], "double": [523, 784], "pip": [880]}.items():
                path = directory / f"{name}.wav"
                self._write(path, notes)
                self.paths[name] = path
        except OSError as exc:
            self.error = f"Could not prepare sounds: {exc}"
        if self.player:
            bus = self.player.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._message)
        else:
            self.error = "GStreamer audio playback is unavailable."

    @staticmethod
    def _write(path, notes):
        rate = 44100
        samples = bytearray()
        for frequency in notes:
            length = int(rate * 0.18)
            for i in range(length):
                envelope = min(1, i / 440, (length - i) / 2200)
                sample = int(10000 * envelope * math.sin(2 * math.pi * frequency * i / rate))
                samples.extend(struct.pack("<h", sample))
            samples.extend(b"\0\0" * int(rate * 0.06))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(samples)

    def _message(self, _bus, message):
        if message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            self.error = f"Audio unavailable: {error.message}"
            self.stop()
        elif message.type == Gst.MessageType.EOS:
            self.stop()

    def play(self, name, volume):
        if not self.player or name not in self.paths:
            return
        self.play_file(self.paths[name], volume)

    def play_file(self, path, volume, maximum_ms=None):
        self.stop()
        if not self.player:
            self.error = "GStreamer audio playback is unavailable."
            return
        path = Path(path)
        if not path.is_file():
            self.error = f"Sound is no longer available: {path.name}"
            return
        self.error = None
        self.player.set_property("uri", path.resolve().as_uri())
        self.player.set_property("volume", max(0.0, min(1.0, volume)))
        self.player.set_state(Gst.State.PLAYING)
        if maximum_ms:
            self.stop_source = GLib.timeout_add(maximum_ms, self._stop_limited)

    def play_choice(self, sound, volume, maximum_ms=None):
        path = sound.path if sound.path is not None else self.paths.get(sound.id.removeprefix("builtin:"))
        if path is not None:
            self.play_file(path, volume, maximum_ms)
        else:
            self.stop()
            self.error = "This sound could not be prepared. Choose another sound."

    def _stop_limited(self):
        self.stop_source = 0
        self.stop()
        return GLib.SOURCE_REMOVE

    def stop(self):
        if self.stop_source:
            GLib.source_remove(self.stop_source)
            self.stop_source = 0
        if self.player:
            self.player.set_state(Gst.State.NULL)
