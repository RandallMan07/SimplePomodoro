# SimplePomodoro

A small native Linux focus timer built with Python, GTK4, and libadwaita. Dark charcoal, a mint countdown ring, and a lavender rest phase. No browser runtime.

<img src="assets/io.github.simplepomodoro.App.png" alt="SimplePomodoro icon" width="128">

## Features

- Configurable focus/rest durations and rounds, with pause, resume, and reset.
- A schedule planner that suggests sessions for the time you have available.
- Advance warnings, distinct chimes, volume control, and desktop notifications.
- Saved preferences, an application launcher, and optional Hyprland placement.
- Local timer operation with no account; optional gallery downloads use an internet connection.
- Follows the current Omarchy desktop palette, including live theme switches.
- Persistent sessions, plus a compact top-center summary widget for Hyprland.

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
- Open **Sound library & countdown…** to select independent heads-up, phase-change, completion, and countdown sounds. Six generated sounds work offline. Choose a local folder, then **Use folder / Refresh** to scan WAV, OGG, MP3, FLAC, Opus, and M4A files; decoding depends on your installed GStreamer plugins. The default library is `$XDG_DATA_HOME/simplepomodoro/sounds` (normally `~/.local/share/simplepomodoro/sounds`). Files stay in that folder; the app does not copy or delete your sounds.
- Each sound has a **Preview**. **Test 3 · 2 · 1 + change** auditions synchronized pips followed by the selected phase-change sound. **Stop preview** or closing the form stops playback. Previews explicitly play even with automatic tones muted. Enable **Beep with 3, 2, 1 seconds remaining** for optional countdown cues; countdown files are limited to 300 ms so a long recording cannot mask the phase change. Missing selections fall back to generated sounds, and playback failures appear on screen.
- In the sound form, **Download sounds…** opens the compact Freesound browser. **Reminder** searches 0.05–3 second CC0/CC BY effects; **Countdown pip** requires 0.05–0.30 seconds and onset within 30 ms. Select a result and use its adjacent **Preview** to listen immediately. Preview files and attribution stay in a private temporary directory under `/tmp`; changing the result, cancelling, or closing removes them after any download worker stops. Previewing never adds a sound to your library. The bottom **Save sound** button explicitly saves the selected OGG/MP3 preview-format file and attribution into your library, independently of whether you previewed it. Original-quality OAuth downloads are outside this feature. Sidecars keep the Freesound ID, creator, source, license, preview URL, actual byte count, and time; requests remain cancellable and capped at 15 MiB.
- **Search in browser** opens the current query and matching short-sound/license filters on Freesound without an API key. The website may require an account for downloading; save any manually downloaded effect into your library and select **Use folder / Refresh**.
- For in-app search, create a [Freesound account/application API key](https://freesound.org/apiv2/apply/). The **API key** field and saved state are always visible. Enter the key and choose **Save key**; your typed value stays masked, with **Saved in desktop keyring** shown after success. Reopening shows saved state without loading the secret into the entry; type to replace it or use the remove icon. Storage uses optional system `libsecret` and a Secret Service provider such as GNOME Keyring. Keyring encryption depends on your desktop configuration; the application does not implement its own encryption. If the keyring is unavailable/locked, unlock it and retry or choose **Use for session** explicitly; no new plaintext file is written. A pre-existing `$XDG_CONFIG_HOME/simplepomodoro/freesound.json` remains compatible and is labeled **Move to keyring**; explicit migration deletes it only after a successful keyring store. `FREESOUND_API_KEY` still overrides local/session keys and is visibly labeled; removing local keys cannot unset that environment variable. Keys never enter timer preferences or attribution. Do not paste keys into chat or commit them.
- Short-effect filters reduce unsuitable recordings, but they do not trim existing files or make playback sample-accurate. A downloaded sound with a quiet opening can still produce an inaudible countdown because countdown playback stops after 300 ms. Use the built-in short pip or audition a suitably short effect with **Test 3 · 2 · 1 + change**. Ordinary timer operation never searches or downloads automatically.
- **Compact widget** in the header turns the window into a top-center arrow. Hover to reveal the current phase and remaining time. Click the arrow to pin the summary just below the panel; use its minimize control to return to the hover arrow, or **Open** to restore the full window. Hyprland uses layer-shell; other compositors may show the ordinary window instead.
- Keep the window open or minimize it to receive sounds and notifications. Closing automatically saves the countdown without a confirmation prompt. Running sessions account for elapsed time when reopened; paused sessions remain paused. Use **Reset** before closing to discard the current countdown. If saving fails, the window stays open and displays the error so you can retry.

Session state lives in `$XDG_STATE_HOME/simplepomodoro/session.json` (normally `~/.local/state/simplepomodoro/`). A running session accounts for elapsed wall time while the app is closed, advances to the correct round/phase, and shows completion if the whole session elapsed. Historical sounds and notifications are not replayed; no alerts play while the application is closed. State saves at controls and transitions, on normal close, and every five seconds while running. Invalid state falls back to an idle timer with a visible message. A backward system-clock change counts as zero closed time; a forward change may advance or complete the session.
Use the header arrow button to switch to the **summary widget**. The arrow stays at the top center of the current monitor, above windows and fullscreen applications. Hover or focus it to expand the bar with phase, remaining time, round, pause/resume, and **Open full timer**. Moving away fades out the bar. Click the arrow to keep the summary visible near the top while the arrow disappears. The summary's minimize button returns to the hover arrow. The arrow sits flush below the desktop panel and stays in place while the separate summary fades in or out. Escape or launching SimplePomodoro again restores the full window. The timer and alerts keep running while the full window is hidden. On Hyprland, reopening restores its previous floating size and position or its tiled state, and its workspace when available.

The widget requires the optional Arch package `gtk4-layer-shell` (`sudo pacman -S --needed gtk4-layer-shell`) and a Wayland compositor with layer-shell support, including Hyprland. It avoids taking screen space from other windows and respects existing panels. The widget button is disabled on unsupported desktops. No compositor configuration changes are needed.

Colors follow `$XDG_CONFIG_HOME/omarchy/current/theme/colors.toml` (normally `~/.config/omarchy/current/theme/colors.toml`) when available. Semantic color names and ANSI `color0`–`color7` slots are supported; light palettes also switch the native controls to light mode. Theme changes apply within about two seconds. Missing or malformed palettes use the original charcoal/mint/lavender colors. No desktop configuration is changed.

Preferences live in `$XDG_CONFIG_HOME/simplepomodoro/settings.json` (normally `~/.config/simplepomodoro/`). Generated chimes live in `$XDG_CACHE_HOME/simplepomodoro/`. The timer works offline; only explicit gallery searches/downloads use the network. On Hyprland/Omarchy, the main window opens floating, centered, and raised once, sized to its contents with timer and settings side by side. You can then move, resize, or tile it with Win+T. Small screens retain scrolling. This uses `hyprctl` without changing your desktop configuration.

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
