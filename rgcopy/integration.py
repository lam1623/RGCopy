"""Hook RGCopy into the desktop: menu entry and "Paste with RGCopy" in the file managers."""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from .clipboard import uri_to_path

APP_ID = "io.github.lam1623.rgcopy"
SCRIPT_NAME = "Paste with RGCopy"
# Always available next to the file manager's own paste; with the takeover Ctrl+V uses RGCopy too
DEFAULT_ACCEL = "<Control><Shift>v"
MARKER = "# Installed by `rgcopy integrate`"
# Nautilus extension that gives Ctrl+V to RGCopy (needs nautilus-python, `python3-nautilus`)
NAUTILUS_EXTENSION = "rgcopy_paste.py"
# GtkAccelMap action of the file manager's own Paste (Nemo and Caja)
NATIVE_PASTE_PATH = "<Actions>/DirViewActions/Paste"


@dataclass(frozen=True)
class FileManager:
    name: str
    scripts_dir: Path
    # Prefix of the environment variables the file manager gives its scripts
    env_prefix: str


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def file_managers() -> list[FileManager]:
    return [
        FileManager("nautilus", _data_home() / "nautilus" / "scripts", "NAUTILUS"),
        FileManager("nemo", _data_home() / "nemo" / "scripts", "NEMO"),
        FileManager("caja", _config_home() / "caja" / "scripts", "CAJA"),
    ]


def destination_from_env(env: dict[str, str] | None = None) -> str | None:
    """The folder a file manager script was run in: the one folder selected, else the open one."""

    env = dict(os.environ if env is None else env)
    for manager in file_managers():
        prefix = manager.env_prefix
        current = env.get(f"{prefix}_SCRIPT_CURRENT_URI")
        if current is None:
            continue
        selected = [u for u in env.get(f"{prefix}_SCRIPT_SELECTED_URIS", "").splitlines() if u.strip()]
        if len(selected) == 1:
            path = uri_to_path(selected[0])
            if path and Path(path).is_dir():
                return path
        return uri_to_path(current)
    return None


def launcher_command() -> list[str]:
    """How to start this very RGCopy from a desktop file or a script."""

    found = shutil.which("rgcopy")
    if found:
        return [found]
    argv0 = Path(sys.argv[0])
    if argv0.name == "rgcopy" and argv0.exists():
        return [str(argv0.resolve())]
    return [sys.executable, "-m", "rgcopy"]


def _write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, "utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _script() -> str:
    command = shlex.join([*launcher_command(), "paste"])
    return (
        f"#!/bin/sh\n{MARKER}\n"
        "# Pastes the copied or cut files into this folder with RGCopy\n"
        f'exec {command} "$@"\n'
    )


def _set_accel(accel: str) -> Path:
    """Nautilus 3.30+ reads script shortcuts from ``scripts-accels``."""

    path = _config_home() / "nautilus" / "scripts-accels"
    lines = path.read_text("utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.rstrip().endswith(SCRIPT_NAME)]
    lines.append(f"{accel} {SCRIPT_NAME}")
    _write(path, "\n".join(lines) + "\n")
    return path


def _accel_map_files() -> dict[str, Path]:
    """GtkAccelMap files of the file managers that let any action be rebound (Nemo, Caja)."""

    return {
        "nemo": Path.home() / ".gnome2" / "accels" / "nemo",
        "caja": _config_home() / "caja" / "accels",
    }


def script_accel_path(script: Path) -> str:
    """Accel path Nemo and Caja give a script: its URI with "/" written as "\\s"."""

    uri = "file://" + quote(str(script))
    return "<Actions>/ScriptsGroup/script_" + uri.replace("\\", "\\\\").replace("/", "\\s")


def _accel_line(path: str, accel: str) -> str:
    # The accel map file escapes backslashes once more
    escaped = path.replace("\\", "\\\\")
    return f'(gtk_accel_path "{escaped}" "{accel}")'


def _rewrite_accel_map(path: Path, lines: list[str]) -> None:
    """Drop RGCopy's previous lines and the Paste binding, then append ``lines``."""

    current = path.read_text("utf-8").splitlines() if path.exists() else []
    kept = [
        line
        for line in current
        if SCRIPT_NAME.replace(" ", "%20") not in line and f'"{NATIVE_PASTE_PATH}"' not in line
    ]
    _write(path, "\n".join([*kept, *lines]) + "\n")


def _nautilus_python_available() -> bool:
    return any(Path(p).exists() for p in _glob_nautilus_python())


def _glob_nautilus_python() -> list[str]:
    import glob

    return glob.glob("/usr/lib*/**/nautilus/extensions-4/libnautilus-python.so", recursive=True)


def quit_file_managers(names: list[str]) -> list[str]:
    """Close the running file managers: Nemo and Caja save their shortcuts on exit (and would
    overwrite ours), and Nautilus only loads extensions at startup. Returns the ones closed."""

    closed = []
    for name in names:
        if not shutil.which(name) or not shutil.which("pgrep"):
            continue
        running = subprocess.run(
            ["pgrep", "-x", "-u", str(os.getuid()), name], capture_output=True, check=False
        )
        if running.returncode == 0:
            subprocess.run([name, "-q"], capture_output=True, check=False, timeout=15)
            closed.append(name)
    if closed:
        time.sleep(1)
    return closed


def take_over_paste(managers: list[FileManager]) -> tuple[list[Path], list[str]]:
    """Make Ctrl+V paste through RGCopy, like TeraCopy on Windows. Returns (files, warnings)."""

    written: list[Path] = []
    warnings: list[str] = []
    accel_maps = _accel_map_files()
    for manager in managers:
        script = manager.scripts_dir / SCRIPT_NAME
        if manager.name == "nautilus":
            extension = _data_home() / "nautilus-python" / "extensions" / NAUTILUS_EXTENSION
            extension.parent.mkdir(parents=True, exist_ok=True)
            source = resources.files("rgcopy.assets").joinpath("nautilus_rgcopy.py")
            extension.write_bytes(source.read_bytes())
            written.append(extension)
            if not _nautilus_python_available():
                warnings.append(
                    "Ctrl+V in Nautilus needs nautilus-python: sudo apt install python3-nautilus "
                    "(Fedora: nautilus-python, Arch: python-nautilus). Ctrl+Shift+V works meanwhile."
                )
        elif manager.name in accel_maps:
            accel_map = accel_maps[manager.name]
            _rewrite_accel_map(
                accel_map,
                [_accel_line(NATIVE_PASTE_PATH, ""), _accel_line(script_accel_path(script), "<Primary>v")],
            )
            written.append(accel_map)
    return written, warnings


def _desktop_entry() -> str:
    exec_line = shlex.join(launcher_command())
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=RGCopy\n"
        "GenericName=File copy queue\n"
        "GenericName[es]=Cola de copias de archivos\n"
        "Comment=Copy and move files with rsync: pause, resume and see the progress\n"
        "Comment[es]=Copia y mueve archivos con rsync: pausa, reanuda y sigue el progreso\n"
        f"Exec={exec_line}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Utility;FileTools;System;\n"
        "Keywords=copy;move;rsync;paste;transfer;copiar;mover;pegar;\n"
        "StartupNotify=true\n"
    )


