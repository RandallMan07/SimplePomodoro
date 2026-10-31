"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from unittest.mock import patch
from pathlib import Path
import os
from simplepomodoro import layer_support  # Layer shell must load before GTK.
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from simplepomodoro.app import Application, Window
from simplepomodoro.core import Config
from simplepomodoro.widget import LayerShell, widget_available


def main():
    Gtk.init_check()
    if Gdk.Display.get_default() is None:
        print("SKIP: no accessible graphical display")
        return 77
    with (tempfile.TemporaryDirectory(prefix="simplepomodoro-smoke-") as directory,
          patch("simplepomodoro.app.open_floating"),
          patch("simplepomodoro.app.capture_for_widget", lambda callback: callback(None)),
          patch("simplepomodoro.app.restore_after_widget")):
        def pump():
            context = GLib.MainContext.default()
            for _ in range(30):
                if context.pending():
                    context.iteration(False)
        os.environ["XDG_CONFIG_HOME"] = directory
        os.environ["XDG_CACHE_HOME"] = directory
        app = Adw.Application(application_id="io.github.simplepomodoro.Smoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        window = Window(app)
        assert window.timer.config == Config()
        assert not hasattr(window, "minimize_button")
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
        window.present()
        with patch("simplepomodoro.widget.LayerShell", None):
            assert not widget_available()
            assert not window.show_widget()
            assert window.get_visible()
        if widget_available():
            window.present()
            assert window.show_widget()
            pump()
            widget = window.summary_widget
            assert LayerShell.is_layer_window(widget)
            assert LayerShell.get_layer(widget) == LayerShell.Layer.OVERLAY
            assert LayerShell.get_anchor(widget, LayerShell.Edge.TOP)
            assert LayerShell.get_exclusive_zone(widget) == 0
            assert not window.get_visible()
            assert not widget.expanded
            widget.pointer_enter()
            assert widget.expanded
            widget.arrow.emit("clicked")  # Mouse click must never pin.
            assert not hasattr(widget, "pinned")
            widget.pause_button.emit("clicked")
            assert window.timer.running
            assert "Focus" in widget.state_label.get_text()
            widget.pause_button.emit("clicked")
            assert not window.timer.running
            widget.pointer_leave()
            widget.focus_windows.clear()
            widget.cancel_collapse()
            widget.collapse()
            assert not widget.expanded
            widget.open_button.emit("clicked")
            assert window.summary_widget is None
            assert window.get_visible()
            assert window.show_widget()
            pump()
            assert window.summary_widget is not widget
            Application.do_activate(app)
            assert window.summary_widget is None
            assert window.get_visible()
            assert len([item for item in app.get_windows() if isinstance(item, Window)]) == 1
            window.reset_timer()
            # New activation invalidates an in-flight capture, preventing a late hide.
            callbacks = []
            with patch("simplepomodoro.app.capture_for_widget", callbacks.append):
                window.show_widget()
                Application.do_activate(app)
                callbacks[0](None)
                pump()
                assert window.summary_widget is None
                assert window.get_visible()
        else:
            assert not window.compact_button.get_sensitive()
        window.warning.set_value(12)
        window.save_settings()
        assert Path(directory, "simplepomodoro/settings.json").exists()
        window.close()
        restored = Window(app)
        assert restored.warning.get_value_as_int() == 12
        if widget_available():
            restored.present()
            restored.show_widget()
            pump()
        restored.close()
        assert restored.summary_widget is None
        print("PASS: GTK construction, planner, start/pause/reset, warning, settings, summary widget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
