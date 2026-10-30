# Project decisions

Record subsequent product, architecture, and behavior decisions in this directory.

## 2026-10-30 — Native first release

- **User requirements:** configurable focus/rest durations and repetitions; suggest a schedule from a time budget; radial time remaining; a phase-change tone and customizable advance warning, defaulting to seven seconds; dark theme. Design is delegated to the implementer.
- **Stack:** Python with GTK4, libadwaita, Cairo, and GStreamer. The user prefers native desktop applications over Electron and other browser-based approaches. These libraries are already available in the Arch environment. No server, webview, npm, or Rust toolchain is needed.
- **Design:** a single scrollable window, charcoal surfaces, mint focus ring, lavender rest ring, and amber warning text. Native controls provide keyboard interaction; a large numeric clock accompanies the radial visualization.
- **Session:** default 50 minutes focus, 10 minutes rest, two repetitions. One repetition is a full focus/rest pair, including the final break. Both phases advance automatically. Start, pause/resume, reset, and start again are supported. Reset is required to edit a running or paused session.
- **Limits:** focus 1–180 minutes, rest 1–60 minutes, 1–12 repetitions, available time 2–1440 minutes. The planner searches focus durations up to 60 minutes and breaks up to 20 minutes with 1–12 rounds. Very large budgets can leave unused time, explicitly shown in the result.
- **Planning:** deterministic heuristic prioritizing budget utilization, closeness to 50-minute focus periods, and a 20% break/work ratio, with a small preference for five-minute focus increments. Complete pairs never exceed the budget. Very short budgets use shorter phases. No claim of scientific optimality. The proposal is applied immediately while idle.
- **Timekeeping:** monotonic deadlines; delayed UI callbacks catch up without stretching phases. Pause retains fractional remaining time. Suspended time does not count. Request idle/suspend inhibition while running where the compositor permits it.
- **Alerts:** one advance chime per phase, default seven seconds before transition; configurable 0–60 seconds (0 disables). Distinct generated chimes for advance, transition, and completion. Global tone toggle and volume apply to automatic sounds; Preview explicitly auditions the transition sound. Visual reminders remain active when muted. A desktop notification is sent at transitions/completion; delivery depends on the desktop notification daemon. Delayed transitions coalesce into one current alert instead of replaying old chimes.
- **Persistence/lifecycle:** save settings atomically in the XDG config directory and generated WAV files in the XDG cache directory. Invalid settings fall back to defaults. Sessions run while the window is open/minimized and are not restored after exit. Closing an active session requires an explicit End session response.
- **Distribution:** run directly using `./run.sh` and Arch system libraries. Installation bundles, tray integration, global shortcuts, statistics, and long-break rules are deferred until requested.

## Reference documentation

- [PyGObject setup](https://pygobject.gnome.org/getting_started.html)
- [GTK DrawingArea / Cairo](https://docs.gtk.org/gtk4/class.DrawingArea.html)
- [libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/)
- [Gio desktop notifications](https://docs.gtk.org/gio/method.Application.send_notification.html)

## 2026-10-30 — Floating opening behavior and content-sized layout

- **User request:** open outside Hyprland's tiled layout, on top, with all controls fitting the window; allow normal window management afterward. Omarchy's Win+T binding toggles floating/tiling.
- **Opening behavior:** on the first map only, query Hyprland for the main window matching both this process ID and the application's exact class. Set that window floating, resize to the measured GTK content size, center on its current monitor, and raise it. No repeated enforcement or permanent compositor configuration is needed. Existing windows are not repositioned on subsequent application activations.
- **Layout:** show the timer on the left and the configuration/reminder cards on the right. GTK measures the content at an opening width of at least 900 logical pixels. The scroller propagates its natural height rather than hiding the height of its children. The old fixed 580 × 880 default is removed.
- **Screen limits:** constrain the requested size to the usable monitor area, accounting for scaling, rotation, reserved panels, negative monitor coordinates, and a 16-pixel margin on each side. Vertical scrolling remains available on screens too short to show every control. Resizing and Win+T remain under user control after opening.
- **Integration:** use bounded asynchronous `hyprctl` calls so IPC cannot freeze GTK. On another compositor or if Hyprland IPC is unavailable, retain normal GTK placement and report an IPC failure in the terminal. No files under the user's Hyprland/Omarchy configuration are changed.
- **References:** [GTK natural scroller height](https://docs.gtk.org/gtk4/property.ScrolledWindow.propagate-natural-height.html), [GTK content measurement](https://docs.gtk.org/gtk4/method.Widget.measure.html), and [Hyprland 0.56.2 dispatcher implementation](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/config/legacy/DispatcherTranslator.cpp).

## 2026-10-30 — Header polish, icon, and local Arch package

- **Header:** remove the visible SimplePomodoro title from the native header bar, retaining window controls, drag area, application identity, and desktop launcher name.
- **Spacing:** add 10 logical pixels above the two-column content, increasing the gap below the introduction without changing the spacing inside the cards.
- **Icon:** use the built-in imagegen skill to generate a mint timer/tomato mark with a lavender rest segment on a charcoal tile. Save the transparent PNG in `assets/io.github.simplepomodoro.App.png`, use it for GTK and the desktop launcher, and record the complete generation prompt in `docs/icon-generation.md`.
- **Packaging:** prepare version 0.1.0-1 as an architecture-independent local Arch package. Package the source and assets together in `/usr/share/simplepomodoro`, expose `/usr/bin/simplepomodoro`, and install a desktop entry and hicolor icon for Omarchy's app launcher. Build with `python packaging/build.py`; the builder hashes a local source snapshot and runs unit tests and desktop-entry validation through makepkg. Keep generated packages under ignored `dist/`.
- **Dependencies:** use Arch's system Python/GTK/GStreamer packages; require `desktop-file-utils` for building. No pip install, vendored runtime, compositor configuration changes, or public license choice is needed for this private local package.
- **Installation:** install/update the resulting package with pacman; preferences remain in the existing XDG location and survive package upgrades/removal. System installation needs privileges and access outside this workspace. No package is published remotely.
