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
LAYOUT_SETTLE_SECONDS = 0.10


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
        self.settle_id = 0
        self.persistent_reminder = False
        self.focus_reminder_controls = False
        self.transitioning = False
        self.transition_generation = 0
        self.require_fresh_hover = False
        self.arrow_height = 0
        self.arrow_layout_surface = None
        self.expanded = False
        self.disposed = False
        prepare_layer(self, owner, "simplepomodoro-arrow", 0)
        self.connect("close-request", self.on_close)
        self.arrow = Gtk.Button(icon_name="pan-down-symbolic")
        self.arrow.add_css_class("summary-arrow")
        self.arrow.set_tooltip_text("SimplePomodoro · hover to show the timer")
        self.arrow.connect("clicked", self.enter_persistent)
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
        self.minimize_button = Gtk.Button(icon_name="window-minimize-symbolic")
        self.minimize_button.set_tooltip_text("Return to the timer arrow")
        self.minimize_button.set_visible(False)
        self.minimize_button.connect("clicked", self.return_to_hover)
        self.bar.append(self.minimize_button)
        self.add_controllers(self, self.arrow, "arrow")
        self.add_controllers(self.bar_window, self.bar, "bar")
        self.connect("realize", self.on_arrow_realize)
        self.update()

    def on_arrow_realize(self, *_):
        # GtkWidget allocation can still be zero at map time. The surface layout
        # signal supplies the actual compositor-configured size in logical pixels.
        surface = self.get_surface()
        if surface != self.arrow_layout_surface:
            self.arrow_layout_surface = surface
            surface.connect("layout", self.on_arrow_layout)

    def on_arrow_layout(self, surface, _width, height):
        if self.disposed or height <= 0:
            return
        monitor = self.get_display().get_monitor_at_surface(surface)
        if monitor is not None and LayerShell.get_monitor(self.bar_window) != monitor:
            LayerShell.set_monitor(self.bar_window, monitor)
        self.arrow_height = height
        summary_top_margin = SUMMARY_GAP_PX if self.persistent_reminder else height + SUMMARY_GAP_PX
        can_reposition = not self.transitioning or self.bar_window.get_opacity() == 0
        if can_reposition and LayerShell.get_margin(self.bar_window, LayerShell.Edge.TOP) != summary_top_margin:
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
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed, name)
        root.add_controller(keys)

    def set_bar_input(self, enabled):
        surface = self.bar_window.get_surface()
        if surface is not None:
            surface.set_input_region(None if enabled else cairo.Region())
        LayerShell.set_keyboard_mode(self.bar_window, LayerShell.KeyboardMode.ON_DEMAND if enabled else LayerShell.KeyboardMode.NONE)

    def set_arrow_input(self, enabled):
        surface = self.get_surface()
        if surface is not None:
            surface.set_input_region(None if enabled else cairo.Region())
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND if enabled else LayerShell.KeyboardMode.NONE)

    def set_expanded(self, expanded):
        if self.disposed or self.transitioning or self.persistent_reminder or expanded == self.expanded:
            return
        self.expanded = expanded
        self.arrow.set_icon_name("pan-up-symbolic" if expanded else "pan-down-symbolic")
        self.set_bar_input(expanded)
        self.fade_to(1.0 if expanded else 0.0)

    def fade_to(self, opacity, complete=None):
        if self.fade_id:
            self.bar_window.remove_tick_callback(self.fade_id)
        self.fade_complete = complete
        self.fade_start_opacity = self.bar_window.get_opacity()
        self.fade_target_opacity = opacity
        self.fade_started_us = None
        self.fade_id = self.bar_window.add_tick_callback(self.fade_frame)

    def enter_persistent(self, *_, keyboard=False):
        if self.disposed or self.persistent_reminder or self.transitioning:
            return
        self.persistent_reminder = True
        self.focus_reminder_controls = keyboard
        self.begin_mode_transition()
        self.set_arrow_input(False)
        self.set_focus_visible(False)
        # Top-level opacity is not a reliable hide for native layer surfaces.
        # Unmap the arrow once per mode change; retain its configured height.
        self.set_visible(False)
        generation = self.transition_generation
        self.fade_to(0.0, lambda: self.reposition_mode(generation))

    def return_to_hover(self, *_):
        if self.disposed or not self.persistent_reminder or self.transitioning:
            return
        self.persistent_reminder = False
        self.begin_mode_transition()
        self.bar_window.set_focus_visible(False)
        generation = self.transition_generation
        self.fade_to(0.0, lambda: self.reposition_mode(generation))

    def begin_mode_transition(self):
        self.transition_generation += 1
        self.transitioning = True
        self.cancel_collapse()
        self.pointer_windows.clear()
        self.focus_windows.clear()
        self.set_bar_input(False)

    def reposition_mode(self, generation):
        if self.disposed or generation != self.transition_generation:
            return
        # Resize/reanchor only while completely transparent, then wait for stable
        # allocations before fading in. The summary itself is never remapped.
        self.minimize_button.set_visible(self.persistent_reminder)
        margin = SUMMARY_GAP_PX if self.persistent_reminder else self.arrow_height + SUMMARY_GAP_PX
        LayerShell.set_margin(self.bar_window, LayerShell.Edge.TOP, margin)
        if not self.persistent_reminder:
            self.expanded = False
            self.arrow.set_icon_name("pan-down-symbolic")
            self.set_visible(True)
            self.set_arrow_input(True)
        self.settle_started_us = None
        self.settle_size = None
        self.settle_stable_frames = 0
        self.settle_id = self.bar_window.add_tick_callback(self.settle_layout, generation)

    def settle_layout(self, _widget, clock, generation):
        if self.disposed or generation != self.transition_generation:
            self.settle_id = 0
            return GLib.SOURCE_REMOVE
        now_us = clock.get_frame_time()
        if self.settle_started_us is None:
            self.settle_started_us = now_us
        size = (self.bar_window.get_width(), self.bar_window.get_height())
        self.settle_stable_frames = self.settle_stable_frames + 1 if size == self.settle_size else 0
        self.settle_size = size
        if min(size) <= 0 or self.settle_stable_frames < 2 or now_us - self.settle_started_us < LAYOUT_SETTLE_SECONDS * 1000000:
            return GLib.SOURCE_CONTINUE
        self.settle_id = 0
        self.transitioning = False
        if self.persistent_reminder:
            self.expanded = True
            self.set_bar_input(True)
            if self.focus_reminder_controls:
                self.bar_window.present()
                self.bar_window.set_focus_visible(True)
                self.pause_button.grab_focus()
            self.fade_to(1.0)
        else:
            # If revealing the arrow put it under the cursor, require leaving
            # it first; an ordinary later hover still opens it immediately.
            self.require_fresh_hover = "arrow" in self.pointer_windows
            self.pointer_windows.clear()
            self.focus_windows.clear()
        return GLib.SOURCE_REMOVE

    def fade_frame(self, _widget, clock):
        if self.disposed:
            self.fade_id = 0
            return GLib.SOURCE_REMOVE
        now_us = clock.get_frame_time()
        if self.fade_started_us is None:
            self.fade_started_us = now_us
        fraction = min(1.0, (now_us - self.fade_started_us) / (FADE_DURATION_SECONDS * 1000000))
        eased = fraction * fraction * (3 - 2 * fraction)
        self.bar_window.set_opacity(self.fade_start_opacity + (self.fade_target_opacity - self.fade_start_opacity) * eased)
        if fraction >= 1:
            self.fade_id = 0
            complete = self.fade_complete
            self.fade_complete = None
            if complete is not None:
                complete()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def cancel_collapse(self):
        if self.collapse_id:
            GLib.source_remove(self.collapse_id)
            self.collapse_id = 0

    def pointer_enter(self, name="arrow"):
        self.pointer_windows.add(name)
        if self.transitioning or self.persistent_reminder or self.require_fresh_hover:
            return
        self.cancel_collapse()
        self.set_expanded(True)

    def pointer_leave(self, name="arrow"):
        self.pointer_windows.discard(name)
        if name == "arrow":
            self.require_fresh_hover = False
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
        if self.transitioning or self.persistent_reminder:
            return
        self.collapse_id = GLib.timeout_add(LEAVE_GRACE_MS, self.collapse)

    def collapse(self):
        self.collapse_id = 0
        if not self.persistent_reminder and not self.transitioning and not (self.pointer_windows or self.focus_windows):
            self.set_expanded(False)
        return GLib.SOURCE_REMOVE

    def key_pressed(self, _controller, keyval, _keycode, _state, name):
        if keyval == Gdk.KEY_Escape:
            self.owner.restore_main()
            return True
        if name == "arrow" and keyval in (Gdk.KEY_Return, Gdk.KEY_space):
            self.enter_persistent(keyboard=True)
            return True
        if name == "arrow" and keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
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
        self.transition_generation += 1
        self.cancel_collapse()
        if self.settle_id:
            self.bar_window.remove_tick_callback(self.settle_id)
            self.settle_id = 0
        if self.fade_id:
            self.bar_window.remove_tick_callback(self.fade_id)
            self.fade_id = 0
        self.bar_window.destroy()
        self.destroy()
