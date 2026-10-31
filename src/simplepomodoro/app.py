"""Native GTK4 interface for SimplePomodoro."""
import json
import math
import os
from pathlib import Path
import sys
import time
from . import layer_support  # Must load before importing GTK/Wayland.
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
import cairo
from .audio import Chimes
from .core import Config, Timer, propose
from .desktop import capture_for_widget, open_floating, restore_after_widget
from .sounds import CountdownCues, SoundLibrary
from .sound_settings import SoundSettings
from .theme import ThemeSource, rgb
from .session import SessionStore
from .widget import SummaryWidget, widget_available

ROOT = Path(__file__).resolve().parents[2]


def label(text, css=None, **kwargs):
    widget = Gtk.Label(label=text, **kwargs)
    if css:
        widget.add_css_class(css)
    return widget


class Window(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="SimplePomodoro")
        self.set_icon_name("io.github.simplepomodoro.App")
        self.theme_source = ThemeSource()
        self.theme_provider = Gtk.CssProvider()
        self.theme_css = (ROOT / "assets/style.css").read_text()
        Gtk.StyleContext.add_provider_for_display(self.get_display(), self.theme_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.reload_theme(force=True)
        self.theme_timeout_id = GLib.timeout_add_seconds(2, self.reload_theme)
        self.summary_widget = None
        self.widget_cycle = 0
        self.widget_capture_pending = False
        self.saved_window_state = None
        self.closed = False
        self.settings_file = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "simplepomodoro/settings.json"
        self.settings = self.load_settings()
        self.initializing = True
        self.session_store = SessionStore(Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "simplepomodoro/session.json")
        self.last_checkpoint_seconds = time.monotonic()
        self.timer = Timer()
        self.audio = Chimes(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "simplepomodoro")
        self.sound_library = SoundLibrary(self.settings.get("sound_folder"))
        self.sound_selections = self.sound_library.selections(self.settings.get("sound_selections"))
        self.countdown_enabled = self.settings.get("countdown_enabled") is True
        self.countdown_cues = CountdownCues()
        self.sound_dialog = None
        self.audio_error_seen = None
        self.inhibit_cookie = 0
        self.inhibit_requested = False
        self.connect("close-request", self.on_close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Box())
        header.set_decoration_layout(":close")
        self.compact_button = Gtk.Button(icon_name="pan-up-symbolic")
        self.compact_button.set_tooltip_text("Show the top-center timer widget")
        self.compact_button.connect("clicked", self.show_widget)
        supported = widget_available()
        self.compact_button.set_sensitive(supported)
        if not supported:
            self.compact_button.set_tooltip_text("Widget requires gtk4-layer-shell and a Wayland compositor supporting layer shell")
        header.pack_end(self.compact_button)
        outer.append(header)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, propagate_natural_height=True)
        outer.append(scroll)
        clamp = Adw.Clamp(maximum_size=960, tightening_threshold=900)
        scroll.set_child(clamp)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.add_css_class("main")
        clamp.set_child(body)
        body.append(label("A LITTLE SPACE TO FOCUS", "eyebrow"))
        body.append(label("One thing at a time.", "hero"))
        body.append(label("Find your rhythm. Make room for a break.", "muted", wrap=True))

        columns = Gtk.Box(spacing=24, margin_top=10)
        timer_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, hexpand=True)
        settings_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, hexpand=True)
        columns.append(timer_panel)
        columns.append(settings_panel)
        body.append(columns)
        overlay = Gtk.Overlay()
        self.ring = Gtk.DrawingArea(content_width=300, content_height=300, hexpand=True)
        self.ring.set_draw_func(self.draw_ring)
        overlay.set_child(self.ring)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        self.phase_label = label("FOCUS", "phase")
        self.time_label = label("50:00", "time")
        self.round_label = label("Round 1 of 2", "muted")
        center.append(self.phase_label)
        center.append(self.time_label)
        center.append(self.round_label)
        overlay.add_overlay(center)
        timer_panel.append(overlay)
        self.status = label("Ready when you are.", "hint", wrap=True)
        timer_panel.append(self.status)
        self.persistence_status = label("", "hint", wrap=True)
        timer_panel.append(self.persistence_status)
        buttons = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        self.start_button = Gtk.Button(label="Start focus")
        self.start_button.add_css_class("primary")
        self.start_button.connect("clicked", self.toggle_timer)
        buttons.append(self.start_button)
        self.reset_button = Gtk.Button(label="Reset")
        self.reset_button.add_css_class("secondary")
        self.reset_button.connect("clicked", self.reset_timer)
        buttons.append(self.reset_button)
        timer_panel.append(buttons)
        self.progress = Gtk.ProgressBar()
        timer_panel.append(self.progress)
        self.summary = label("", "hint", wrap=True)
        timer_panel.append(self.summary)

        self.session_card = self.card(settings_panel, "Your rhythm")
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, column_homogeneous=True)
        self.session_card.append(grid)
        self.work = self.add_spin(grid, 0, "Focus · min", "work", 50, 1, 180)
        self.rest = self.add_spin(grid, 1, "Rest · min", "rest", 10, 1, 60)
        self.repetitions = self.add_spin(grid, 2, "Rounds", "repetitions", 2, 1, 12)
        self.session_card.append(label("Each round includes focus + rest, including the final round.", "hint", wrap=True, xalign=0))

        self.planner_card = self.card(settings_panel, "Have a time limit?")
        row = Gtk.Box(spacing=12)
        row.append(label("Available minutes", "muted", hexpand=True, xalign=0))
        self.budget = Gtk.SpinButton.new_with_range(2, 1440, 1)
        self.budget.set_value(self.setting_int("budget", 120, 2, 1440))
        self.budget.set_tooltip_text("Total time available, including all breaks")
        row.append(self.budget)
        fit = Gtk.Button(label="Find my rhythm")
        fit.connect("clicked", self.plan)
        row.append(fit)
        self.planner_card.append(row)
        self.plan_result = label("A balanced suggestion based on a 50 / 10 rhythm.", "hint", wrap=True, xalign=0)
        self.planner_card.append(self.plan_result)

        alerts = self.card(settings_panel, "Gentle reminders")
        row = Gtk.Box(spacing=12)
        row.append(label("Heads-up · seconds before change", "muted", wrap=True, xalign=0, hexpand=True))
        self.warning = Gtk.SpinButton.new_with_range(0, 60, 1)
        self.warning.set_value(self.setting_int("warning", 7, 0, 60))
        self.warning.set_tooltip_text("One advance chime per phase; 0 disables it")
        self.warning.connect("value-changed", self.alert_changed)
        row.append(self.warning)
        alerts.append(row)
        row = Gtk.Box(spacing=12)
        row.append(label("Phase-change tones", "muted", xalign=0, hexpand=True))
        self.sound = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.sound.set_active(self.settings.get("sound", True) is not False)
        self.sound.connect("notify::active", self.alert_changed)
        row.append(self.sound)
        self.preview = Gtk.Button(label="Preview")
        self.preview.connect("clicked", lambda *_: self.play_sound("phase"))
        row.append(self.preview)
        alerts.append(row)
        row = Gtk.Box(spacing=12)
        row.append(label("Volume", "muted"))
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.05)
        self.volume.set_hexpand(True)
        self.volume.set_draw_value(False)
        value = self.settings.get("volume", 0.5)
        self.volume.set_value(value if type(value) in (int, float) and 0 <= value <= 1 else 0.5)
        self.volume.connect("value-changed", self.alert_changed)
        row.append(self.volume)
        alerts.append(row)
        customize = Gtk.Button(label="Sound library & countdown…")
        customize.connect("clicked", self.show_sound_settings)
        alerts.append(customize)
        alerts.append(label("The heads-up also appears on screen. 0 seconds turns it off.", "hint", wrap=True, xalign=0))
        self.set_content(outer)
        self.loading = False
        for widget in (self.work, self.rest, self.repetitions):
            widget.connect("value-changed", self.config_changed)
        self.budget.connect("value-changed", lambda *_: self.save_settings())
        self.config_changed()
        restored_timer = self.session_store.load()
        if restored_timer is not None:
            self.loading = True
            self.timer = restored_timer
            self.work.set_value(restored_timer.config.work_minutes)
            self.rest.set_value(restored_timer.config.rest_minutes)
            self.repetitions.set_value(restored_timer.config.repetitions)
            self.warning.set_value(restored_timer.warning_seconds)
            self.loading = False
            self.save_settings()
        if self.session_store.error:
            self.persistence_status.set_text(self.session_store.error)
        self.initializing = False
        self.update_inhibit()
        self.render()
        # Request the actual content height, then let small screens scroll.
        minimum_width, natural_width, *_ = outer.measure(Gtk.Orientation.HORIZONTAL, -1)
        width = max(900, minimum_width)
        _, height, *_ = outer.measure(Gtk.Orientation.VERTICAL, width)
        self.opening_size = (width, height)
        self.set_default_size(width, height)
        self.connect("map", self.on_first_map)
        self.opening_applied = False
        self.timeout_id = GLib.timeout_add(100, self.tick)

    def reload_theme(self, force=False):
        if self.theme_source.reload(force=force):
            self.palette = self.theme_source.palette
            self.theme_provider.load_from_data((self.palette.definitions() + self.theme_css).encode())
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if self.palette.light else Adw.ColorScheme.FORCE_DARK)
            if hasattr(self, "ring"):
                self.ring.queue_draw()
        return GLib.SOURCE_CONTINUE

    def show_widget(self, *_):
        if not widget_available():
            self.status.set_text("The top-center widget needs gtk4-layer-shell and a compatible Wayland desktop.")
            return False
        if self.summary_widget is not None or self.widget_capture_pending:
            return True
        self.widget_cycle += 1
        cycle = self.widget_cycle
        self.widget_capture_pending = True

        def captured(state):
            def apply():
                if self.closed or cycle != self.widget_cycle:
                    return GLib.SOURCE_REMOVE
                self.widget_capture_pending = False
                self.saved_window_state = state
                self.summary_widget = SummaryWidget(self)
                self.summary_widget.present()
                self.set_visible(False)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(apply)

        capture_for_widget(captured)
        return True

    def restore_main(self):
        self.widget_cycle += 1
        self.widget_capture_pending = False
        widget = self.summary_widget
        self.summary_widget = None
        state = self.saved_window_state
        self.saved_window_state = None
        if widget is not None:
            widget.dispose_widget()
        self.unminimize()
        self.present()
        if widget is not None:
            restore_after_widget(state, *self.opening_size)

    def on_first_map(self, *_):
        if not self.opening_applied:
            self.opening_applied = True
            open_floating(*self.opening_size)

    @staticmethod
    def card(parent, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("card")
        box.append(label(title, "section-title", xalign=0))
        parent.append(box)
        return box

    def setting_int(self, key, default, lower, upper):
        value = self.settings.get(key, default)
        return value if type(value) is int and lower <= value <= upper else default

    def add_spin(self, grid, column, title, key, default, lower, upper):
        grid.attach(label(title, "hint", xalign=0), column, 0, 1, 1)
        widget = Gtk.SpinButton.new_with_range(lower, upper, 1)
        widget.set_value(self.setting_int(key, default, lower, upper))
        widget.set_hexpand(True)
        widget.set_tooltip_text(title)
        grid.attach(widget, column, 1, 1, 1)
        return widget

    def load_settings(self):
        try:
            data = json.loads(self.settings_file.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self):
        data = dict(work=self.work.get_value_as_int(), rest=self.rest.get_value_as_int(), repetitions=self.repetitions.get_value_as_int(), budget=self.budget.get_value_as_int(), warning=self.warning.get_value_as_int(), sound=self.sound.get_active(), volume=self.volume.get_value())
        data.update(sound_folder=str(self.sound_library.directory), sound_selections=self.sound_selections,
                    countdown_enabled=self.countdown_enabled)
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, indent=2) + "\n")
            temporary.replace(self.settings_file)
        except OSError:
            self.status.set_text("Settings could not be saved. You can still use the timer.")

    def config_changed(self, *_):
        if getattr(self, "loading", False):
            return
        self.timer.configure(Config(self.work.get_value_as_int(), self.rest.get_value_as_int(), self.repetitions.get_value_as_int()), self.warning.get_value_as_int())
        self.countdown_cues.reset()
        self.save_settings()
        self.save_session()
        self.render()

    def alert_changed(self, *_):
        if not hasattr(self, "volume"):
            return
        self.timer.warning_seconds = self.warning.get_value_as_int()
        if not self.sound.get_active():
            self.stop_sound_preview()
        self.save_settings()
        self.save_session()

    def save_session(self, force=True):
        if self.initializing:
            return
        now_seconds = time.monotonic()
        if not force and now_seconds - self.last_checkpoint_seconds < 5:
            return
        self.last_checkpoint_seconds = now_seconds
        if self.session_store.save(self.timer):
            self.persistence_status.set_text("")
            return True
        else:
            self.persistence_status.set_text(self.session_store.error)
            return False

    def show_sound_settings(self, *_):
        if self.sound_dialog is None:
            self.sound_dialog = SoundSettings(self)
        self.sound_dialog.present(self)

    def stop_sound_preview(self):
        if self.sound_dialog:
            self.sound_dialog.stop_test()
        self.audio.stop()

    def play_sound(self, event):
        selected = self.sound_selections.get(event)
        sound = self.sound_library.resolve(selected, event)
        self.audio.play_choice(sound, self.volume.get_value(), 300 if event == "countdown" else None)
        if selected != sound.id:
            self.plan_result.set_text("A selected sound is missing. Playing the built-in sound instead.")

    def plan(self, *_):
        budget = self.budget.get_value_as_int()
        config = propose(budget)
        self.loading = True
        self.work.set_value(config.work_minutes)
        self.rest.set_value(config.rest_minutes)
        self.repetitions.set_value(config.repetitions)
        self.loading = False
        self.config_changed()
        spare = budget - config.total_minutes
        self.plan_result.set_text(f"{config.work_minutes} min focus + {config.rest_minutes} min rest × {config.repetitions} rounds. {spare} min spare. Applied to your rhythm.")

    def toggle_timer(self, *_):
        self.stop_sound_preview()
        if self.timer.running:
            self.handle_events(self.timer.pause())
        else:
            if self.timer.finished:
                self.timer.reset()
                self.countdown_cues.reset()
            self.countdown_cues.prime(self.timer)
            self.timer.start()
        self.update_inhibit()
        self.save_session()
        self.render()

    def reset_timer(self, *_):
        self.timer.reset()
        self.countdown_cues.reset()
        self.stop_sound_preview()
        self.update_inhibit()
        self.save_session()
        self.render()

    def update_inhibit(self):
        app = self.get_application()
        if self.timer.running and not self.inhibit_requested:
            # Keep an intentional focus session awake where supported by the shell.
            self.inhibit_requested = True
            self.inhibit_cookie = app.inhibit(self, Gtk.ApplicationInhibitFlags.SUSPEND | Gtk.ApplicationInhibitFlags.IDLE, "Pomodoro session in progress")
        elif not self.timer.running and self.inhibit_requested:
            if self.inhibit_cookie:
                app.uninhibit(self.inhibit_cookie)
            self.inhibit_cookie = 0
            self.inhibit_requested = False

    def tick(self):
        events = self.timer.tick()
        cue = self.countdown_cues.observe(self.timer)
        self.handle_events(events)
        if cue is not None and self.countdown_enabled and self.sound.get_active() and not any(event in events for event in ("phase", "complete")):
            if self.sound_dialog:
                self.sound_dialog.stop_test()
            self.play_sound("countdown")
        if events or self.timer.running:
            self.save_session(force=bool(events))
        self.update_inhibit()
        self.render()
        if self.audio.error and self.audio.error != self.audio_error_seen:
            self.audio_error_seen = self.audio.error
            self.plan_result.set_text(self.audio.error + " Visual reminders remain active.")
            self.plan_result.add_css_class("error")
        return GLib.SOURCE_CONTINUE

    def handle_events(self, events):
        if not events:
            return
        # Coalesce delayed transitions into a single current alert.
        event = "complete" if "complete" in events else "phase" if "phase" in events else "warning"
        if self.sound.get_active():
            if self.sound_dialog:
                self.sound_dialog.stop_test()
            self.play_sound(event)
        if event != "warning":
            title = "Session complete" if self.timer.finished else "Time to focus" if self.timer.is_work else "Time for a break"
            notification = Gio.Notification.new(title)
            notification.set_body("Nicely done. Your planned rounds are complete." if self.timer.finished else f"Round {self.timer.repetition} of {self.timer.config.repetitions}")
            self.get_application().send_notification("phase-change", notification)

    def render(self):
        timer = self.timer
        seconds = timer.seconds_left
        self.time_label.set_text(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self.phase_label.set_text("COMPLETE" if timer.finished else "FOCUS" if timer.is_work else "REST")
        self.round_label.set_text(f"Round {timer.repetition} of {timer.config.repetitions}")
        locked = timer.running or (not timer.finished and (timer.index > 0 or timer.remaining < timer.duration))
        self.start_button.set_label("Pause" if timer.running else "Start again" if timer.finished else "Resume" if locked else "Start focus")
        self.session_card.set_sensitive(not locked)
        self.planner_card.set_sensitive(not locked)
        self.remove_css_class("rest")
        self.remove_css_class("warning")
        if not timer.is_work:
            self.add_css_class("rest")
        if timer.finished:
            message = "All done. A little progress goes a long way."
        elif timer.running and timer.warning_seconds and seconds <= timer.warning_seconds:
            next_phase = "session complete" if timer.index == timer.config.repetitions * 2 - 1 else "rest" if timer.is_work else "focus"
            message = f"{next_phase.capitalize()} in {seconds} seconds…"
            self.add_css_class("warning")
        elif timer.running:
            message = "Stay with this moment." if timer.is_work else "Unclench your shoulders. Take a breath."
        elif locked:
            message = "Paused. Your time is waiting for you."
        else:
            message = "Ready when you are."
        self.status.set_text(message)
        config = timer.config
        self.summary.set_text(f"{config.work_minutes * config.repetitions} min focus  ·  {config.rest_minutes * config.repetitions} min rest  ·  {config.total_minutes} min total")
        elapsed = (timer.index // 2 * (config.work_minutes + config.rest_minutes) * 60
                   + (config.work_minutes * 60 if not timer.is_work else 0)
                   + timer.duration - timer.remaining)
        self.progress.set_fraction(1 if timer.finished else elapsed / (config.total_minutes * 60))
        self.ring.queue_draw()
        if self.summary_widget is not None:
            self.summary_widget.update()

    def draw_ring(self, _area, cr, width, height):
        x, y = width / 2, height / 2
        radius = min(width, height) / 2 - 25
        cr.set_line_width(1)
        for i in range(60):
            angle = i * math.tau / 60 - math.pi / 2
            length = 7 if i % 5 == 0 else 3
            cr.set_source_rgba(*rgb(self.palette.muted), 0.35)
            cr.move_to(x + (radius + 15) * math.cos(angle), y + (radius + 15) * math.sin(angle))
            cr.line_to(x + (radius + 15 + length) * math.cos(angle), y + (radius + 15 + length) * math.sin(angle))
            cr.stroke()
        cr.set_line_width(9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgb(*rgb(self.palette.border))
        cr.arc(x, y, radius, 0, math.tau)
        cr.stroke()
        if self.timer.progress > 0:
            cr.set_source_rgb(*rgb(self.palette.focus if self.timer.is_work else self.palette.rest))
            cr.arc(x, y, radius, -math.pi / 2, -math.pi / 2 + math.tau * self.timer.progress)
            cr.stroke()

    def on_close(self, *_):
        return not self.cleanup()

    def cleanup(self):
        # Persist before releasing inhibition and marking the in-memory timer
        # stopped, so a running session continues across a normal close.
        if not self.save_session():
            # Do not tear down the timer when its latest running/paused/reset
            # state could not replace the previous snapshot. Keep it available
            # for a retry, with the persistence error visible in the window.
            return False
        self.closed = True
        self.widget_cycle += 1
        self.widget_capture_pending = False
        if self.summary_widget is not None:
            self.summary_widget.dispose_widget()
            self.summary_widget = None
        self.timer.running = False
        self.update_inhibit()
        self.stop_sound_preview()
        if self.sound_dialog:
            self.sound_dialog.cancel_gallery()
            self.sound_dialog.close()
        GLib.source_remove(self.timeout_id)
        GLib.source_remove(self.theme_timeout_id)
        Gtk.StyleContext.remove_provider_for_display(self.get_display(), self.theme_provider)
        self.save_settings()
        return True


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.simplepomodoro.App")

    def do_activate(self):
        window = next((item for item in self.get_windows() if isinstance(item, Window)), None)
        if window is None:
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(ROOT / "assets"))
            window = Window(self)
        window.restore_main()


def main():
    Gtk.init_check()
    if Gdk.Display.get_default() is None:
        print("SimplePomodoro needs access to your desktop display. Run ./run.sh from a terminal in your graphical session.", file=sys.stderr)
        return 1
    return Application().run(sys.argv)
