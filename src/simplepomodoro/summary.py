"""Display values for the shared timer; no GTK dependency."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    phase: str
    clock: str
    detail: str
    action: str


def timer_summary(timer):
    seconds = timer.seconds_left
    started = timer.index > 0 or timer.remaining < timer.duration
    phase = "Complete" if timer.finished else "Focus" if timer.is_work else "Rest"
    detail = f"Round {timer.repetition}/{timer.config.repetitions}"
    if not timer.running and not timer.finished:
        detail += " · Paused" if started else " · Ready"
    action = "Pause" if timer.running else "Start again" if timer.finished else "Resume" if started else "Start"
    return Summary(phase, f"{seconds // 60:02d}:{seconds % 60:02d}", detail, action)
