"""Files copied or cut in a file manager (Nautilus, Nemo, Caja, Thunar, Dolphin, PCManFM)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

Action = Literal["copy", "cut"]

# GNOME-family file managers put "copy|cut" followed by one URI per line in this target
GNOME_TARGET = "x-special/gnome-copied-files"
# Caja (MATE) uses the same payload under its own name
MATE_TARGET = "x-special/mate-copied-files"
# KDE marks a cut with this target ("1") next to a plain URI list
KDE_CUT_TARGET = "application/x-kde-cutselection"
URI_LIST_TARGET = "text/uri-list"


@dataclass
class ClipboardFiles:
    action: Action = "copy"
    paths: list[str] = field(default_factory=list)
    # Where the clipboard was read from: "wayland", "x11" or None when nothing could read it
    source: str | None = None


def gvfs_path(uri: str, uid: int | None = None) -> str | None:
    """Local path of a GVfs mount (smb://, sftp://, ftp://…) as GVfs exposes it under /run/user."""

    parts = urlsplit(uri)
    uid = os.getuid() if uid is None else uid
    base = Path(f"/run/user/{uid}/gvfs")
    path = unquote(parts.path).lstrip("/")
    host = parts.hostname or ""
    if parts.scheme == "smb":
        share, _, rest = path.partition("/")
        if not share:
            return None
        return str(base / f"smb-share:server={host},share={share.lower()}" / rest)
    if parts.scheme in ("sftp", "ftp", "dav", "davs"):
        mount = f"{parts.scheme}:host={host}"
        if parts.port:
            mount += f",port={parts.port}"
        if parts.username:
            mount += f",user={unquote(parts.username)}"
        return str(base / mount / path)
    return None


def uri_to_path(uri: str, uid: int | None = None) -> str | None:
    uri = uri.strip()
    if not uri or uri.startswith("#"):
        return None
    if uri.startswith("/"):
        return uri
    parts = urlsplit(uri)
    if parts.scheme == "file":
        return unquote(parts.path) or None
    return gvfs_path(uri, uid)


def parse_gnome(data: str, uid: int | None = None) -> ClipboardFiles:
    lines = [line for line in data.replace("\r", "").split("\n") if line.strip()]
    if not lines:
        return ClipboardFiles()
    action: Action = "cut" if lines[0].strip() == "cut" else "copy"
    uris = lines[1:] if lines[0].strip() in ("copy", "cut") else lines
    # Nautilus 45+ writes the same payload as plain text, prefixed with this header
    if uris and uris[0].strip() == "x-special/nautilus-clipboard":
        uris = uris[1:]
        if uris and uris[0].strip() in ("copy", "cut"):
            action = "cut" if uris[0].strip() == "cut" else "copy"
            uris = uris[1:]
    paths = [p for p in (uri_to_path(u, uid) for u in uris) if p]
    return ClipboardFiles(action=action, paths=paths)


def _reader() -> tuple[str, list[str], list[str]] | None:
    """(name, command listing targets, command reading a target) for this session."""

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return "wayland", ["wl-paste", "--list-types"], ["wl-paste", "--no-newline", "--type"]
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        return (
            "x11",
            ["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"],
            ["xclip", "-selection", "clipboard", "-o", "-t"],
        )
    return None


def _run(argv: list[str]) -> str | None:
    try:
        result = subprocess.run(argv, capture_output=True, timeout=3, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def available() -> bool:
    return _reader() is not None


def read() -> ClipboardFiles:
    """The files on the desktop clipboard; empty when it holds none or cannot be read."""

    reader = _reader()
    if reader is None:
        return ClipboardFiles()
    name, list_cmd, read_cmd = reader
    targets = set((_run(list_cmd) or "").split())
    special = next((t for t in (GNOME_TARGET, MATE_TARGET) if t in targets), None)
    if special:
        files = parse_gnome(_run([*read_cmd, special]) or "")
    elif URI_LIST_TARGET in targets:
        files = parse_gnome(_run([*read_cmd, URI_LIST_TARGET]) or "")
        if KDE_CUT_TARGET in targets and (_run([*read_cmd, KDE_CUT_TARGET]) or "").strip() == "1":
            files.action = "cut"
    else:
        text = _run([*read_cmd, "text/plain"]) or ""
        files = parse_gnome(text) if text.startswith("x-special/nautilus-clipboard") else ClipboardFiles()
    files.source = name
    files.paths = [p for p in files.paths if os.path.lexists(p)]
    return files
