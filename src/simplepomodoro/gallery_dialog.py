"""Compact Freesound browser with transient previews and explicit library saves."""
from pathlib import Path
import shutil
import tempfile
import threading
import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from .gallery import FreesoundGallery, GalleryError, browser_search_url
from .freesound_credentials import (CredentialError, clear_api_key, credential_state,
                                    migrate_api_key, save_api_key, use_session_key)
from .sounds import Sound


class PreviewCache:
    """Defer removal until the writer exits; never delete beneath a download."""
    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix="simplepomodoro-preview-", dir="/tmp"))
        self.writing = True
        self.discarded = False

    def discard(self):
        self.discarded = True
        if not self.writing:
            shutil.rmtree(self.directory, ignore_errors=True)

    def finished(self):
        self.writing = False
        if self.discarded:
            shutil.rmtree(self.directory, ignore_errors=True)


def compact_label(text="", **kwargs):
    return Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                     max_width_chars=60, **kwargs)


class GalleryDialog(Adw.Dialog):
    def __init__(self, sound_settings, gallery=None):
        super().__init__(title="Find sounds", content_width=650, content_height=480)
        self.settings = sound_settings
        self.gallery = gallery or FreesoundGallery()
        self.cancel_event = threading.Event()
        self.generation = 0
        self.closed = False
        self.results = []
        self.downloaded = None
        self.preview_cache = None
        self.preview_path = None
        self.preview_id = None
        self.credential_generation = 0
        self.credential_cancel = Gio.Cancellable()
        self.key_state = "checking"
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         propagate_natural_height=True)
        outer.append(self.scroll)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=10, margin_bottom=14, margin_start=18, margin_end=18)
        self.scroll.set_child(body)
        key_row = Gtk.Box(spacing=8)
        key_row.append(Gtk.Label(label="API key"))
        self.api_key_entry = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)
        self.api_key_entry.set_tooltip_text("Enter or replace your Freesound API key")
        key_row.append(self.api_key_entry)
        self.save_key_button = Gtk.Button(label="Save key")
        self.save_key_button.connect("clicked", self.save_key)
        key_row.append(self.save_key_button)
        self.clear_key_button = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Remove saved and session keys")
        self.clear_key_button.connect("clicked", self.clear_key)
        key_row.append(self.clear_key_button)
        body.append(key_row)
        key_info = Gtk.Box(spacing=8)
        self.credential_status = compact_label("Checking desktop keyring…", hexpand=True)
        key_info.append(self.credential_status)
        self.session_button = Gtk.Button(label="Use for session", visible=False)
        self.session_button.connect("clicked", self.use_session)
        key_info.append(self.session_button)
        key_info.append(Gtk.LinkButton(label="Get API key", uri="https://freesound.org/apiv2/apply/"))
        body.append(key_info)
        row = Gtk.Box(spacing=8)
        self.query = Gtk.SearchEntry(placeholder_text="bell, beep, chime…", hexpand=True)
        self.query.connect("activate", self.search)
        self.query.connect("notify::text", self.query_changed)
        row.append(self.query)
        self.search_button = Gtk.Button(label="Search")
        self.search_button.connect("clicked", self.search)
        row.append(self.search_button)
        self.cancel_button = Gtk.Button(icon_name="process-stop-symbolic", tooltip_text="Cancel request / stop preview", sensitive=False)
        self.cancel_button.connect("clicked", self.cancel)
        row.append(self.cancel_button)
        body.append(row)
        row = Gtk.Box(spacing=8)
        self.purpose_choice = Gtk.DropDown.new_from_strings(["Reminder · ≤3 s", "Countdown pip · ≤0.30 s"])
        self.purpose_choice.set_hexpand(True)
        self.purpose_choice.set_tooltip_text("Countdown requires an onset within 30 ms")
        self.purpose_choice.connect("notify::selected", self.purpose_changed)
        row.append(self.purpose_choice)
        self.browser_button = Gtk.LinkButton(label="Search in browser", uri=browser_search_url(""))
        row.append(self.browser_button)
        body.append(row)
        row = Gtk.Box(spacing=8)
        self.result_choice = Gtk.DropDown(hexpand=True, sensitive=False)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda _factory, item: item.set_child(Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=44)))
        factory.connect("bind", lambda _factory, item: item.get_child().set_text(item.get_item().get_string()))
        self.result_choice.set_factory(factory)
        self.result_choice.set_list_factory(factory)
        self.result_choice.connect("notify::selected", self.selection_changed)
        row.append(self.result_choice)
        self.preview_button = Gtk.Button(label="Preview", sensitive=False)
        self.preview_button.connect("clicked", self.preview)
        row.append(self.preview_button)
        body.append(row)
        self.details = compact_label("", selectable=True)
        self.details.set_lines(2)
        body.append(self.details)
        row = Gtk.Box(spacing=8)
        self.source_link = Gtk.LinkButton(label="Source / creator", uri="https://freesound.org", sensitive=False)
        self.license_link = Gtk.LinkButton(label="License", uri="https://creativecommons.org", sensitive=False)
        row.append(self.source_link)
        row.append(self.license_link)
        row.append(compact_label("OGG/MP3 preview quality", hexpand=True))
        body.append(row)
        self.destination = compact_label()
        body.append(self.destination)
        self.status = compact_label("Search here or open Freesound in your browser.")
        self.status.set_lines(2)
        body.append(self.status)
        self.download_button = Gtk.Button(label="Save sound", halign=Gtk.Align.CENTER, sensitive=False)
        self.download_button.add_css_class("suggested-action")
        self.download_button.connect("clicked", self.download)
        body.append(self.download_button)
        self.set_child(outer)
        self.update_destination()
        self.connect("closed", self.on_closed)
        self.run_credential_operation(lambda cancel: credential_state(cancel), initial=True)

    def purpose(self):
        return "countdown" if self.purpose_choice.get_selected() == 1 else "reminder"

    def update_browser_url(self, *_):
        if hasattr(self, "browser_button"):
            self.browser_button.set_uri(browser_search_url(self.query.get_text(), self.purpose()))

    def query_changed(self, *_):
        self.update_browser_url()
        if hasattr(self, "status"):
            self.cancel(silent=True)

    def purpose_changed(self, *_):
        self.cancel(silent=True)
        self.show_results([])
        self.update_browser_url()
        self.set_status("Search again with this sound length filter.")

    def set_status(self, text):
        self.status.set_text(text)
        self.status.set_tooltip_text(text)

    def run_credential_operation(self, operation, initial=False):
        self.credential_cancel.cancel()
        self.credential_cancel = Gio.Cancellable()
        self.credential_generation += 1
        generation = self.credential_generation
        cancel = self.credential_cancel
        self.save_key_button.set_sensitive(False)
        self.clear_key_button.set_sensitive(False)
        def worker():
            try:
                state = operation(cancel)
                error = None
            except (CredentialError, ValueError) as failure:
                state, error = None, str(failure)
            except Exception:
                state, error = None, "Desktop keyring unavailable. Use this key for the session."
            GLib.idle_add(self.finish_credentials, generation, state, error, initial)
        threading.Thread(target=worker, daemon=True).start()

    def finish_credentials(self, generation, state, error, initial):
        if self.closed or generation != self.credential_generation:
            return GLib.SOURCE_REMOVE
        self.save_key_button.set_sensitive(True)
        self.clear_key_button.set_sensitive(True)
        if error:
            self.session_button.set_visible(True)
            self.credential_status.set_text(error)
            self.credential_status.set_tooltip_text(error)
            if not initial:
                self.set_status(error)
            return GLib.SOURCE_REMOVE
        self.key_state = state
        messages = {"environment": "Environment key active · local Save/Remove won't change it",
                    "session": "Key active for this session only", "keyring": "Saved in desktop keyring",
                    "locked": "Desktop keyring locked · unlock to search",
                    "legacy": "Legacy local file · Move to keyring", "none": "No key · browser search still works",
                    "unavailable": "Desktop keyring unavailable · session-only available"}
        message = messages.get(state, "No key")
        self.credential_status.set_text(message)
        self.credential_status.set_tooltip_text(message)
        self.save_key_button.set_label("Move to keyring" if state == "legacy" else "Save key")
        self.api_key_entry.set_tooltip_text(message + ". Type to replace the key.")
        self.api_key_entry.set_property("placeholder-text", "Saved · type to replace" if state in ("keyring", "locked", "legacy", "environment", "session") else "Enter Freesound API key")
        self.session_button.set_visible(state in ("unavailable", "locked", "session"))
        if not initial:
            self.set_status(message)
        return GLib.SOURCE_REMOVE

    def save_key(self, *_):
        value = self.api_key_entry.get_text()
        migrating = not value.strip() and self.key_state == "legacy"
        def store(cancel):
            migrate_api_key(cancel) if migrating else save_api_key(value, cancel)
            return credential_state(cancel)
        self.credential_status.set_text("Saving to desktop keyring…")
        self.run_credential_operation(store)

    def clear_key(self, *_):
        def remove(cancel):
            clear_api_key(cancel)
            return credential_state(cancel)
        self.api_key_entry.set_text("")
        self.run_credential_operation(remove)

    def use_session(self, *_):
        try:
            use_session_key(self.api_key_entry.get_text())
            self.run_credential_operation(lambda cancel: credential_state(cancel))
        except ValueError as error:
            self.set_status(str(error))

    def update_destination(self):
        folder = str(self.settings.owner.sound_library.directory)
        self.destination.set_text("Library: " + folder)
        self.destination.set_tooltip_text(folder)

    def selected(self):
        index = self.result_choice.get_selected()
        return self.results[index] if index < len(self.results) else None

    def discard_preview(self):
        self.settings.owner.audio.stop()
        if self.preview_cache:
            self.preview_cache.discard()
        self.preview_cache = None
        self.preview_path = None
        self.preview_id = None

    def selection_changed(self, *_):
        self.cancel(silent=True)
        sound = self.selected()
        present = sound is not None
        self.download_button.set_sensitive(present)
        self.preview_button.set_sensitive(present)
        self.source_link.set_sensitive(present)
        self.license_link.set_sensitive(present)
        if not sound:
            self.details.set_text("")
            return
        onset = f"onset {sound.start_time_seconds * 1000:.0f} ms" if sound.start_time_seconds is not None else "onset unknown"
        text = f"{sound.author} · {sound.license_name} · {sound.duration_seconds:g} s\nFreesound #{sound.sound_id} · {onset}"
        self.details.set_text(text)
        self.details.set_tooltip_text(sound.title + "\n" + text)
        self.source_link.set_uri(sound.source_url)
        self.license_link.set_uri(sound.license_url)
        self.license_link.set_label(sound.license_name)

    def set_busy(self, busy):
        self.search_button.set_sensitive(not busy)
        self.query.set_sensitive(not busy)
        self.result_choice.set_sensitive(not busy and bool(self.results))
        self.cancel_button.set_sensitive(busy or self.preview_path is not None)
        self.download_button.set_sensitive(not busy and self.selected() is not None)
        self.preview_button.set_sensitive(not busy and self.selected() is not None)

    def cancel(self, *_args, silent=False):
        self.cancel_event.set()
        self.generation += 1
        self.discard_preview()
        self.set_busy(False)
        if not silent:
            self.set_status("Cancelled.")

    def run_operation(self, operation, callback, directory=None, cache=None):
        self.cancel_event.set()
        self.cancel_event = threading.Event()
        self.generation += 1
        generation = self.generation
        cancel = self.cancel_event
        self.set_busy(True)
        def worker():
            try:
                value = operation(cancel)
                error = None
            except GalleryError as failure:
                value, error = None, str(failure)
            except Exception:
                value, error = None, "Could not complete this request. Try again."
            finally:
                if cache:
                    if cancel.is_set():
                        cache.discard()
                    cache.finished()
            GLib.idle_add(self.finish_operation, generation, cancel, directory, callback, value, error, cache)
        threading.Thread(target=worker, daemon=True).start()

    def finish_operation(self, generation, cancel, directory, callback, value, error, cache=None):
        stale = (self.closed or cancel.is_set() or generation != self.generation
                 or (directory is not None and directory != self.settings.owner.sound_library.directory))
        if stale:
            if cache:
                cache.discard()
            elif directory is not None and isinstance(value, Path):
                value.unlink(missing_ok=True)
                value.with_name(value.name + ".json").unlink(missing_ok=True)
            if not self.closed and generation == self.generation:
                self.set_busy(False)
                self.set_status("Library folder changed. Save again.")
            return GLib.SOURCE_REMOVE
        self.set_busy(False)
        if error:
            if cache:
                cache.discard()
            self.set_status(error)
        else:
            callback(value)
        return GLib.SOURCE_REMOVE

    def search(self, *_):
        self.cancel(silent=True)
        query, purpose = self.query.get_text(), self.purpose()
        self.set_status("Searching Freesound…")
        self.run_operation(lambda cancel: self.gallery.search(query, cancel, purpose=purpose), self.show_results)

    def show_results(self, results):
        self.results = results
        self.result_choice.set_model(Gtk.StringList.new([sound.title for sound in results]))
        self.result_choice.set_selected(0)
        self.selection_changed()
        self.set_busy(False)
        notice = getattr(self.gallery, "notice", "")
        message = f"{len(results)} short sounds" if results else "No matches. Try beep, bell, or a wider duration."
        self.set_status(message + (" · " + notice if notice else ""))

    def download(self, *_):
        sound = self.selected()
        if sound is None:
            return
        self.cancel(silent=True)
        directory = self.settings.owner.sound_library.directory
        self.update_destination()
        self.set_status("Saving sound and attribution…")
        self.run_operation(lambda cancel: self.gallery.download(sound, directory, cancel), self.download_complete, directory)

    def download_complete(self, path):
        self.downloaded = path
        self.settings.refresh_choices()
        self.set_status(f"Saved {path.name}")

    def preview(self, *_):
        sound = self.selected()
        if sound is None:
            return
        if self.preview_path and self.preview_id == sound.sound_id:
            self.play_preview(self.preview_path)
            return
        self.cancel(silent=True)
        cache = PreviewCache()
        self.preview_cache = cache
        self.preview_id = sound.sound_id
        self.set_status("Loading preview…")
        self.run_operation(lambda cancel: self.gallery.download(sound, cache.directory, cancel), self.play_preview, cache=cache)

    def play_preview(self, path):
        self.preview_path = path
        self.settings.stop_test()
        self.settings.owner.audio.play_choice(Sound("preview", path.name, path), self.settings.owner.volume.get_value())
        self.cancel_button.set_sensitive(True)
        self.set_status("Playing preview")

    def on_closed(self, *_):
        self.closed = True
        self.credential_cancel.cancel()
        self.credential_generation += 1
        self.cancel(silent=True)
        self.settings.gallery_dialog = None
