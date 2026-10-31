"""Asynchronous Freesound browser; network access requires a user action."""
from pathlib import Path
import os
import threading
import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from .gallery import FreesoundGallery, GalleryError, browser_search_url
from .freesound_credentials import clear_api_key, credentials_path, save_api_key
from .sounds import Sound


class GalleryDialog(Adw.Dialog):
    def __init__(self, sound_settings, gallery=None):
        super().__init__(title="Download free sounds", content_width=660, content_height=600)
        self.settings = sound_settings
        self.gallery = gallery or FreesoundGallery()
        self.cancel_event = threading.Event()
        self.generation = 0
        self.closed = False
        self.results = []
        self.downloaded = None
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.append(scroll)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                       margin_top=16, margin_bottom=20, margin_start=20, margin_end=20)
        scroll.set_child(body)
        body.append(Gtk.Label(label="Find short Freesound effects under CC0 or CC BY. Downloads use OGG/MP3 preview quality, not the original recording. Review attribution before downloading.", wrap=True, xalign=0))
        setup = Gtk.Expander(label="API key setup (optional for browser search)")
        setup_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        setup_body.append(Gtk.Label(label="Create a Freesound account, then apply for an application API key. Paste the Client secret / API key here. It is stored separately in a private local file. FREESOUND_API_KEY overrides the saved key.", wrap=True, xalign=0))
        setup_body.append(Gtk.LinkButton(label="Create account / request API key", uri="https://freesound.org/apiv2/apply/"))
        if os.environ.get("FREESOUND_API_KEY"):
            setup_body.append(Gtk.Label(label="An environment API key is active. Save/Clear changes only the local key file.", wrap=True, xalign=0))
        credential_row = Gtk.Box(spacing=8)
        self.api_key_entry = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)
        self.api_key_entry.set_tooltip_text("Freesound Client secret / API key; never included in search URLs")
        credential_row.append(self.api_key_entry)
        save_key = Gtk.Button(label="Save key")
        save_key.connect("clicked", self.save_key)
        credential_row.append(save_key)
        clear_key = Gtk.Button(label="Clear saved key")
        clear_key.connect("clicked", self.clear_key)
        credential_row.append(clear_key)
        setup_body.append(credential_row)
        setup.set_child(setup_body)
        body.append(setup)
        self.credential_status = Gtk.Label(wrap=True, xalign=0)
        body.append(self.credential_status)
        self.update_credential_status()
        row = Gtk.Box(spacing=8)
        self.query = Gtk.SearchEntry(placeholder_text="Try bell, beep, or chime", hexpand=True)
        self.query.connect("activate", self.search)
        self.query.connect("notify::text", self.update_browser_url)
        row.append(self.query)
        self.search_button = Gtk.Button(label="Search")
        self.search_button.connect("clicked", self.search)
        row.append(self.search_button)
        self.cancel_button = Gtk.Button(label="Cancel", sensitive=False)
        self.cancel_button.connect("clicked", self.cancel)
        row.append(self.cancel_button)
        body.append(row)
        mode_row = Gtk.Box(spacing=10)
        self.purpose_choice = Gtk.DropDown.new_from_strings(["Reminder · up to 3 seconds", "Countdown pip · up to 0.30 seconds"])
        self.purpose_choice.set_hexpand(True)
        self.purpose_choice.connect("notify::selected", self.purpose_changed)
        mode_row.append(self.purpose_choice)
        self.browser_button = Gtk.LinkButton(label="Search in browser", uri=browser_search_url(""))
        mode_row.append(self.browser_button)
        body.append(mode_row)
        body.append(Gtk.Label(label="Shows up to 15 matches. Reminder searches require 0.05–3 second sounds. Countdown requires 0.05–0.30 seconds and onset within 30 ms. Preview downloads are capped at 15 MiB. The browser button needs no API key; downloading on the website may need an account.", wrap=True, xalign=0))
        self.result_choice = Gtk.DropDown(hexpand=True, sensitive=False)
        self.result_choice.connect("notify::selected", self.selection_changed)
        body.append(self.result_choice)
        self.details = Gtk.Label(wrap=True, xalign=0, selectable=True)
        body.append(self.details)
        links = Gtk.Box(spacing=12)
        self.source_link = Gtk.LinkButton(label="Source and attribution", uri="https://freesound.org", sensitive=False)
        self.license_link = Gtk.LinkButton(label="License", uri="https://creativecommons.org", sensitive=False)
        links.append(self.source_link)
        links.append(self.license_link)
        body.append(links)
        self.destination = Gtk.Label(wrap=True, xalign=0, selectable=True)
        body.append(self.destination)
        row = Gtk.Box(spacing=10)
        self.download_button = Gtk.Button(label="Download preview file", sensitive=False)
        self.download_button.connect("clicked", self.download)
        row.append(self.download_button)
        self.preview_button = Gtk.Button(label="Play downloaded preview", sensitive=False)
        self.preview_button.connect("clicked", self.preview)
        row.append(self.preview_button)
        body.append(row)
        self.status = Gtk.Label(label="Search to browse sounds. Nothing is downloaded automatically.", wrap=True, xalign=0)
        body.append(self.status)
        self.set_child(outer)
        self.update_destination()
        self.connect("closed", self.on_closed)

    def purpose(self):
        return "countdown" if self.purpose_choice.get_selected() == 1 else "reminder"

    def update_browser_url(self, *_):
        if hasattr(self, "browser_button"):
            self.browser_button.set_uri(browser_search_url(self.query.get_text(), self.purpose()))

    def purpose_changed(self, *_):
        self.cancel()
        self.results = []
        self.result_choice.set_model(Gtk.StringList.new([]))
        self.selection_changed()
        self.update_browser_url()
        self.status.set_text("Search again to use this sound length filter.")

    def update_credential_status(self):
        if os.environ.get("FREESOUND_API_KEY"):
            message = "Environment API key active. Save/Clear only affects the local key file."
        elif credentials_path().is_file():
            message = "Saved local API key found. Use Search to browse in the app."
        else:
            message = "No API key configured. Search in browser works without one."
        self.credential_status.set_text(message)

    def save_key(self, *_):
        try:
            save_api_key(self.api_key_entry.get_text())
            self.api_key_entry.set_text("")
            self.update_credential_status()
            self.status.set_text("API key saved privately. You can now search Freesound.")
        except ValueError as error:
            self.status.set_text(str(error))
        except OSError:
            self.status.set_text("Could not save the key. Check your local configuration folder permissions.")

    def clear_key(self, *_):
        try:
            clear_api_key()
            self.api_key_entry.set_text("")
            self.update_credential_status()
            self.status.set_text("Saved key removed. FREESOUND_API_KEY, if set, still applies. Browser search needs no key.")
        except OSError:
            self.status.set_text("Could not remove the saved key. Check configuration folder permissions.")

    def update_destination(self):
        self.destination.set_text(f"Download folder: {self.settings.owner.sound_library.directory}")

    def selected(self):
        index = self.result_choice.get_selected()
        return self.results[index] if index < len(self.results) else None

    def selection_changed(self, *_):
        sound = self.selected()
        if sound is None:
            self.details.set_text("")
            self.download_button.set_sensitive(False)
            return
        duration = f"{sound.duration_seconds:.1f} seconds" if sound.duration_seconds is not None else "duration unavailable"
        size = f"{sound.size_bytes / 1024:.1f} KiB" if sound.size_bytes is not None else "preview size measured on download"
        onset = f"onset {sound.start_time_seconds * 1000:.0f} ms" if sound.start_time_seconds is not None else "onset analysis unavailable; listen before using as a countdown"
        self.details.set_text(f"{sound.title}\nCreator: {sound.author} · Freesound #{sound.sound_id}\nLicense: {sound.license_name}\n{duration} · {onset}\n{size}\nOGG/MP3 preview file and attribution sidecar saved together.")
        self.source_link.set_uri(sound.source_url)
        self.source_link.set_sensitive(True)
        self.license_link.set_uri(sound.license_url)
        self.license_link.set_sensitive(True)
        self.download_button.set_sensitive(not self.cancel_button.get_sensitive())

    def set_busy(self, busy):
        self.search_button.set_sensitive(not busy)
        self.query.set_sensitive(not busy)
        self.result_choice.set_sensitive(not busy and bool(self.results))
        self.cancel_button.set_sensitive(busy)
        self.download_button.set_sensitive(not busy and self.selected() is not None)

    def cancel(self, *_):
        self.cancel_event.set()
        self.generation += 1
        self.set_busy(False)
        self.status.set_text("Cancelled. You can search or download again.")

    def run_operation(self, operation, callback, directory=None):
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
            except Exception as failure:
                value, error = None, f"Could not complete this request: {failure}"
            GLib.idle_add(self.finish_operation, generation, cancel, directory, callback, value, error)

        threading.Thread(target=worker, daemon=True).start()

    def finish_operation(self, generation, cancel, directory, callback, value, error):
        stale = (self.closed or cancel.is_set() or generation != self.generation
                 or (directory is not None and directory != self.settings.owner.sound_library.directory))
        if stale:
            if directory is not None and isinstance(value, Path):
                value.unlink(missing_ok=True)
                value.with_name(value.name + ".json").unlink(missing_ok=True)
            if not self.closed and generation == self.generation:
                self.set_busy(False)
                self.status.set_text("The sound folder changed. Download again to use the new folder.")
            return GLib.SOURCE_REMOVE
        self.set_busy(False)
        if error:
            self.status.set_text(error)
        else:
            callback(value)
        return GLib.SOURCE_REMOVE

    def search(self, *_):
        query = self.query.get_text()
        purpose = self.purpose()
        self.status.set_text("Searching Freesound…")
        self.run_operation(lambda cancel: self.gallery.search(query, cancel, purpose=purpose), self.show_results)

    def show_results(self, results):
        self.results = results
        self.result_choice.set_model(Gtk.StringList.new([sound.title for sound in results]))
        self.result_choice.set_selected(0)
        self.result_choice.set_sensitive(bool(results))
        self.selection_changed()
        if not results:
            self.source_link.set_sensitive(False)
            self.license_link.set_sensitive(False)
        message = f"{len(results)} short sounds. Select one to review its source and license." if results else "No suitable short sounds found. Try beep or bell, or use Reminder for a wider duration range."
        notice = getattr(self.gallery, "notice", "")
        self.status.set_text(message + (" " + notice if notice else ""))

    def download(self, *_):
        sound = self.selected()
        if sound is None:
            return
        directory = self.settings.owner.sound_library.directory
        self.update_destination()
        self.status.set_text("Downloading preview file and saving attribution…")
        self.run_operation(lambda cancel: self.gallery.download(sound, directory, cancel), self.download_complete, directory)

    def download_complete(self, path):
        self.downloaded = path
        self.settings.refresh_choices()
        self.preview_button.set_sensitive(True)
        self.status.set_text(f"Saved {path.name}. Preview here, then close this browser and select the sound for a reminder in Sound library.")

    def preview(self, *_):
        if self.downloaded and self.downloaded.is_file():
            self.settings.stop_test()
            self.settings.owner.audio.play_choice(Sound(f"file:{self.downloaded.name}", self.downloaded.name, self.downloaded), self.settings.owner.volume.get_value())

    def on_closed(self, *_):
        self.closed = True
        self.cancel_event.set()
        self.generation += 1
        self.settings.owner.audio.stop()
        self.settings.gallery_dialog = None
