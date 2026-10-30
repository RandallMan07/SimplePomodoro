"""Sound library form, explicit previews, and a cancellable countdown test."""
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

class SoundSettings(Adw.Dialog):
    def __init__(self, owner):
        super().__init__(title="Sound library", content_width=650, content_height=580)
        self.owner = owner
        self.test_source = 0
        self.test_step = 0
        self.dropdowns = {}
        self.refreshing = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        outer.append(header)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.append(scroll)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                       margin_top=16, margin_bottom=20, margin_start=20, margin_end=20)
        scroll.set_child(body)
        body.append(Gtk.Label(label="Choose sounds for each reminder. Preview always plays at your current volume, even when automatic tones are muted.", wrap=True, xalign=0))
        self.folder = Gtk.Entry(text=str(owner.sound_library.directory), hexpand=True)
        self.folder.set_tooltip_text("Local folder containing WAV, OGG, MP3, FLAC, Opus, or M4A sounds")
        body.append(Gtk.Label(label="Sound folder", xalign=0))
        row = Gtk.Box(spacing=8)
        row.append(self.folder)
        browse = Gtk.Button(label="Browse…")
        browse.connect("clicked", self.choose_folder)
        row.append(browse)
        refresh = Gtk.Button(label="Use folder / Refresh")
        refresh.connect("clicked", self.change_folder)
        row.append(refresh)
        body.append(row)
        self.extension_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.append(self.extension_box)
        for event, title in (("warning", "Heads-up"), ("phase", "Phase change"), ("complete", "Session complete"), ("countdown", "Countdown pip")):
            row = Gtk.Box(spacing=10)
            row.append(Gtk.Label(label=title, xalign=0, width_chars=17))
            dropdown = Gtk.DropDown(hexpand=True)
            dropdown.connect("notify::selected", self.selection_changed, event)
            self.dropdowns[event] = dropdown
            row.append(dropdown)
            preview = Gtk.Button(label="Preview")
            preview.connect("clicked", self.preview, event)
            row.append(preview)
            body.append(row)
        row = Gtk.Box(spacing=12)
        row.append(Gtk.Label(label="Beep with 3, 2, 1 seconds remaining", hexpand=True, xalign=0))
        self.countdown = Gtk.Switch(valign=Gtk.Align.CENTER, active=owner.countdown_enabled)
        self.countdown.connect("notify::active", self.countdown_changed)
        row.append(self.countdown)
        body.append(row)
        body.append(Gtk.Label(label="Countdown pips are limited to 300 ms. The heads-up and phase-change sounds remain independent.", wrap=True, xalign=0))
        row = Gtk.Box(spacing=10)
        test = Gtk.Button(label="Test 3 · 2 · 1 + change")
        test.connect("clicked", self.start_test)
        row.append(test)
        stop = Gtk.Button(label="Stop preview")
        stop.connect("clicked", lambda *_: self.stop_test())
        row.append(stop)
        body.append(row)
        self.status = Gtk.Label(wrap=True, xalign=0)
        body.append(self.status)
        self.set_child(outer)
        self.refresh_choices()
        self.connect("closed", self.on_closed)

    def refresh_choices(self):
        self.owner.sound_library.refresh()
        self.choices = list(self.owner.sound_library.sounds)
        self.refreshing = True
        for event, dropdown in self.dropdowns.items():
            selection = self.owner.sound_library.resolve(self.owner.sound_selections.get(event), event).id
            dropdown.set_model(Gtk.StringList.new([sound.title for sound in self.choices]))
            dropdown.set_selected(next(i for i, sound in enumerate(self.choices) if sound.id == selection))
            self.owner.sound_selections[event] = selection
        self.refreshing = False
        self.status.set_text(self.owner.sound_library.error or f"{len(self.choices)} sounds available. Changes are saved immediately.")

    def choose_folder(self, *_):
        chooser = Gtk.FileDialog(title="Choose sound folder")
        chooser.set_initial_folder(Gio.File.new_for_path(str(self.owner.sound_library.directory)))
        chooser.select_folder(self.owner, None, self.folder_selected)

    def folder_selected(self, chooser, result):
        try:
            folder = chooser.select_folder_finish(result)
            if folder and folder.get_path():
                self.folder.set_text(folder.get_path())
                self.change_folder()
        except GLib.Error:
            pass  # Cancelling the native chooser leaves the library unchanged.

    def change_folder(self, *_):
        value = self.folder.get_text().strip()
        if not value:
            self.status.set_text("Enter a folder path or choose Browse.")
            return
        self.stop_test()
        self.owner.sound_library.directory = Path(value).expanduser().absolute()
        self.folder.set_text(str(self.owner.sound_library.directory))
        self.refresh_choices()
        self.owner.save_settings()

    def selection_changed(self, dropdown, _pspec, event):
        if self.refreshing or not hasattr(self, "choices"):
            return
        index = dropdown.get_selected()
        if index < len(self.choices):
            self.stop_test()
            self.owner.sound_selections[event] = self.choices[index].id
            self.owner.save_settings()

    def countdown_changed(self, *_):
        self.stop_test()
        self.owner.countdown_enabled = self.countdown.get_active()
        self.owner.countdown_cues.prime(self.owner.timer)
        self.owner.save_settings()

    def preview(self, _button, event):
        self.stop_test()
        self.owner.play_sound(event)
        self.status.set_text("Playing selected sound…")

    def start_test(self, *_):
        self.stop_test()
        self.test_step = 3
        self.test_tick()
        self.test_source = GLib.timeout_add(1000, self.test_tick)

    def test_tick(self):
        if self.test_step:
            self.status.set_text(f"{self.test_step}…")
            self.owner.play_sound("countdown")
            self.test_step -= 1
            return GLib.SOURCE_CONTINUE
        self.owner.play_sound("phase")
        self.status.set_text("Phase change. Test complete.")
        self.test_source = 0
        return GLib.SOURCE_REMOVE

    def stop_test(self):
        if self.test_source:
            GLib.source_remove(self.test_source)
            self.test_source = 0
        self.test_step = 0
        self.owner.audio.stop()

    def on_closed(self, *_):
        self.stop_test()
        self.owner.sound_dialog = None
