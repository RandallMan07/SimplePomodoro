"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from pathlib import Path
import os
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
        app = Adw.Application(application_id="io.github.simplepomodoro.Smoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        theme_file = Path(directory, "omarchy/current/theme/colors.toml")
        theme_file.parent.mkdir(parents=True)
        theme_file.write_text('accent = "#123456"\nbackground = "#ffffff"\nmode = "light"\n')
        window = Window(app)
        assert window.palette.focus == "#123456"
        assert Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_LIGHT
        errors = []
        window.theme_provider.connect("parsing-error", lambda _provider, _section, error: errors.append(str(error)))
        theme_file.write_text('accent = "#abcdef"\nmode = "dark"\n')
        window.reload_theme()
        assert window.palette.focus == "#abcdef"
        assert Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK
        assert not errors, errors
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
        assert restored.warning.get_value_as_int() == 12
        restored.close()
        print("PASS: GTK construction, planner, start/pause/reset, warning, settings, desktop palette reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
