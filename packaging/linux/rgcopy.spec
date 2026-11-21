# PyInstaller spec: RGCopy with its own Python, its dependencies and a Qt web view.
# Build with `pyinstaller packaging/linux/rgcopy.spec` after `pip install ".[desktop]" pyinstaller`.
import os
import re
import subprocess

import rgcopy
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Libraries every desktop Linux has, or that must match the system: the GPU drivers load the
# system C++ runtime, GTK and friends need the system GLib, NSS and ALSA load plugins from system
# paths, fontconfig reads the system configuration, and OpenSSL gets its security updates from the
# distribution. Bundling older copies of them breaks on newer distributions.
SYSTEM_LIBRARIES = re.compile(
    r"^lib("
    r"stdc\+\+|gcc_s|GL|GLX|GLdispatch|OpenGL|EGL|gbm|drm|udev|systemd|"
    r"X11|X11-xcb|Xau|Xdmcp|Xext|Xrender|Xfixes|Xdamage|Xcomposite|Xrandr|Xtst|Xi|"
    r"xcb|xcb-dri[23]|xcb-glx|xcb-present|xcb-sync|xshmfence|"
    r"glib-2\.0|gobject-2\.0|gio-2\.0|gmodule-2\.0|gthread-2\.0|"
    r"asound|fontconfig|freetype|harfbuzz|fribidi|png16|expat|z|uuid|dbus-1|"
    r"nss3|nssutil3|smime3|ssl3|nspr4|plc4|plds4|softokn3|freebl3|freeblpriv3|nssckbi|nssdbm3|ssl|crypto|"
    r"wayland-client|wayland-cursor|wayland-egl|wayland-server"
    r")\.so(\.|$)"
)
# Qt parts the web view never uses: QML modules, the NSS modules (the system NSS brings its own)
# and the developer tools
DROPPED = re.compile(r"^(nss/|PyQt6/Qt6/qml/|PyQt6/Qt6/resources/qtwebengine_devtools_resources\.pak$)")
# Qt and Chromium translations for the languages of the interface
TRANSLATION = re.compile(r"(_es|_en)\.qm$|qtwebengine_locales/(en-US|es|es-419)\.pak$")
# Qt plugins that matter on a desktop: X11 and Wayland, input methods, the portal file dialogs,
# OpenGL integration and the image formats the interface shows
PLUGINS = re.compile(
    r"^PyQt6/Qt6/plugins/("
    r"platforms/libq(xcb|wayland|offscreen)\.so|platforminputcontexts/|platformthemes/libqxdgdesktopportal\.so|"
    r"xcbglintegrations/|wayland-[a-z-]+/|imageformats/libq(svg|ico|gif|jpeg|webp)\.so|iconengines/"
    r")"
)

# The Nautilus extension is a .py file that `rgcopy integrate` copies out, not code the app runs
NAUTILUS_EXTENSION = os.path.join(os.path.dirname(rgcopy.__file__), "assets", "nautilus_rgcopy.py")

a = Analysis(
    ["launcher.py"],
    datas=collect_data_files("rgcopy")
    + [(NAUTILUS_EXTENSION, "rgcopy/assets")]
    + collect_data_files("webview"),
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("rgcopy") + ["webview.platforms.qt"],
    excludes=[
        # Toolkits pywebview can use elsewhere; this build ships Qt
        "gi",
        "tkinter",
        "PyQt5",
        "PySide2",
        "PySide6",
        "webview.platforms.android",
        "webview.platforms.cef",
        "webview.platforms.cocoa",
        "webview.platforms.edgechromium",
        "webview.platforms.gtk",
        "webview.platforms.mshtml",
        "webview.platforms.winforms",
        # Optional speedups of uvicorn a local app does not need
        "uvloop",
        "watchfiles",
    ],
    noarchive=False,
)


def _wanted(dest):
    if DROPPED.match(dest) or SYSTEM_LIBRARIES.match(os.path.basename(dest)):
        return False
    if dest.startswith("PyQt6/Qt6/translations/"):
        return bool(TRANSLATION.search(dest))
    if dest.startswith("PyQt6/Qt6/plugins/"):
        return bool(PLUGINS.match(dest))
    return True


def _needed(path):
    out = subprocess.run(["readelf", "-d", path], capture_output=True, text=True, check=False).stdout
    return set(re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out))


a.datas = [entry for entry in a.datas if _wanted(entry[0])]
binaries = [entry for entry in a.binaries if _wanted(entry[0])]

# Keep a library only when something that runs needs it: the Python extensions and library, the
# Qt plugins and the web engine process, and whatever they link to
by_name = {}
for entry in binaries:
    by_name.setdefault(os.path.basename(entry[0]), []).append(entry)
todo = [
    entry
    for entry in binaries
    if entry[2] == "EXTENSION"
    or os.path.basename(entry[0]).startswith("libpython")
    or entry[0].startswith(("PyQt6/Qt6/plugins/", "PyQt6/Qt6/libexec/"))
]
kept = {os.path.basename(entry[0]) for entry in todo}
while todo:
    dest, src, kind = todo.pop()
    if kind == "SYMLINK":
        continue
    for name in _needed(src) - kept:
        if name in by_name:
            kept.add(name)
            todo.extend(by_name[name])
a.binaries = [entry for entry in binaries if os.path.basename(entry[0]) in kept]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="rgcopy", strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="rgcopy")
