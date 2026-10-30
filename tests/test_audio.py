"""Fake GStreamer player tests; skipped on CI without system GI bindings."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from simplepomodoro.audio import Chimes
except (ImportError, ValueError):
    Chimes = None


@unittest.skipIf(Chimes is None, "System GStreamer bindings unavailable")
class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.audio = Chimes.__new__(Chimes)
        self.audio.player = Mock()
        self.audio.stop_source = 0
        self.audio.error = None

    def test_selected_local_file_sets_uri_volume_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "a sound.wav"
            file.touch()
            with patch("simplepomodoro.audio.GLib.timeout_add", return_value=42) as timeout:
                self.audio.play_file(file, 1.5, 300)
            self.audio.player.set_property.assert_any_call("uri", file.as_uri())
            self.audio.player.set_property.assert_any_call("volume", 1.0)
            timeout.assert_called_once_with(300, self.audio._stop_limited)
            with patch("simplepomodoro.audio.GLib.source_remove") as remove:
                self.audio.stop()
            remove.assert_called_once_with(42)
            self.assertEqual(self.audio.stop_source, 0)

    def test_missing_file_stops_prior_track_and_reports_error(self):
        self.audio.play_file("/does-not-exist.wav", 0.5)
        self.assertIn("no longer available", self.audio.error)
        self.audio.player.set_property.assert_not_called()
        self.audio.player.set_state.assert_called_once()

    def test_limited_stop_can_be_followed_by_new_track(self):
        self.audio.stop_source = 42
        self.assertFalse(self.audio._stop_limited())
        self.assertEqual(self.audio.stop_source, 0)
        self.audio.player.set_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
