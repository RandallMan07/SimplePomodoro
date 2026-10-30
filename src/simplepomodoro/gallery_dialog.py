"""Asynchronous Commons browser; network access requires a user action."""
from pathlib import Path
import threading
import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from .gallery import CommonsGallery, GalleryError
from .sounds import Sound


class GalleryDialog(Adw.Dialog):
    def __init__(self, sound_settings, gallery=None):
        super().__init__(title="Download free sounds", content_width=660, content_height=600)
        self.settings = sound_settings
        self.gallery = gallery or CommonsGallery()
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
        body.append(Gtk.Label(label="Search Wikimedia Commons. Results use CC0, public-domain, CC BY, or CC BY-SA licenses. Review the source and attribution before downloading.", wrap=True, xalign=0))
        row = Gtk.Box(spacing=8)
        self.query = Gtk.SearchEntry(placeholder_text="Try bell, beep, or chime", hexpand=True)
        self.query.connect("activate", self.search)
        row.append(self.query)
        self.search_button = Gtk.Button(label="Search")
        self.search_button.connect("clicked", self.search)
        row.append(self.search_button)
        self.cancel_button = Gtk.Button(label="Cancel", sensitive=False)
        self.cancel_button.connect("clicked", self.cancel)
        row.append(self.cancel_button)
        body.append(row)
        body.append(Gtk.Label(label="Shows up to 10 matches. Unsupported licenses/formats, restrictions, and files above 15 MiB are filtered out. Downloads require internet; the timer works offline.", wrap=True, xalign=0))
        self.result_choice = Gtk.DropDown(hexpand=True, sensitive=False)
        self.result_choice.connect("notify::selected", self.selection_changed)
        body.append(self.result_choice)
        self.details = Gtk.Label(wrap=True, xalign=0, selectable=True)
        body.append(self.details)
        links = Gtk.Box(spacing=12)
        self.source_link = Gtk.LinkButton(label="Source and attribution", uri="https://commons.wikimedia.org", sensitive=False)
        self.license_link = Gtk.LinkButton(label="License", uri="https://creativecommons.org", sensitive=False)
        links.append(self.source_link)
        links.append(self.license_link)
        body.append(links)
        self.destination = Gtk.Label(wrap=True, xalign=0, selectable=True)
        body.append(self.destination)
        row = Gtk.Box(spacing=10)
        self.download_button = Gtk.Button(label="Download selected sound", sensitive=False)
        self.download_button.connect("clicked", self.download)
        row.append(self.download_button)
        self.preview_button = Gtk.Button(label="Preview download", sensitive=False)
        self.preview_button.connect("clicked", self.preview)
        row.append(self.preview_button)
        body.append(row)
        self.status = Gtk.Label(label="Search to browse sounds. Nothing is downloaded automatically.", wrap=True, xalign=0)
        body.append(self.status)
        self.set_child(outer)
        self.update_destination()
        self.connect("closed", self.on_closed)

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
        self.details.set_text(f"{sound.title}\nCreator: {sound.author}\nLicense: {sound.license_name}\n{duration} · {sound.size_bytes / 1024:.1f} KiB\nThe original file and attribution sidecar will be saved together.")
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
        self.status.set_text("Searching Wikimedia Commons…")
        self.run_operation(lambda cancel: self.gallery.search(query, cancel), self.show_results)

    def show_results(self, results):
        self.results = results
        self.result_choice.set_model(Gtk.StringList.new([sound.title for sound in results]))
        self.result_choice.set_selected(0)
        self.result_choice.set_sensitive(bool(results))
        self.selection_changed()
        if not results:
            self.source_link.set_sensitive(False)
            self.license_link.set_sensitive(False)
        self.status.set_text(f"{len(results)} matching sounds. Select one to review its source and license." if results else "No supported sounds found. Try a more specific search such as short bell or electronic beep.")

    def download(self, *_):
        sound = self.selected()
        if sound is None:
            return
        directory = self.settings.owner.sound_library.directory
        self.update_destination()
        self.status.set_text("Downloading selected sound and saving attribution…")
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
