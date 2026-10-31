import json
import subprocess
import unittest
from unittest.mock import patch
from simplepomodoro.desktop import APP_ID, WindowState, capture_window, opening_geometry, place_window, restore_window


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


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.client = dict(pid=123, **{"class": APP_ID}, address="0xc", floating=True,
                           size=[910, 720], at=[-200, 35], workspace={"id": 4})

    def run_hyprctl(self, arguments, **kwargs):
        self.calls.append(arguments)
        self.assertEqual(kwargs["timeout"], 0.5)
        if arguments[1:] == ["-j", "clients"]:
            other = dict(self.client, pid=999, address="0xb")
            return subprocess.CompletedProcess(arguments, 0, json.dumps([other, self.client]))
        return subprocess.CompletedProcess(arguments, 0, "ok\n")

    def test_float_snapshot_restores_geometry_and_workspace(self):
        state = capture_window(run=self.run_hyprctl, pid=123)
        self.assertEqual(state, WindowState(True, 910, 720, -200, 35, 4))
        restore_window(state, 900, 800, run=self.run_hyprctl, pid=123)
        batch = self.calls[-1][-1]
        self.assertIn("movetoworkspacesilent 4,address:0xc", batch)
        self.assertIn("setfloating address:0xc", batch)
        self.assertIn("resizewindowpixel exact 910 720,address:0xc", batch)
        self.assertIn("movewindowpixel exact -200 35,address:0xc", batch)
        self.assertNotIn("address:0xb", batch)

    def test_tiled_restore_leaves_geometry_to_layout(self):
        self.client["floating"] = False
        state = capture_window(run=self.run_hyprctl, pid=123)
        restore_window(state, 900, 800, run=self.run_hyprctl, pid=123)
        batch = self.calls[-1][-1]
        self.assertIn("settiled address:0xc", batch)
        self.assertNotIn("resizewindowpixel", batch)
        self.assertNotIn("movewindowpixel", batch)

    def test_invalid_snapshot_is_ignored(self):
        self.client["size"] = ["910;bad", 720]
        self.assertIsNone(capture_window(run=self.run_hyprctl, pid=123))
        self.client["address"] = "0xc;bad"
        self.assertIsNone(capture_window(run=self.run_hyprctl, pid=123))

    def test_missing_snapshot_uses_content_size_fallback(self):
        with patch("simplepomodoro.desktop.place_window") as fallback:
            restore_window(None, 900, 800, run=self.run_hyprctl, pid=123)
        fallback.assert_called_once_with(900, 800, run=self.run_hyprctl, pid=123)


if __name__ == "__main__":
    unittest.main()
