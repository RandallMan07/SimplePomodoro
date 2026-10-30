"""A top-center Wayland layer surface sharing the main window's timer."""
from .layer_support import LAYER_LIBRARY
import gi

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


def widget_available():
    return LayerShell is not None and LayerShell.is_supported()


class SummaryWidget(Gtk.Window):
    def __init__(self, owner):
        super().__init__(application=owner.get_application(), title="SimplePomodoro summary")
        self.owner = owner
        self.pointer_inside = False
        self.focus_inside = False
        self.pinned = False
        self.collapse_id = 0
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(1, 1)
        self.add_css_class("pomodoro-widget")
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "simplepomodoro-summary")
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, 6)
        LayerShell.set_exclusive_zone(self, 0)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
        if hasattr(LayerShell, "set_respect_close"):
            LayerShell.set_respect_close(self, True)
        surface = owner.get_surface()
        if surface is not None:
            LayerShell.set_monitor(self, owner.get_display().get_monitor_at_surface(surface))
        self.connect("close-request", self.on_close)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)
        self.arrow = Gtk.Button(icon_name="pan-down-symbolic", halign=Gtk.Align.CENTER)
        self.arrow.add_css_class("summary-arrow")
        self.arrow.set_tooltip_text("SimplePomodoro · hover or click to show the timer")
        self.arrow.connect("clicked", self.toggle_pinned)
        root.append(self.arrow)
        self.bar = Gtk.Box(spacing=12, margin_top=4)
        self.bar.add_css_class("summary-bar")
        self.bar.set_visible(False)
        root.append(self.bar)
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
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self.pointer_enter)
        motion.connect("leave", self.pointer_leave)
        root.add_controller(motion)
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", self.focus_enter)
        focus.connect("leave", self.focus_leave)
        root.add_controller(focus)
        self.connect("notify::focus-visible", self.focus_visibility_changed)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed)
        root.add_controller(keys)
        self.update()

    def set_expanded(self, expanded):
        self.bar.set_visible(expanded)
        self.arrow.set_icon_name("pan-up-symbolic" if expanded else "pan-down-symbolic")
        self.set_default_size(1, 1)

    def toggle_pinned(self, *_):
        self.pinned = not self.pinned
        self.set_expanded(self.pinned or self.pointer_inside or self.focus_inside)

    def cancel_collapse(self):
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0

    def pointer_enter(self, *_):
        self.pointer_inside = True
        self.cancel_collapse()
        self.set_expanded(True)

    def pointer_leave(self, *_):
        self.pointer_inside = False
        self.schedule_collapse()

    def focus_enter(self, *_):
        # GTK assigns an initial focus widget while mapping. Expand for keyboard
        # navigation, not that automatic assignment. Pointer/click have own paths.
        self.focus_inside = self.get_focus_visible()
        if self.focus_inside:
            self.cancel_collapse()
            self.set_expanded(True)

    def focus_visibility_changed(self, *_):
        self.focus_inside = self.get_focus_visible() and self.get_focus() is not None
        if self.focus_inside:
            self.cancel_collapse()
            self.set_expanded(True)
        else:
            self.schedule_collapse()

    def focus_leave(self, *_):
        self.focus_inside = False
        self.schedule_collapse()

    def schedule_collapse(self):
        self.cancel_collapse()
        self.collapse_id = GLib.timeout_add(250, self.collapse)

    def collapse(self):
        self.collapse_id = 0
        if not (self.pointer_inside or self.focus_inside or self.pinned):
            self.set_expanded(False)
        return GLib.SOURCE_REMOVE

    def key_pressed(self, _controller, keyval, *_):
        if keyval == Gdk.KEY_Escape:
            self.owner.restore_main()
            return True
        return False

    def update(self):
        summary = timer_summary(self.owner.timer)
        self.state_label.set_text(f"{summary.phase} · {summary.clock}")
        self.detail_label.set_text(summary.detail)
        self.pause_button.set_label(summary.action)
        self.remove_css_class("rest")
        if not self.owner.timer.is_work:
            self.add_css_class("rest")
        self.arrow.set_tooltip_text(f"{summary.phase} · {summary.clock} · {summary.detail}\nHover or click to show the timer")

    def on_close(self, *_):
        self.owner.restore_main()
        return True

    def dispose_widget(self):
        self.cancel_collapse()
        self.destroy()
