"""Run in a graphical session with temporary XDG directories (see README)."""
import tempfile
from pathlib import Path
import os
import json
import threading
import time
from unittest.mock import Mock, patch
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
        key_state = {"value": "none"}
        def save_fake_key(_value, _cancel):
            key_state["value"] = "keyring"
        def clear_fake_key(_cancel):
            key_state["value"] = "none"
        # Never use the user's real Secret Service in a smoke test.
        with patch("simplepomodoro.gallery_dialog.credential_state", side_effect=lambda *_: key_state["value"]), \
             patch("simplepomodoro.gallery_dialog.save_api_key", side_effect=save_fake_key), \
             patch("simplepomodoro.gallery_dialog.clear_api_key", side_effect=clear_fake_key):
            dialog.show_gallery()
            gallery = dialog.gallery_dialog
            context = GLib.MainContext.default()
            def wait_until(condition):
                deadline = time.monotonic() + 2
                while not condition() and time.monotonic() < deadline:
                    while context.pending():
                        context.iteration(False)
                    time.sleep(0.01)
                assert condition()
            wait_until(lambda: gallery.key_state == "none")
            assert gallery.purpose() == "reminder"
            gallery.query.set_text("bell & pip")
            assert "q=bell+%26+pip" in gallery.browser_button.get_uri()
            gallery.api_key_entry.set_text("testcredential123456")
            gallery.save_key()
            wait_until(lambda: gallery.key_state == "keyring")
            assert gallery.api_key_entry.get_text() == "testcredential123456"
            assert "Saved in desktop keyring" in gallery.credential_status.get_text()
            gallery.clear_key()
            wait_until(lambda: gallery.key_state == "none")
            result = GallerySound("Test bell", "Example", "https://freesound.org/people/Example/sounds/123/",
                                  "CC0", "https://creativecommons.org/publicdomain/zero/1.0/",
                                  "https://cdn.freesound.org/previews/1/123_456-hq.ogg", None, 0.2, "audio/ogg", 123, 0.01)
            gallery.gallery.search = Mock(return_value=[result])
            gallery.query.set_text("bell")
            gallery.search()
            wait_until(lambda: gallery.selected() == result)
            assert "Example" in gallery.details.get_text()
            def fake_download(_result, folder, cancel):
                path = folder / "test-download.ogg"
                path.write_bytes(b"OggS")
                path.with_name(path.name + ".json").write_text(json.dumps({"author": "Example"}))
                return path
            gallery.gallery.download = Mock(side_effect=fake_download)
            gallery.preview()
            wait_until(lambda: gallery.preview_path is not None)
            preview_path = gallery.preview_path
            preview_folder = preview_path.parent
            assert preview_folder.parent == Path("/tmp")
            assert preview_folder.stat().st_mode & 0o777 == 0o700
            assert not list(window.sound_library.directory.iterdir())
            assert window.audio.play_choice.call_args.args[0].path == preview_path
            gallery.cancel()
            assert not preview_folder.exists()
            gallery.download()
            wait_until(lambda: gallery.downloaded is not None)
            downloaded = gallery.downloaded
            assert downloaded.parent == window.sound_library.directory
            assert any(choice.id == "file:test-download.ogg" for choice in dialog.choices)
            # Close during an active preview writer: cleanup waits for that writer.
            started = threading.Event()
            released = threading.Event()
            def blocked_download(_result, folder, cancel):
                path = folder / "partial.ogg"
                path.write_bytes(b"partial")
                started.set()
                cancel.wait(2)
                released.set()
                return path
            gallery.gallery.download = Mock(side_effect=blocked_download)
            gallery.preview()
            assert started.wait(1)
            pending_folder = gallery.preview_cache.directory
            gallery.force_close()
            wait_until(lambda: released.is_set() and not pending_folder.exists())
            assert gallery.closed
            assert gallery.cancel_event.is_set()
            assert dialog.gallery_dialog is None
            assert downloaded.exists()  # Only explicit Save sound persists.
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
