# Changelog

## 0.1.0

Initial release of SimplePomodoro for Linux.

- Native GTK4 and libadwaita interface with focus and rest countdown rings.
- Configurable focus/rest durations and rounds, with a schedule planner.
- Start, pause, resume, reset, and advance warnings.
- Generated chimes, volume control, and desktop notifications.
- Saved preferences and optional Hyprland opening placement.
- Arch Linux package, desktop launcher, and application icon.

Known limitations: closing the app ends the session; running sessions are not
restored. Suspend time does not count toward the timer. Notification delivery and
idle inhibition depend on the desktop environment. Live graphical acceptance
checks are documented in `docs/verification.md`.
