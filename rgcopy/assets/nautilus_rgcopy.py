# Installed by `rgcopy integrate --takeover`.
#
# Makes Ctrl+V in Nautilus paste copied or cut files through RGCopy, the way TeraCopy takes over
# Explorer on Windows. Nautilus keeps everything else:
#   - text fields (rename, location bar, search) paste text as usual;
#   - a clipboard without files (an image, some text) is pasted by Nautilus itself;
#   - Edit > Paste in the menus still uses Nautilus' own copy.
# Remove it with `rgcopy integrate --uninstall`.

import os
import weakref
from urllib.parse import quote

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, GObject, Gtk, Nautilus  # noqa: E402

SCRIPT_NAME = "Paste with RGCopy"
FILE_TARGETS = ("x-special/gnome-copied-files", "text/uri-list")
# Nautilus' own Ctrl+V action, taken away from Ctrl+V while this extension is loaded
NATIVE_PASTE = "view.paste_accel"


def _script_action() -> str:
    """The action Nautilus creates for our script: "script_" + the escaped URI of the file."""

    path = os.path.join(GLib.get_user_data_dir(), "nautilus", "scripts", SCRIPT_NAME)
    return "view.script_" + quote(Gio.File.new_for_path(path).get_uri(), safe="")


def _has_files(widget: Gtk.Widget) -> bool:
    formats = widget.get_clipboard().get_formats()
    return any(formats.contain_mime_type(target) for target in FILE_TARGETS)


def _typing(window: Gtk.Window) -> bool:
    focus = window.get_focus()
    while focus is not None:
        if isinstance(focus, (Gtk.Editable, Gtk.Text, Gtk.TextView)):
            return True
        focus = focus.get_parent()
    return False


def _on_paste(window: Gtk.Window, _args: GLib.Variant | None) -> bool:
    if _typing(window):
        return False  # let the text field paste
    if _has_files(window) and window.activate_action(_script_action(), None):
        return True
    return window.activate_action("view.paste", None)


class RGCopyPaste(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self) -> None:
        super().__init__()
        self._windows: weakref.WeakSet[Gtk.Window] = weakref.WeakSet()
        # The application and its windows appear after the extensions load
        GLib.timeout_add(1000, self._attach)

    def _attach(self) -> bool:
        app = Gtk.Application.get_default()
        if app is None:
            return True
        accels = [a for a in app.get_accels_for_action(NATIVE_PASTE) if a != "<Control>v"]
        if accels != app.get_accels_for_action(NATIVE_PASTE):
            app.set_accels_for_action(NATIVE_PASTE, accels)
        for window in app.get_windows():
            if window in self._windows:
                continue
            self._windows.add(window)
            controller = Gtk.ShortcutController()
            controller.set_name("rgcopy-paste")
            controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            controller.add_shortcut(
                Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string("<Control>v"),
                    Gtk.CallbackAction.new(_on_paste),
                )
            )
            window.add_controller(controller)
        # New windows keep coming: check again now and then
        return True

    def get_background_items(self, *_args: object) -> list[Nautilus.MenuItem]:
        return []
