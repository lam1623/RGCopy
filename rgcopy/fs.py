"""Filesystem access restricted to configured roots, plus the size scan of a transfer."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

EntryKind = Literal["dir", "file"]


class PathError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Root(BaseModel):
    name: str
    path: str


class Entry(BaseModel):
    name: str
    path: str
    kind: EntryKind
    size: int | None = None
    modified: float | None = None
    link: bool = False


class Listing(BaseModel):
    path: str
    parent: str | None
    root: str
    entries: list[Entry]
    truncated: bool = False


def _natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


def filesystem_roots() -> list[Path]:
    return [Path("/")]


# Files listed per transfer (the totals always count everything)
MAX_LISTED = 20_000


@dataclass
class ScanResult:
    """What a transfer will move: bytes and regular files (directories and links count as 0 bytes)."""

    total_bytes: int = 0
    total_files: int = 0
    total_dirs: int = 0
    # (path as rsync names it, i.e. relative to the source's parent, size), in rsync's order
    files: list[tuple[str, int]] = field(default_factory=list)
    truncated: bool = False

    def _add(self, name: str, size: int) -> None:
        self.total_files += 1
        self.total_bytes += size
        if len(self.files) < MAX_LISTED:
            self.files.append((name, size))
        else:
            self.truncated = True


def scan(paths: list[Path]) -> ScanResult:
    """Walk the sources without following symlinks (rsync -a copies links as links)."""

    result = ScanResult()
    for path in paths:
        try:
            if path.is_symlink() or not path.is_dir():
                result._add(path.name, 0 if path.is_symlink() else path.stat().st_size)
                continue
        except OSError:
            continue
        result.total_dirs += 1
        base = path.parent
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            dirnames.sort()
            result.total_dirs += len(dirnames)
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                try:
                    stat = os.lstat(full)
                except OSError:
                    continue
                size = 0 if os.path.islink(full) else stat.st_size
                result._add(os.path.relpath(full, base), size)
    return result


class Conflict(BaseModel):
    """A file of the transfer that already exists at the destination."""

    path: str
    existing_size: int
    existing_mtime: float
    incoming_size: int
    incoming_mtime: float


def find_conflicts(
    sources: list[Path], destination: Path, files: list[tuple[str, int]], limit: int = 200
) -> tuple[int, list[Conflict]]:
    """How many listed files already exist at the destination, and the first ``limit`` of them."""

    parents = {source.name: source.parent for source in sources}
    count = 0
    found: list[Conflict] = []
    for name, size in files:
        target = destination / name
        try:
            existing = target.lstat()
        except OSError:
            continue
        if not os.path.isfile(target):
            continue
        count += 1
        if len(found) >= limit:
            continue
        parent = parents.get(name.split("/", 1)[0])
        try:
            incoming = (parent / name).lstat() if parent is not None else None
        except OSError:
            incoming = None
        found.append(
            Conflict(
                path=name,
                existing_size=existing.st_size,
                existing_mtime=existing.st_mtime,
                incoming_size=size,
                incoming_mtime=incoming.st_mtime if incoming else 0.0,
            )
        )
    return count, found


def free_space(path: Path) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def same_device(a: Path, b: Path) -> bool:
    try:
        return a.lstat().st_dev == b.stat().st_dev
    except OSError:
        return False


class FileSystem:
    def __init__(self, roots: list[Path], max_entries: int = 5000) -> None:
        resolved: list[Path] = []
        for root in roots:
            try:
                path = root.expanduser().resolve(strict=True)
            except OSError:
                continue
            if path.is_dir() and path not in resolved:
                resolved.append(path)
        self._roots = resolved
        self.max_entries = max_entries

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def root_views(self) -> list[Root]:
        home = Path.home()
        views = []
        # The home folder first: it is where most copies start
        for root in sorted(self._roots, key=lambda r: r != home):
            if root == home:
                name = "Home"
            elif root == Path(root.anchor):
                name = "/"
            else:
                name = root.name or str(root)
            views.append(Root(name=name, path=str(root)))
        if home not in self._roots and self.root_of(home) is not None:
            views.insert(0, Root(name="Home", path=str(home)))
        return views

    def root_of(self, path: Path) -> Path | None:
        matches = [root for root in self._roots if path == root or path.is_relative_to(root)]
        return max(matches, key=lambda r: len(r.parts)) if matches else None

    def resolve(
        self,
        raw: str,
        *,
        kind: Literal["file", "dir", "any"] = "any",
        must_exist: bool = True,
        follow: bool = True,
    ) -> Path:
        """An absolute path inside the roots. ``follow=False`` keeps a symlink itself (a source)."""

        if not raw or "\x00" in raw:
            raise PathError("bad_path", "Empty or invalid path")
        path = Path(raw)
        if not path.is_absolute():
            raise PathError("bad_path", "Paths must be absolute")
        try:
            if follow:
                resolved = path.resolve(strict=must_exist)
            else:
                # Resolve the parent only, so a link is copied as a link
                resolved = path.parent.resolve(strict=must_exist) / path.name
                if must_exist and not resolved.exists() and not resolved.is_symlink():
                    raise FileNotFoundError(raw)
        except (OSError, RuntimeError) as exc:
            raise PathError("not_found", f"Not found: {raw}") from exc
        if self.root_of(resolved) is None:
            raise PathError("outside_roots", "This location is outside the folders RGCopy can access")
        if must_exist:
            if kind == "file" and not resolved.is_file():
                raise PathError("not_a_file", f"Not a file: {raw}")
            if kind == "dir" and not resolved.is_dir():
                raise PathError("not_a_dir", f"Not a folder: {raw}")
        return resolved

    def list_dir(self, raw: str, *, show_hidden: bool = False) -> Listing:
        directory = self.resolve(raw, kind="dir")
        root = self.root_of(directory)
        assert root is not None
        entries: list[Entry] = []
        truncated = False
        try:
            with os.scandir(directory) as scan_it:
                for item in scan_it:
                    if not show_hidden and item.name.startswith("."):
                        continue
                    try:
                        is_dir = item.is_dir()
                        stat = item.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if len(entries) >= self.max_entries:
                        truncated = True
                        break
                    entries.append(
                        Entry(
                            name=item.name,
                            path=str(directory / item.name),
                            kind="dir" if is_dir else "file",
                            size=None if is_dir else stat.st_size,
                            modified=stat.st_mtime,
                            link=item.is_symlink(),
                        )
                    )
        except PermissionError as exc:
            raise PathError("forbidden", f"Permission denied: {directory}") from exc
        entries.sort(key=lambda e: (e.kind != "dir", _natural_key(e.name)))
        parent = directory.parent if directory != root else None
        return Listing(
            path=str(directory),
            parent=str(parent) if parent else None,
            root=str(root),
            entries=entries,
            truncated=truncated,
        )
