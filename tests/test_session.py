import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simplepomodoro.core import Config, Timer
from simplepomodoro.session import MAX_STATE_BYTES, SessionStore, restore, snapshot


class Clock:
    def __init__(self, now_seconds=0):
        self.now_seconds = now_seconds

    def __call__(self):
        return self.now_seconds

    def advance(self, elapsed_seconds):
        self.now_seconds += elapsed_seconds


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.monotonic = Clock(100)
        self.wall = Clock(10000)
        self.timer = Timer(Config(1, 1, 2), warning_seconds=7, clock=self.monotonic)

    def state(self):
        return snapshot(self.timer, self.wall)

    def reopen(self, data):
        return restore(data, self.wall, self.monotonic)

    def test_idle_configuration_and_custom_warning_round_trip(self):
        self.timer.configure(Config(25, 5, 4), 12)
        restored = self.reopen(self.state())
        self.assertEqual(restored.config, Config(25, 5, 4))
        self.assertEqual(restored.warning_seconds, 12)
        self.assertFalse(restored.running)
        self.assertFalse(restored.finished)
        self.assertEqual(restored.remaining, 1500)

    def test_running_session_preserves_fractional_time_and_closed_elapsed(self):
        self.timer.start()
        self.monotonic.advance(10.25)
        data = self.state()
        self.wall.advance(20.5)
        # A new process has an unrelated monotonic origin.
        self.monotonic.now_seconds = 5000
        restored = self.reopen(data)
        self.assertTrue(restored.running)
        self.assertAlmostEqual(restored.remaining, 29.25)
        self.monotonic.advance(0.25)
        self.assertEqual(restored.tick(), [])
        self.assertEqual(restored.remaining, 29)

    def test_paused_session_does_not_count_closed_elapsed(self):
        self.timer.start()
        self.monotonic.advance(12.75)
        self.timer.pause()
        data = self.state()
        self.wall.advance(100000)
        restored = self.reopen(data)
        self.assertFalse(restored.running)
        self.assertEqual(restored.remaining, 47.25)
        restored.start()
        self.monotonic.advance(1)
        restored.tick()
        self.assertEqual(restored.remaining, 46.25)

    def test_closed_elapsed_crosses_multiple_phases_and_rounds(self):
        self.timer.start()
        data = self.state()
        self.wall.advance(125.5)
        restored = self.reopen(data)
        self.assertEqual(restored.index, 2)
        self.assertEqual(restored.repetition, 2)
        self.assertEqual(restored.remaining, 54.5)
        self.assertEqual(restored.tick(), [])

    def test_reopen_at_phase_boundary_and_final_break(self):
        self.timer.start()
        data = self.state()
        self.wall.advance(60)
        restored = self.reopen(data)
        self.assertEqual(restored.index, 1)
        self.assertEqual(restored.remaining, 60)
        self.wall.advance(120)
        restored = self.reopen(data)
        self.assertEqual(restored.index, 3)
        self.assertTrue(restored.running)
        self.assertEqual(restored.remaining, 60)

    def test_finished_while_closed_is_silent_and_persists_completion(self):
        self.timer.start()
        data = self.state()
        self.wall.advance(1000000)
        restored = self.reopen(data)
        self.assertFalse(restored.running)
        self.assertTrue(restored.finished)
        self.assertEqual(restored.remaining, 0)
        self.assertEqual(restored.index, 3)
        self.assertEqual(restored.tick(), [])
        again = self.reopen(snapshot(restored, self.wall))
        self.assertTrue(again.finished)
        self.assertEqual(again.tick(), [])

    def test_no_old_warning_on_reopen_but_next_phase_warns(self):
        self.timer.start()
        data = self.state()
        self.wall.advance(54)
        restored = self.reopen(data)
        self.assertTrue(restored.warned)
        self.assertEqual(restored.tick(), [])
        self.monotonic.advance(59)
        self.assertEqual(restored.tick(), ["phase", "warning"])

    def test_pause_resume_does_not_repeat_saved_warning(self):
        self.timer.start()
        self.monotonic.advance(54)
        self.assertEqual(self.timer.tick(), ["warning"])
        self.timer.pause()
        restored = self.reopen(self.state())
        restored.start()
        self.assertEqual(restored.tick(), [])

    def test_reset_cannot_restore_previous_active_session(self):
        self.timer.start()
        self.monotonic.advance(130)
        self.timer.tick()
        self.timer.reset()
        data = self.state()
        self.wall.advance(100)
        restored = self.reopen(data)
        self.assertEqual(restored.index, 0)
        self.assertEqual(restored.remaining, 60)
        self.assertFalse(restored.running)
        self.assertFalse(restored.finished)

    def test_backward_clock_change_does_not_extend_saved_remaining(self):
        self.timer.start()
        self.monotonic.advance(20)
        data = self.state()
        self.wall.advance(-100)
        restored = self.reopen(data)
        self.assertEqual(restored.remaining, 40)

    def test_snapshot_does_not_consume_live_transitions(self):
        self.timer.start()
        self.monotonic.advance(65)
        data = self.state()
        self.assertEqual(data["index"], 1)
        self.assertEqual(data["remaining_seconds"], 55)
        self.assertEqual(self.timer.index, 0)
        self.assertEqual(self.timer.tick(), ["phase"])

    def test_invalid_values_are_rejected(self):
        data = self.state()
        changes = {
            "version": [True, 0, 999, "1"],
            "config": [None, [], {"work_minutes": True, "rest_minutes": 1, "repetitions": 2}, {"work_minutes": 1, "rest_minutes": 1, "repetitions": 13}],
            "warning_seconds": [True, -1, 61, "7"],
            "index": [True, -1, 4, 0.5],
            "remaining_seconds": [True, -1, 0, 61, float("nan"), float("inf"), "30"],
            "saved_at_seconds": [True, -1, float("nan"), float("inf"), None],
            "running": [1, "false", None],
            "finished": [0, "true", None],
            "warned": [1, "false", None],
        }
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    invalid = copy.deepcopy(data)
                    invalid[key] = value
                    with self.assertRaises(ValueError):
                        self.reopen(invalid)
        for invalid in (None, [], {}, {"version": 1}):
            with self.assertRaises(ValueError):
                self.reopen(invalid)

    def test_invalid_completed_state_is_rejected(self):
        data = self.state()
        data.update(finished=True, index=3, remaining_seconds=0)
        self.assertTrue(self.reopen(data).finished)
        for changes in ({"running": True}, {"index": 2}, {"remaining_seconds": 1}):
            invalid = dict(data, **changes)
            with self.assertRaises(ValueError):
                self.reopen(invalid)


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "nested/session.json")
        self.store = SessionStore(self.path, wall_clock=lambda: 10000)
        self.timer = Timer(Config(1, 1, 1), clock=lambda: 100)

    def test_missing_state_is_normal_first_launch(self):
        self.assertIsNone(self.store.load())
        self.assertIsNone(self.store.error)

    def test_atomic_save_and_load(self):
        self.timer.start()
        self.assertTrue(self.store.save(self.timer))
        self.assertEqual(json.loads(self.path.read_text())["running"], True)
        restored = self.store.load(clock=lambda: 500)
        self.assertTrue(restored.running)
        self.assertEqual(restored.remaining, 60)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_corrupt_unicode_json_and_oversized_state_are_nonfatal(self):
        self.path.parent.mkdir()
        deeply_nested = b"[" * 1100 + b"0" + b"]" * 1100
        oversized_number = json.dumps(dict(snapshot(self.timer), saved_at_seconds=10 ** 1000)).encode()
        for contents in (b"{", b"\xff", b"null", b"[]", deeply_nested, oversized_number, b" " * (MAX_STATE_BYTES + 1)):
            with self.subTest(contents=contents[:10]):
                self.path.write_bytes(contents)
                self.assertIsNone(self.store.load())
                self.assertIn("could not be restored", self.store.error)

    def test_failed_replace_preserves_previous_snapshot_and_cleans_temp(self):
        self.assertTrue(self.store.save(self.timer))
        previous = self.path.read_bytes()
        self.timer.start()
        with patch.object(Path, "replace", side_effect=PermissionError("read-only")):
            self.assertFalse(self.store.save(self.timer))
        self.assertIn("could not be saved", self.store.error)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_directory_access_error_is_nonfatal(self):
        self.path.parent.write_text("not a directory")
        self.assertFalse(self.store.save(self.timer))
        self.assertIsNotNone(self.store.error)


if __name__ == "__main__":
    unittest.main()
