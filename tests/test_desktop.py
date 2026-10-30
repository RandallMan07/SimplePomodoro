import json
import subprocess
import unittest
from unittest.mock import patch
from simplepomodoro.desktop import APP_ID, opening_geometry, place_window


class PlacementTests(unittest.TestCase):
    def test_fractional_scale_and_reserved_bars(self):
        monitor = dict(width=2560, height=1440, scale=1.25, x=0, y=0, reserved=[0, 40, 0, 0])
        self.assertEqual(opening_geometry(900, 800, monitor), (900, 800, 574, 196))

    def test_portrait_and_negative_monitor_coordinates(self):
        monitor = dict(width=1920, height=1080, scale=1, transform=3, x=-1080, y=0)
        self.assertEqual(opening_geometry(900, 800, monitor), (900, 800, -990, 560))

    def test_oversized_content_stays_within_monitor(self):
        monitor = dict(width=1280, height=720, scale=1, x=0, y=0, reserved=[0, 30, 0, 0])
        self.assertEqual(opening_geometry(1400, 900, monitor), (1248, 658, 16, 46))

    def test_only_current_process_and_app_are_changed(self):
        calls = []
        clients = [dict(pid=123, **{"class": "other-app"}, address="0xa", monitor=0),
                   dict(pid=999, **{"class": APP_ID}, address="0xb", monitor=0),
                   dict(pid=123, **{"class": APP_ID}, address="0xc", monitor=0)]

        def run(arguments, **kwargs):
            calls.append(arguments)
            if arguments[1:] == ["-j", "clients"]:
                return subprocess.CompletedProcess(arguments, 0, json.dumps(clients))
            if arguments[1:] == ["-j", "monitors"]:
                return subprocess.CompletedProcess(arguments, 0, json.dumps([dict(id=0, width=1920, height=1080, x=0, y=0)]))
            return subprocess.CompletedProcess(arguments, 0, "ok\nok\nok\nok\n")

        place_window(900, 800, run=run, pid=123)
        batch = calls[-1][-1]
        self.assertEqual(batch.count("address:0xc"), 4)
        self.assertNotIn("address:0xa", batch)
        self.assertNotIn("address:0xb", batch)
        self.assertNotIn("togglefloating", batch)
        self.assertNotIn("pin", batch)
        self.assertIn("dispatch setfloating", batch)
        self.assertIn("dispatch alterzorder top", batch)

    def test_unavailable_compositor_is_nonfatal(self):
        with patch("sys.stderr") as stderr:
            place_window(900, 800, run=lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("hyprctl", 0.5)))
        self.assertTrue(stderr.write.called)


if __name__ == "__main__":
    unittest.main()
