# Repository Guidelines

## Project Structure & Module Organization

SimplePomodoro is a Python application using system GTK4, libadwaita, and GStreamer bindings. `src/simplepomodoro/__main__.py` is the entry point; `run.sh` launches it using the system Python. Timer logic lives in `core.py`, separate from GTK rendering in `app.py`.

Use `src/` for application code, `tests/` for automated tests, and `assets/` for static resources if the chosen framework supports these conventions. Keep timer logic separate from interface rendering so timing behavior can be tested independently. Document the selected stack and entry points in `README.md`.

## Build, Test, and Development Commands

Run locally with `./run.sh`. Run unit tests with `PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v`. Run graphical checks with `PYTHONPATH=src /usr/bin/python tests/gtk_smoke.py`; exit 77 means no display. Build the Arch package with `python3 packaging/build.py`, or only the source archive with `python3 packaging/build.py --source-only`. Build outputs belong in ignored `dist/`. GitHub Actions runs unit tests, shell syntax checks, and source archive verification.

When adding tooling, provide reproducible commands for local development, production builds, and automated checks. Record exact commands and prerequisites in `README.md`, and commit the appropriate dependency lockfile.

## Coding Style & Naming Conventions

Follow the selected language and framework conventions. Configure a formatter and linter when introducing source code; keep formatting changes separate from behavioral changes.

Use descriptive names that distinguish durations, elapsed time, and remaining time. Include units in timing variables, such as `remainingSeconds` or `durationMs`. Keep modules focused and avoid unexplained timing constants.

## Testing Guidelines

Tests use the Python standard library's unittest framework and the `test_*.py` naming pattern. There is no coverage threshold. No pip dependencies or dependency lockfile are needed for the system-library application. No formatter or linter is currently configured.

Cover start, pause, resume, reset, session transitions, and timer completion. Prefer controlled clocks over real-time waits. Document how to run the suite before requesting review.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects, such as `Add pause and resume controls`. Release instructions are in `docs/releasing.md`; use annotated version tags such as `0.1.0`. Keep generated packages and local credentials out of Git.

Pull requests should explain the behavior changed, list validation performed, and link relevant issues. Include screenshots for interface changes and identify any setup steps or checks that remain unavailable.