def _dolphin_menu() -> str:
    exec_line = shlex.join([*launcher_command(), "paste"])
    return (
        "[Desktop Entry]\n"
        "Type=Service\n"
        "MimeType=inode/directory;\n"
        "Actions=rgcopyPaste;\n"
        "X-KDE-ServiceTypes=KonqPopupMenu/Plugin\n\n"
        "[Desktop Action rgcopyPaste]\n"
        f"Name={SCRIPT_NAME}\n"
        "Name[es]=Pegar con RGCopy\n"
        f"Icon={APP_ID}\n"
        f"Exec={exec_line} %f\n"
    )


def install(accel: str | None = DEFAULT_ACCEL, *, takeover: bool = True) -> tuple[list[Path], list[str]]:
    """Menu entry, icon and "Paste with RGCopy"; ``takeover`` also gives it Ctrl+V."""

    written: list[Path] = []
    icon = _data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"
    icon.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(resources.files("rgcopy.assets").joinpath("rgcopy.svg").read_bytes())
    written.append(icon)
    entry = _data_home() / "applications" / f"{APP_ID}.desktop"
    _write(entry, _desktop_entry())
    written.append(entry)
    installed: list[FileManager] = []
    for manager in file_managers():
        # Only for file managers that are installed (or were set up before)
        if shutil.which(manager.name) or manager.scripts_dir.is_dir():
            script = manager.scripts_dir / SCRIPT_NAME
            _write(script, _script(), executable=True)
            written.append(script)
            installed.append(manager)
            if manager.name == "nautilus" and accel:
                written.append(_set_accel(accel))
    if shutil.which("dolphin") or (_data_home() / "kio" / "servicemenus").is_dir():
        menu = _data_home() / "kio" / "servicemenus" / "rgcopy-paste.desktop"
        _write(menu, _dolphin_menu(), executable=True)
        written.append(menu)
    warnings: list[str] = []
    if takeover:
        files, warnings = take_over_paste(installed)
        written += files
    return written, warnings


def uninstall() -> list[Path]:
    removed: list[Path] = []
    candidates = [
        _data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
        _data_home() / "applications" / f"{APP_ID}.desktop",
        _data_home() / "kio" / "servicemenus" / "rgcopy-paste.desktop",
        _data_home() / "nautilus-python" / "extensions" / NAUTILUS_EXTENSION,
        *(m.scripts_dir / SCRIPT_NAME for m in file_managers()),
    ]
    for path in candidates:
        if path.exists():
            path.unlink()
            removed.append(path)
    accels = _config_home() / "nautilus" / "scripts-accels"
    if accels.exists():
        lines = [line for line in accels.read_text("utf-8").splitlines() if not line.endswith(SCRIPT_NAME)]
        accels.write_text("\n".join(lines) + ("\n" if lines else ""), "utf-8")
    # Gives Paste its default Ctrl+V back in Nemo and Caja
    for accel_map in _accel_map_files().values():
        if accel_map.exists() and SCRIPT_NAME.replace(" ", "%20") in accel_map.read_text("utf-8"):
            _rewrite_accel_map(accel_map, [])
            removed.append(accel_map)
    return removed
