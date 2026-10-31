"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from pathlib import Path
import os
import json
import threading
import time
from unittest.mock import Mock
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from simplepomodoro.app import Window
from simplepomodoro.core import Config
from simplepomodoro.gallery import GallerySound


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
        dialog.show_gallery()
        gallery = dialog.gallery_dialog
        assert gallery.purpose() == "reminder"
        gallery.query.set_text("bell & pip")
        assert "q=bell+%26+pip" in gallery.browser_button.get_uri()
        gallery.api_key_entry.set_text("testcredential123456")
        gallery.save_key()
        assert not gallery.api_key_entry.get_text()
        gallery.clear_key()
        result = GallerySound("Test bell", "Example", "https://freesound.org/people/Example/sounds/123/",
                              "CC0", "https://creativecommons.org/publicdomain/zero/1.0/",
                              "https://cdn.freesound.org/previews/1/123_456-hq.ogg", None, 0.2, "audio/ogg", 123, 0.01)
        gallery.gallery.search = Mock(return_value=[result])
        gallery.query.set_text("bell")
        gallery.search()
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 2
        while gallery.cancel_button.get_sensitive() and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)
        assert gallery.selected() == result
        assert "Example" in gallery.details.get_text()
        downloaded = window.sound_library.directory / "test-download.ogg"
        def fake_download(_result, folder, cancel):
            assert folder == window.sound_library.directory
            downloaded.write_bytes(b"OggS")
            downloaded.with_name(downloaded.name + ".json").write_text(json.dumps({"author": "Example"}))
            return downloaded
        gallery.gallery.download = Mock(side_effect=fake_download)
        gallery.download()
        deadline = time.monotonic() + 2
        while gallery.cancel_button.get_sensitive() and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)
        assert gallery.downloaded == downloaded
        assert any(choice.id == "file:test-download.ogg" for choice in dialog.choices)
        gallery.preview()
        assert window.audio.play_choice.call_args.args[0].path == downloaded
        stale_file = window.sound_library.directory / "stale.ogg"
        stale_file.write_bytes(b"OggS")
        stale_file.with_name(stale_file.name + ".json").write_text("{}")
        stale_cancel = threading.Event()
        stale_cancel.set()
        gallery.finish_operation(gallery.generation - 1, stale_cancel, window.sound_library.directory,
                                 lambda *_: (_ for _ in ()).throw(AssertionError("stale callback")), stale_file, None)
        assert not stale_file.exists()
        started = threading.Event()
        released = threading.Event()
        def blocked_search(cancel):
            started.set()
            cancel.wait(2)
            released.set()
            return []
        gallery.run_operation(blocked_search, lambda *_: (_ for _ in ()).throw(AssertionError("closed callback")))
        assert started.wait(1)
        gallery.force_close()
        deadline = time.monotonic() + 2
        while not released.is_set() and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)
        while context.pending():
            context.iteration(False)
        assert released.is_set()
        assert gallery.closed
        assert gallery.cancel_event.is_set()
        assert dialog.gallery_dialog is None
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
        print("PASS: GTK controls, sound form, gallery async search/download/preview, cancellation and persistence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
