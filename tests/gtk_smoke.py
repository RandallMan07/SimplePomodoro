"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from pathlib import Path
import os
from unittest.mock import patch
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk
from simplepomodoro.app import Window
from simplepomodoro.core import Config


def main():
    Gtk.init_check()
    if Gdk.Display.get_default() is None:
        print("SKIP: no accessible graphical display")
        return 77
    with tempfile.TemporaryDirectory(prefix="simplepomodoro-smoke-") as directory:
        os.environ["XDG_CONFIG_HOME"] = directory
        os.environ["XDG_CACHE_HOME"] = directory
        os.environ["XDG_STATE_HOME"] = directory
        app = Adw.Application(application_id="io.github.simplepomodoro.Smoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        window = Window(app)
        window.present()
        assert window.timer.config == Config()
        window.budget.set_value(60)
        window.plan()
        assert window.timer.config == Config(50, 10, 1)
        window.sound.set_active(False)
        window.timer.clock = lambda: 0
        window.toggle_timer()
        assert window.timer.running
        assert not window.session_card.get_sensitive()
        window.timer.clock = lambda: 2993
        window.tick()
        assert "7 seconds" in window.status.get_text()
        window.toggle_timer()
        assert not window.timer.running
        window.reset_timer()
        assert window.session_card.get_sensitive()
        window.warning.set_value(12)
        window.save_settings()
        assert Path(directory, "simplepomodoro/settings.json").exists()
        window.close()
        restored = Window(app)
        restored.present()
        assert restored.warning.get_value_as_int() == 12
        restored.work.set_value(2)
        restored.rest.set_value(1)
        restored.repetitions.set_value(3)
        restored.timer.clock = lambda: 0
        restored.toggle_timer()
        restored.timer.clock = lambda: 20
        restored.tick()
        # Save-and-close persists a running timer before cleanup stops it.
        restored.close_response(None, "save")
        with patch("simplepomodoro.app.Chimes.play") as play:
            running = Window(app)
            running.present()
            assert running.timer.running
            assert running.timer.config == Config(2, 1, 3)
            assert running.work.get_value_as_int() == 2
            assert running.repetitions.get_value_as_int() == 3
            assert 99 <= running.timer.remaining <= 100
            assert not running.session_card.get_sensitive()
            play.assert_not_called()
        with patch.object(running.session_store, "save", return_value=False):
            running.session_store.error = "Session could not be saved: test failure"
            running.close_response(None, "save")
            assert not running.close_approved
            assert running.timer.running
            assert "could not be saved" in running.persistence_status.get_text()
        with patch.object(running.session_store, "save", wraps=running.session_store.save) as save:
            checkpoint_seconds = running.last_checkpoint_seconds
            with patch("simplepomodoro.app.time.monotonic", return_value=checkpoint_seconds + 1):
                running.tick()
                save.assert_not_called()
            with patch("simplepomodoro.app.time.monotonic", return_value=checkpoint_seconds + 6):
                running.tick()
                save.assert_called_once()
        running.toggle_timer()
        paused_seconds = running.timer.remaining
        with patch.object(running.session_store, "save", return_value=False):
            running.session_store.error = "Session could not be saved: paused test failure"
            running.close()
            assert running.get_visible()
            assert running in app.get_windows()
            assert not running.timer.running
            assert running.timer.remaining == paused_seconds
            assert "paused test failure" in running.persistence_status.get_text()
        # Retrying the close must save the paused state before any teardown.
        running.close()
        paused = Window(app)
        paused.present()
        assert not paused.timer.running
        assert paused.timer.remaining == paused_seconds
        assert paused.start_button.get_label() == "Resume"
        paused.toggle_timer()
        paused.close_response(None, "end")
        ended = Window(app)
        ended.present()
        assert not ended.timer.running
        assert ended.timer.index == 0
        assert ended.timer.remaining == 120
        assert ended.session_card.get_sensitive()
        with patch.object(ended.session_store, "save", return_value=False):
            ended.session_store.error = "Session could not be saved: idle test failure"
            ended.close()
            assert ended.get_visible()
            assert ended in app.get_windows()
            assert "idle test failure" in ended.persistence_status.get_text()
        ended.close()
        print("PASS: GTK construction, planner, start/pause/reset, warning, settings, running/paused session restoration, end session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
