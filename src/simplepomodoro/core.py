"""Timer and planner logic; independent of GTK and real-time waits."""
from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class Config:
    work_minutes: int = 50
    rest_minutes: int = 10
    repetitions: int = 2

    def __post_init__(self):
        if not 1 <= self.work_minutes <= 180:
            raise ValueError("Work must be between 1 and 180 minutes.")
        if not 1 <= self.rest_minutes <= 60:
            raise ValueError("Rest must be between 1 and 60 minutes.")
        if not 1 <= self.repetitions <= 12:
            raise ValueError("Choose between 1 and 12 repetitions.")

    @property
    def total_minutes(self):
        return (self.work_minutes + self.rest_minutes) * self.repetitions


def propose(available_minutes):
    """Fit complete work/rest pairs; prefer 50/10 and little unused time."""
    if not 2 <= available_minutes <= 1440:
        raise ValueError("Available time must be between 2 and 1440 minutes.")
    candidates = []
    for work in range(1, 61):
        for rest in range(1, 21):
            if rest > work or not 0.1 <= rest / work <= 0.35:
                continue
            for repetitions in range(1, 13):
                config = Config(work, rest, repetitions)
                unused = available_minutes - config.total_minutes
                if unused < 0:
                    continue
                score = (4 * unused / available_minutes
                         + abs(work - 50) / 50
                         + 2 * abs(rest / work - 0.2)
                         + (0.06 if work % 5 else 0))
                candidates.append((score, unused, -work, config))
    if not candidates:
        return Config(available_minutes - 1, 1, 1)
    return min(candidates, key=lambda item: item[:3])[3]


class Timer:
    def __init__(self, config=Config(), warning_seconds=7, clock=time.monotonic):
        self.clock = clock
        self.configure(config, warning_seconds)

    def configure(self, config, warning_seconds):
        self.config = config
        self.warning_seconds = max(0, min(60, warning_seconds))
        self.reset()

    def reset(self):
        self.index = 0
        self.running = False
        self.finished = False
        self.warned = False
        self.remaining = self.duration
        self.deadline = None

    @property
    def is_work(self):
        return self.index % 2 == 0

    @property
    def duration(self):
        return (self.config.work_minutes if self.is_work else self.config.rest_minutes) * 60

    @property
    def repetition(self):
        return min(self.index // 2 + 1, self.config.repetitions)

    @property
    def progress(self):
        return max(0.0, min(1.0, self.remaining / self.duration))

    @property
    def seconds_left(self):
        return max(0, math.ceil(self.remaining))

    def start(self):
        if self.finished or self.running:
            return
        self.deadline = self.clock() + self.remaining
        self.running = True

    def pause(self):
        events = self.tick()
        self.running = False
        return events

    def tick(self):
        if not self.running:
            return []
        now = self.clock()
        events = []
        # Advance from the original deadline so delayed callbacks never add time.
        while now >= self.deadline:
            self.index += 1
            self.warned = False
            if self.index >= self.config.repetitions * 2:
                self.index -= 1
                self.remaining = 0
                self.running = False
                self.finished = True
                return ["complete"]
            self.deadline += self.duration
            events.append("phase")
        self.remaining = self.deadline - now
        if self.warning_seconds and self.remaining <= self.warning_seconds and not self.warned:
            self.warned = True
            events.append("warning")
        return events
