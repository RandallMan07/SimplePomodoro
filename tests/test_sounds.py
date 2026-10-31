import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simplepomodoro.core import Config, Timer
from simplepomodoro.sounds import CountdownCues, DEFAULT_SELECTIONS, SoundLibrary, default_sound_directory


class LibraryTests(unittest.TestCase):
    def test_folder_pool_ignores_sidecars_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("bell.wav", "Bell.OGG", "bell.wav.json", "notes.txt"):
                (folder / name).write_bytes(b"test")
            (folder / "directory.mp3").mkdir()
            library = SoundLibrary(folder)
            self.assertEqual([sound.id for sound in library.sounds if sound.path], ["file:Bell.OGG", "file:bell.wav"])
            self.assertEqual(library.resolve("file:bell.wav").path, folder / "bell.wav")
            (folder / "download.flac").write_bytes(b"test")
            library.refresh()
            self.assertEqual(library.resolve("file:download.flac").id, "file:download.flac")

    def test_missing_files_and_untrusted_ids_fall_back_per_event(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "bell.wav"
            file.touch()
            library = SoundLibrary(directory)
            file.unlink()
            self.assertEqual(library.resolve("file:bell.wav", "warning").id, "builtin:warning")
            for value in (None, [], "file:../outside.wav", "builtin:unknown"):
                self.assertEqual(library.resolve(value, "complete").id, "builtin:complete")
            self.assertEqual(library.selections(["invalid"]), DEFAULT_SELECTIONS)

    def test_folder_error_retains_builtin_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "not-a-folder"
            file.touch()
            library = SoundLibrary(file)
            self.assertIn("Could not read", library.error)
            self.assertEqual(library.resolve("bad").id, "builtin:phase")

    def test_xdg_default_is_user_data_not_cache(self):
        with patch.dict("os.environ", {"XDG_DATA_HOME": "/tmp/test-sounds-data"}):
            self.assertEqual(default_sound_directory(), Path("/tmp/test-sounds-data/simplepomodoro/sounds"))


class CountdownTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.timer = Timer(Config(1, 1, 1), clock=lambda: self.now)
        self.cues = CountdownCues()
        self.cues.prime(self.timer)
        self.timer.start()

    def observe_at(self, seconds):
        self.now = seconds
        self.timer.tick()
        return self.cues.observe(self.timer)

    def test_current_boundary_is_emitted_once(self):
        self.assertIsNone(self.observe_at(56.9))
        self.assertEqual(self.observe_at(57.05), 3)
        self.assertIsNone(self.observe_at(57.1))
        self.assertEqual(self.observe_at(58.05), 2)
        self.assertEqual(self.observe_at(59.05), 1)
        self.assertIsNone(self.observe_at(60))
        self.assertEqual(self.observe_at(117), 3)
        self.assertIsNone(self.observe_at(120))

    def test_late_callback_skips_old_cues(self):
        self.assertIsNone(self.observe_at(58.7))
        self.assertEqual(self.observe_at(59.1), 1)
        self.assertIsNone(self.observe_at(1200))

    def test_pause_resume_does_not_repeat_current_second(self):
        self.assertEqual(self.observe_at(57), 3)
        self.timer.pause()
        self.now = 100
        self.assertIsNone(self.cues.observe(self.timer))
        self.cues.prime(self.timer)
        self.timer.start()
        self.assertIsNone(self.observe_at(100))
        self.assertEqual(self.observe_at(101), 2)

    def test_resume_inside_last_second_does_not_invent_cue(self):
        self.now = 59.5
        self.timer.pause()
        self.cues.prime(self.timer)
        self.timer.start()
        self.assertIsNone(self.cues.observe(self.timer))

    def test_reset_rearms_first_phase(self):
        self.assertEqual(self.observe_at(57), 3)
        self.timer.reset()
        self.cues.reset()
        self.timer.start()
        self.assertEqual(self.observe_at(114), 3)


if __name__ == "__main__":
    unittest.main()
