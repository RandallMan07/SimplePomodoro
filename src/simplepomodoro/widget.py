"""Fixed arrow and fading summary layer surfaces sharing the main timer."""
from .layer_support import LAYER_LIBRARY
import gi
import cairo

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk
from .summary import timer_summary

LayerShell = None
if LAYER_LIBRARY is not None:
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        pass

FADE_DURATION_SECONDS = 0.16
LEAVE_GRACE_MS = 180
SUMMARY_GAP_PX = 6


def widget_available():
    return LayerShell is not None and LayerShell.is_supported()


def prepare_layer(window, owner, namespace, top_margin):
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_default_size(1, 1)
    window.add_css_class("pomodoro-widget")
    LayerShell.init_for_window(window)
    LayerShell.set_namespace(window, namespace)
    LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
    LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
    LayerShell.set_margin(window, LayerShell.Edge.TOP, top_margin)
    LayerShell.set_exclusive_zone(window, 0)
    LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.ON_DEMAND)
    if hasattr(LayerShell, "set_respect_close"):
        LayerShell.set_respect_close(window, True)
    surface = owner.get_surface()
    if surface is not None:
        LayerShell.set_monitor(window, owner.get_display().get_monitor_at_surface(surface))


class SummaryWidget(Gtk.Window):
    def __init__(self, owner):
        super().__init__(application=owner.get_application(), title="SimplePomodoro arrow")
        self.owner = owner
        self.pointer_windows = set()
        self.focus_windows = set()
        self.collapse_id = 0
        self.fade_id = 0
        self.expanded = False
        self.disposed = False
        prepare_layer(self, owner, "simplepomodoro-arrow", 0)
        self.connect("close-request", self.on_close)
        self.arrow = Gtk.Button(icon_name="pan-down-symbolic")
        self.arrow.add_css_class("summary-arrow")
        self.arrow.set_tooltip_text("SimplePomodoro · hover to show the timer")
        self.set_child(self.arrow)
        self.bar_window = Gtk.Window(application=owner.get_application(), title="SimplePomodoro summary")
        prepare_layer(self.bar_window, owner, "simplepomodoro-summary", 0)
        self.bar_window.set_opacity(0)
        LayerShell.set_keyboard_mode(self.bar_window, LayerShell.KeyboardMode.NONE)
        self.bar_window.connect("realize", lambda *_: self.set_bar_input(self.expanded))
        self.bar_window.connect("close-request", self.on_close)
        self.bar = Gtk.Box(spacing=12)
        self.bar.add_css_class("summary-bar")
        self.bar_window.set_child(self.bar)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.state_label = Gtk.Label(xalign=0)
        self.state_label.add_css_class("summary-state")
        self.detail_label = Gtk.Label(xalign=0)
        self.detail_label.add_css_class("hint")
        text.append(self.state_label)
        text.append(self.detail_label)
        self.bar.append(text)
        self.pause_button = Gtk.Button()
        self.pause_button.connect("clicked", owner.toggle_timer)
        self.bar.append(self.pause_button)
        self.open_button = Gtk.Button(icon_name="window-new-symbolic")
        self.open_button.set_tooltip_text("Open full timer")
        self.open_button.connect("clicked", lambda *_: owner.restore_main())
        self.bar.append(self.open_button)
        self.add_controllers(self, self.arrow, "arrow")
        self.add_controllers(self.bar_window, self.bar, "bar")
        self.connect("realize", self.on_arrow_realize)
        self.update()

    def on_arrow_realize(self, *_):
        # GtkWidget allocation can still be zero at map time. The surface layout
        # signal supplies the actual compositor-configured size in logical pixels.
        self.get_surface().connect("layout", self.on_arrow_layout)

    def on_arrow_layout(self, surface, _width, height):
        if self.disposed or height <= 0:
            return
        monitor = self.get_display().get_monitor_at_surface(surface)
        if monitor is not None and LayerShell.get_monitor(self.bar_window) != monitor:
            LayerShell.set_monitor(self.bar_window, monitor)
        summary_top_margin = height + SUMMARY_GAP_PX
        if LayerShell.get_margin(self.bar_window, LayerShell.Edge.TOP) != summary_top_margin:
            LayerShell.set_margin(self.bar_window, LayerShell.Edge.TOP, summary_top_margin)
        # Only map after the arrow has real geometry, so the summary starts
        # below it with a small gap. Both surfaces stay fixed during hover fades.
        if not self.bar_window.get_visible():
            self.bar_window.set_visible(True)
            self.set_bar_input(self.expanded)

    def add_controllers(self, window, root, name):
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self.pointer_enter(name))
        motion.connect("leave", lambda *_: self.pointer_leave(name))
        root.add_controller(motion)
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda *_: self.focus_changed(window, name))
        focus.connect("leave", lambda *_: self.focus_leave(name))
        root.add_controller(focus)
        window.connect("notify::focus-visible", lambda *_: self.focus_changed(window, name))
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed, name)
        root.add_controller(keys)

    def set_bar_input(self, enabled):
        surface = self.bar_window.get_surface()
        if surface is not None:
            surface.set_input_region(None if enabled else cairo.Region())
        LayerShell.set_keyboard_mode(self.bar_window, LayerShell.KeyboardMode.ON_DEMAND if enabled else LayerShell.KeyboardMode.NONE)

    def set_expanded(self, expanded):
        if self.disposed or expanded == self.expanded:
            return
        self.expanded = expanded
        self.arrow.set_icon_name("pan-up-symbolic" if expanded else "pan-down-symbolic")
        if expanded:
            self.set_bar_input(True)
        else:
            # Do not trap the cursor behind a fading, inactive rectangle.
            self.set_bar_input(False)
        if self.fade_id:
            self.bar_window.remove_tick_callback(self.fade_id)
        self.fade_start_opacity = self.bar_window.get_opacity()
        self.fade_target_opacity = 1.0 if expanded else 0.0
        self.fade_started_us = None
        self.fade_id = self.bar_window.add_tick_callback(self.fade_frame)

    def fade_frame(self, _widget, clock):
        now_us = clock.get_frame_time()
        if self.fade_started_us is None:
            self.fade_started_us = now_us
        fraction = min(1.0, (now_us - self.fade_started_us) / (FADE_DURATION_SECONDS * 1000000))
        eased = fraction * fraction * (3 - 2 * fraction)
        self.bar_window.set_opacity(self.fade_start_opacity + (self.fade_target_opacity - self.fade_start_opacity) * eased)
        if fraction >= 1:
            self.fade_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def cancel_collapse(self):
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0

    def pointer_enter(self, name="arrow"):
        self.pointer_windows.add(name)
        self.cancel_collapse()
        self.set_expanded(True)

    def pointer_leave(self, name="arrow"):
        self.pointer_windows.discard(name)
        self.schedule_collapse()

    def focus_changed(self, window, name):
        # Mouse-assigned focus cannot hold the bar open after leaving it.
        if window.get_focus_visible() and window.get_focus() is not None:
            self.focus_windows.add(name)
            self.cancel_collapse()
            self.set_expanded(True)
        else:
            self.focus_leave(name)

    def focus_leave(self, name):
        self.focus_windows.discard(name)
        self.schedule_collapse()

    def schedule_collapse(self):
        self.cancel_collapse()
        self.collapse_id = GLib.timeout_add(LEAVE_GRACE_MS, self.collapse)

    def collapse(self):
        self.collapse_id = 0
        if not (self.pointer_windows or self.focus_windows):
            self.set_expanded(False)
        return GLib.SOURCE_REMOVE

    def key_pressed(self, _controller, keyval, _keycode, _state, name):
        if keyval == Gdk.KEY_Escape:
            self.owner.restore_main()
            return True
        if name == "arrow" and keyval in (Gdk.KEY_Down, Gdk.KEY_Tab, Gdk.KEY_Return, Gdk.KEY_space):
            self.set_expanded(True)
            self.bar_window.present()
            self.bar_window.set_focus_visible(True)
            self.pause_button.grab_focus()
            return True
        return False

    def update(self):
        summary = timer_summary(self.owner.timer)
        self.state_label.set_text(f"{summary.phase} · {summary.clock}")
        self.detail_label.set_text(summary.detail)
        self.pause_button.set_label(summary.action)
        for window in (self, self.bar_window):
            window.remove_css_class("rest")
            if not self.owner.timer.is_work:
                window.add_css_class("rest")
        self.arrow.set_tooltip_text(f"{summary.phase} · {summary.clock} · {summary.detail}\nHover to show the timer")

    def on_close(self, *_):
        self.owner.restore_main()
        return True

    def dispose_widget(self):
        self.disposed = True
        self.cancel_collapse()
        if self.fade_id:
            self.bar_window.remove_tick_callback(self.fade_id)
            self.fade_id = 0
        self.bar_window.destroy()
        self.destroy()
