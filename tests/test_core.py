import unittest
from simplepomodoro.core import Config, Timer, propose


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.timer = Timer(Config(1, 1, 2), clock=self.clock)

    def test_starts_idle_and_start_is_idempotent(self):
        self.assertFalse(self.timer.running)
        self.assertEqual(self.timer.seconds_left, 60)
        self.timer.start()
        self.clock.advance(10)
        self.timer.start()
        self.timer.tick()
        self.assertEqual(self.timer.seconds_left, 50)

    def test_pause_and_resume_preserve_remaining_time(self):
        self.timer.start()
        self.clock.advance(20)
        self.timer.pause()
        self.clock.advance(200)
        self.timer.tick()
        self.assertEqual(self.timer.seconds_left, 40)
        self.timer.start()
        self.clock.advance(5)
        self.timer.tick()
        self.assertEqual(self.timer.seconds_left, 35)

    def test_warning_fires_once_at_threshold_and_again_next_phase(self):
        self.timer.start()
        self.clock.advance(53)
        self.assertEqual(self.timer.tick(), ["warning"])
        self.assertEqual(self.timer.tick(), [])
        self.timer.pause()
        self.timer.start()
        self.assertEqual(self.timer.tick(), [])
        self.clock.advance(7)
        self.assertEqual(self.timer.tick(), ["phase"])
        self.clock.advance(53)
        self.assertEqual(self.timer.tick(), ["warning"])

    def test_warning_can_be_disabled_or_customized(self):
        self.timer.warning_seconds = 0
        self.timer.start()
        self.clock.advance(54)
        self.assertEqual(self.timer.tick(), [])
        self.timer.warning_seconds = 6
        self.assertEqual(self.timer.tick(), ["warning"])

    def test_final_rest_is_included(self):
        self.timer.start()
        self.clock.advance(180)
        self.timer.tick()
        self.assertFalse(self.timer.is_work)
        self.assertEqual(self.timer.repetition, 2)
        self.assertFalse(self.timer.finished)
        self.clock.advance(60)
        self.assertEqual(self.timer.tick(), ["complete"])
        self.assertTrue(self.timer.finished)
        self.assertFalse(self.timer.running)
        self.assertEqual(self.timer.seconds_left, 0)
        self.assertEqual(self.timer.tick(), [])

    def test_late_callback_does_not_extend_session(self):
        self.timer.start()
        self.clock.advance(125.5)
        self.assertEqual(self.timer.tick(), ["phase", "phase"])
        self.assertEqual(self.timer.repetition, 2)
        self.assertTrue(self.timer.is_work)
        self.assertEqual(self.timer.seconds_left, 55)

    def test_callback_after_entire_session_only_completes_once(self):
        self.timer.start()
        self.clock.advance(10000)
        self.assertEqual(self.timer.tick(), ["complete"])
        self.assertEqual(self.timer.tick(), [])

    def test_pause_exactly_at_boundary_processes_phase(self):
        self.timer.start()
        self.clock.advance(60)
        self.assertEqual(self.timer.pause(), ["phase"])
        self.assertFalse(self.timer.is_work)
        self.assertEqual(self.timer.remaining, 60)
        self.assertFalse(self.timer.running)

    def test_reset_restores_first_phase_and_warning(self):
        self.timer.start()
        self.clock.advance(113)
        self.timer.tick()
        self.timer.reset()
        self.assertTrue(self.timer.is_work)
        self.assertFalse(self.timer.running)
        self.assertFalse(self.timer.warned)
        self.assertEqual(self.timer.repetition, 1)
        self.assertEqual(self.timer.progress, 1)
        self.assertEqual(self.timer.seconds_left, 60)

    def test_display_rounds_up_fractional_seconds(self):
        self.timer.start()
        self.clock.advance(0.1)
        self.timer.tick()
        self.assertEqual(self.timer.seconds_left, 60)

    def test_reconfigure_resets_timer(self):
        self.timer.start()
        self.timer.configure(Config(25, 5, 4), 10)
        self.assertFalse(self.timer.running)
        self.assertEqual(self.timer.seconds_left, 1500)
        self.assertEqual(self.timer.warning_seconds, 10)


class PlannerTests(unittest.TestCase):
    def test_standard_budgets(self):
        self.assertEqual(propose(30), Config(25, 5, 1))
        self.assertEqual(propose(60), Config(50, 10, 1))
        self.assertEqual(propose(120), Config(50, 10, 2))
        self.assertEqual(propose(180), Config(50, 10, 3))

    def test_representative_budgets_never_overrun(self):
        for minutes in (2, 3, 5, 7, 10, 17, 25, 43, 59, 61, 75, 90, 121, 240, 480, 1440):
            with self.subTest(minutes=minutes):
                config = propose(minutes)
                self.assertLessEqual(config.total_minutes, minutes)
                self.assertGreaterEqual(config.work_minutes, 1)
                self.assertGreaterEqual(config.rest_minutes, 1)
                self.assertLessEqual(config.repetitions, 12)
                self.assertGreaterEqual(config.work_minutes, config.rest_minutes)

    def test_shortest_budget_includes_break(self):
        self.assertEqual(propose(2), Config(1, 1, 1))

    def test_invalid_budget(self):
        for minutes in (0, 1, -1, 1441):
            with self.assertRaises(ValueError):
                propose(minutes)

    def test_invalid_configuration(self):
        for args in ((0, 10, 2), (181, 10, 2), (50, 0, 2), (50, 61, 2), (50, 10, 0), (50, 10, 13)):
            with self.assertRaises(ValueError):
                Config(*args)


if __name__ == "__main__":
    unittest.main()
