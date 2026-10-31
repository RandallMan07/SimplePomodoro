# SimplePomodoro

A small native Linux focus timer built with Python, GTK4, and libadwaita. Dark charcoal, a mint countdown ring, and a lavender rest phase. No browser runtime.

<img src="assets/io.github.simplepomodoro.App.png" alt="SimplePomodoro icon" width="128">

## Features

- Configurable focus/rest durations and rounds, with pause, resume, and reset.
- A schedule planner that suggests sessions for the time you have available.
- Advance warnings, distinct chimes, volume control, and desktop notifications.
- Saved preferences and timer sessions, an application launcher, and optional Hyprland placement.
- Local operation with no account or network connection.

Arch Linux is the documented installation target. Other Linux distributions need
equivalent GTK, Python bindings, and GStreamer packages; they have not been verified.

## Download and install

Once published, the GitHub **Releases** page provides these downloads:

| File | Purpose |
| --- | --- |
| `simplepomodoro-0.1.0-1-any.pkg.tar.zst` | Installable Arch Linux package; system dependencies are installed by pacman. |
| `simplepomodoro-0.1.0.tar.gz` | Source, required assets, tests, documentation, and local package recipe. |
| `SHA256SUMS` | SHA-256 checksums of the release downloads. |

Download the package and `SHA256SUMS` to the same directory. Verify the package's
checksum (the filter allows you to download just the package), then install:

```sh
grep '  simplepomodoro-0.1.0-1-any.pkg.tar.zst$' SHA256SUMS | sha256sum --check --strict -
sudo pacman -U ./simplepomodoro-0.1.0-1-any.pkg.tar.zst
```

Checksums detect corruption; they are not a cryptographic signature from the author.
Open **SimplePomodoro** from your application launcher or run `simplepomodoro`.
Uninstall with `sudo pacman -R simplepomodoro`; preferences remain in your home directory.

## Run on Arch Linux

To run from a source checkout or extracted source archive, install the dependencies:

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 libadwaita gstreamer gst-plugins-base gst-plugins-good
./run.sh
```

Run from a terminal inside your graphical desktop session. The launcher uses Arch's `/usr/bin/python`, so an unrelated Python environment will not hide the system GTK bindings. No pip dependencies or build step are required. GTK 4.12+ and libadwaita 1.5+ are required.

## Use

- Choose focus minutes, rest minutes, and the number of rounds. Defaults: **50 / 10 × 2**. Every round includes its break, including the final round.
- Set **Available minutes** and select **Find my rhythm** to apply a suggested configuration that fits. For example, 30 minutes gives 25/5; 120 minutes gives 50/10 × 2. This is a preference-based suggestion, not a scientifically optimal schedule.
- **Start focus**, **Pause / Resume**, or **Reset**. Reset stops the session and returns to round one. Reset before editing a session already in progress.
- **Heads-up** plays one advance chime per phase, seven seconds before the transition by default. Choose 0–60 seconds; 0 disables the advance alert. Phase changes use a distinct chime, and completion uses a third.
- Adjust volume, mute tones, or use **Preview**. A visible warning still appears with tones muted. Desktop notifications accompany transitions if your notification service supports them.
- Keep the window open or minimize it to receive sounds and notifications. Closing automatically saves the countdown without a confirmation prompt. Running sessions account for elapsed time when reopened; paused sessions remain paused. Use **Reset** before closing to discard the current countdown. If saving fails, the window stays open and displays the error so you can retry.

Session state lives in `$XDG_STATE_HOME/simplepomodoro/session.json` (normally `~/.local/state/simplepomodoro/`). A running session accounts for elapsed wall time while the app is closed, advances to the correct round/phase, and shows completion if the whole session elapsed. Historical sounds and notifications are not replayed; no alerts play while the application is closed. State saves at controls and transitions, on normal close, and every five seconds while running. Invalid state falls back to an idle timer with a visible message. A backward system-clock change counts as zero closed time; a forward change may advance or complete the session.

Preferences live in `$XDG_CONFIG_HOME/simplepomodoro/settings.json` (normally `~/.config/simplepomodoro/`). Generated chimes live in `$XDG_CACHE_HOME/simplepomodoro/`. No network connection is used. On Hyprland/Omarchy, the window opens floating, centered, and raised once, sized to its contents with timer and settings side by side. You can then move, resize, or tile it with Win+T. Small screens retain scrolling. This uses `hyprctl` without changing your desktop configuration.

GTK requests idle/suspend inhibition during active sessions; compositor support varies. While the app is open, sleep pauses its monotonic clock rather than counting suspended time. While closed, elapsed wall time (including sleep) counts toward restoration.

## Development and checks

```sh
PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
PYTHONPATH=src /usr/bin/python tests/gtk_smoke.py
```

The logic tests use a controlled clock, with no real-time sleeps or GTK requirement. The GTK smoke check needs a graphical session and isolates preferences, session state, and audio cache in a temporary directory; exit 77 means the display is unavailable. It tests widget construction, planning, controls, the advance warning, preferences, automatic running/paused session restoration, close failures, and resetting a session before closing. Manually verify actual sound output, resizing, background operation, and notifications on your desktop.

Application code is in `src/simplepomodoro/`; timer/planner logic is separated from GTK, and styling lives in `assets/style.css`. Use four-space Python indentation and descriptive snake_case names with explicit time units. Dependencies come from Arch's package manager; no Python dependency lockfile is needed for this system-library application.

Project decisions and implementation notes are recorded in [docs/decisions.md](docs/decisions.md).

## Build and install an Arch package

```sh
# Install build tooling if needed:
sudo pacman -S --needed base-devel desktop-file-utils
python packaging/build.py
sudo pacman -U dist/simplepomodoro-0.1.0-1-any.pkg.tar.zst
```

The build runs the unit tests and validates the desktop entry. After installation, open **SimplePomodoro** in Omarchy's app launcher, or run `simplepomodoro`. Close an existing source-launched instance before opening the installed version. Rebuild and run the same pacman command to update. Uninstall with `sudo pacman -R simplepomodoro`; your preferences remain in your home directory.

The generated icon and exact imagegen prompt are documented in [docs/icon-generation.md](docs/icon-generation.md).

To build only the source archive and its checksum, without Arch build tooling:

```sh
python3 packaging/build.py --source-only
```

Build output stays in `dist/`, which is excluded from Git. Required images and
stylesheets in `assets/` are tracked because the application uses them at runtime.

## Publishing and contributing

Follow [the first-release guide](docs/releasing.md) to initialize Git, publish to
GitHub, tag `0.1.0`, and attach downloads to a Release. See
[CHANGELOG.md](CHANGELOG.md) for release notes and
[docs/verification.md](docs/verification.md) for graphical checks and limitations.
GitHub Actions runs the unit tests and source archive checks on pushes and pull requests.

Keep timer logic separate from GTK rendering. Include a description of behavior
changes and the checks performed with contributions.

## License

[MIT](LICENSE). Copyright (c) 2026 SimplePomodoro contributors.
The project license covers this repository's code, documentation, and bundled assets
to the extent its contributors hold rights in them. System dependencies retain their
own licenses. The generated icon's provenance is documented above.
See [the license comparison](docs/licensing.md) for the scope of common alternatives.
