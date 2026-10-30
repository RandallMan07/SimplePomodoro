# Verification — first release

## Automated checks

- **Passed:** 16 standard-library unit tests covering configuration bounds, schedule fitting, short budgets, standard 25/5 and 50/10 suggestions, pause/resume, one-shot warnings, disabled/custom warnings, final rest, reset, display rounding, boundary timing, delayed callbacks, and completion.
- **Passed:** Python compilation and shell launcher syntax checks.
- **Passed:** all three generated WAV chimes validated and decoded to end-of-stream through GStreamer using a silent test sink. This verifies file generation and decoding, not audible playback.
- **Unavailable:** GTK widget smoke check, because this execution sandbox cannot access the host Wayland/X11 display. It exits 77 with an explicit skip message. The launcher reports the missing display clearly and exits 1. A GTK Broadway test backend also could not listen on a socket in this sandbox.

## Graphical acceptance check

Run `./run.sh` from your regular desktop terminal, then:

1. Confirm the dark window, full mint radial ring, 50:00 clock, and 50/10 × 2 defaults on a fresh config. Resize and scroll to the reminder controls.
2. Enter a 120-minute budget and select Find my rhythm. Confirm 50/10 × 2 with zero spare minutes. Try 30 minutes (25/5 × 1) and 90 minutes (a proposal fitting the entire budget).
3. Set 1-minute focus/rest and one round. Start, pause, wait, resume, and reset. Paused time must not decrease, and session controls must remain locked until reset.
4. With a seven-second heads-up, confirm one advance chime and amber countdown at 00:07, then a distinct transition chime, a lavender rest ring, and an attempted desktop notification.
5. Let the final break finish. Confirm 00:00, completion state, completion chime, and Start again.
6. Preview the sound, change volume, mute tones, and set the heads-up to zero. Visual phase changes must continue when muted. Use a notification daemon such as mako if desktop notifications are desired on Hyprland.
7. Close during an active timer and check both Keep focusing and End session. Reopen and confirm preferences persist. The timer starts fresh after exit.

No actual on-screen rendering, speaker output, or desktop notification delivery has been verified from this sandbox.

## Floating-window update

- **Passed:** all 21 unit tests, including five placement tests covering process/class targeting, fractional scaling, portrait rotation, negative monitor positions, reserved bars, small-screen constraints, and unavailable compositor IPC.
- **Passed:** Python compilation after the layout and placement changes.
- **Not verified live:** the sandbox cannot connect to the running Hyprland socket or graphical display. Placement tests use simulated IPC responses; actual rendering and compositor behavior require the graphical session.
- **Desktop check:** close and reopen using `./run.sh`. Confirm it opens centered and floating above tiled windows, with timer and settings side by side. All controls should fit on a sufficiently large monitor. Press Win+T to tile it, resize it manually, and switch focus; the app must not undo those actions. Close and reopen to restore the opening behavior. Check the scaled primary monitor and portrait secondary monitor separately.

## Icon and installation package

- **Passed:** final Arch package build (`simplepomodoro-0.1.0-1-any.pkg.tar.zst`), including all 21 tests, source SHA-256 verification, and desktop-entry validation. Archive contents have root ownership and executable launchers.
- **Passed:** extracted-package imports resolve the installed source layout and find the bundled stylesheet and generated icon.
- **Inspected:** generated icon is a square RGBA PNG with transparent pixels outside the charcoal tile. Tool and complete prompt are saved in `docs/icon-generation.md`.
- **Installation blocked:** `sudo -n pacman -U --noconfirm …` cannot elevate in this sandbox: sudo reports the no-new-privileges flag and inaccessible system ownership. The package is built but has not been installed. Run `sudo pacman -U dist/simplepomodoro-0.1.0-1-any.pkg.tar.zst` in the repository from the regular desktop terminal.
- **Graphical limitation remains:** actual title removal, spacing, launcher appearance, and installed GUI startup need checking in the desktop session.
