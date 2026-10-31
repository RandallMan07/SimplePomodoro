"""Load GTK4 Layer Shell before GTK/Wayland, as required by its Python API.

The optional dependency is only used for the desktop summary surface.
https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md
"""
from ctypes import CDLL, RTLD_GLOBAL

try:
    LAYER_LIBRARY = CDLL("libgtk4-layer-shell.so.0", mode=RTLD_GLOBAL)
except OSError:
    LAYER_LIBRARY = None
