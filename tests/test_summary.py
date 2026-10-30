import unittest
from simplepomodoro.core import Config, Timer
from simplepomodoro.summary import timer_summary


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.timer = Timer(Config(1, 1, 2), clock=lambda: self.now)

    def test_idle_start_and_pause(self):
        summary = timer_summary(self.timer)
        self.assertEqual((summary.phase, summary.clock, summary.detail, summary.action), ("Focus", "01:00", "Round 1/2 · Ready", "Start"))
        self.timer.start()
        self.now = 15.2
        self.timer.tick()
        summary = timer_summary(self.timer)
        self.assertEqual((summary.clock, summary.action), ("00:45", "Pause"))
        self.timer.pause()
        summary = timer_summary(self.timer)
        self.assertEqual(summary.detail, "Round 1/2 · Paused")
        self.assertEqual(summary.action, "Resume")

    def test_rest_round_and_completion(self):
        self.timer.start()
        self.now = 60
        self.timer.tick()
        self.assertEqual(timer_summary(self.timer).phase, "Rest")
        self.now = 125
        self.timer.tick()
        self.assertEqual(timer_summary(self.timer).detail, "Round 2/2")
        self.now = 240
        self.timer.tick()
        summary = timer_summary(self.timer)
        self.assertEqual((summary.phase, summary.clock, summary.action), ("Complete", "00:00", "Start again"))
        self.timer.reset()
        self.assertEqual(timer_summary(self.timer).detail, "Round 1/2 · Ready")


if __name__ == "__main__":
    unittest.main()
