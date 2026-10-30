"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from pathlib import Path
import os
from unittest.mock import Mock
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
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
        os.environ["XDG_DATA_HOME"] = directory
        app = Adw.Application(application_id="io.github.simplepomodoro.Smoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        window = Window(app)
        window.present()
        window.audio.play_choice = Mock()
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
        window.show_sound_settings()
        dialog = window.sound_dialog
        assert len(dialog.choices) == 6
        dialog.dropdowns["phase"].set_selected(3)
        assert window.sound_selections["phase"] == "builtin:bell"
        dialog.countdown.set_active(True)
        dialog.start_test()
        assert dialog.test_source
        window.sound.set_active(True)
        window.sound.set_active(False)
        assert not dialog.test_source
        dialog.preview(None, "phase")
        assert window.audio.play_choice.call_args.args[0].id == "builtin:bell"
        dialog.start_test()
        dialog.force_close()
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        assert not dialog.test_source
        assert window.sound_dialog is None
        window.save_settings()
        assert Path(directory, "simplepomodoro/settings.json").exists()
        window.close()
        assert window not in app.get_windows()
        assert not window.audio.stop_source
        restored = Window(app)
        restored.present()
        assert restored.warning.get_value_as_int() == 12
        assert restored.sound_selections["phase"] == "builtin:bell"
        assert restored.countdown_enabled
        restored.close()
        assert restored not in app.get_windows()
        print("PASS: GTK construction, planner, controls, warnings, sound form/preview cancellation, persistence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
