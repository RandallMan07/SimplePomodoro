# Changelog

## 0.1.1

- Customize reminder sounds, preview countdowns, and download short licensed effects from Freesound.
- Follow Omarchy's current color palette, including live theme changes.
- Save and resume running or paused sessions automatically.
- Add a Hyprland top-center summary widget with hover and pinned reminder modes.
- Save Freesound credentials in the desktop keyring when available.

Known limitations: Freesound requires a user API key for in-app search; browser
search is available without one. Widget support requires a compatible Wayland
compositor and gtk4-layer-shell. See the feature notes in `docs/` and verify
sound output and widget interaction in the target desktop session.

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
