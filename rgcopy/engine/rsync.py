"""Find rsync, build its command line and parse its progress output."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# --info=progress2 needs rsync 3.1
MIN_VERSION = (3, 1, 0)

Mode = Literal["copy", "move"]
# "ask": RGCopy looks for existing files before starting and asks which rule to use
Conflict = Literal["ask", "overwrite", "skip", "update", "backup"]
# The rules rsync itself applies
Resolution = Literal["overwrite", "skip", "update", "backup"]

# Suffix rsync gives to the previous version of a replaced file with conflict="backup"
BACKUP_SUFFIX = ".rgcopy~"


class RsyncNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class RsyncInfo:
    path: str
    version: str
    protocol: int | None

    @property
    def version_tuple(self) -> tuple[int, ...]:
        return tuple(int(p) for p in re.findall(r"\d+", self.version)[:3])


def popen_kwargs(**extra_env: str) -> dict[str, Any]:
    """Child processes run in the C locale so numbers never use locale separators."""

    env = {**os.environ, "LC_ALL": "C", "LANG": "C", **extra_env}
    return {"env": env}


def discover(explicit: str | None = None) -> RsyncInfo:
    candidate = explicit or os.environ.get("RGCOPY_RSYNC") or shutil.which("rsync")
    if not candidate:
        raise RsyncNotFoundError("rsync was not found: install it (e.g. `sudo apt install rsync`)")
    try:
        out = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
            **popen_kwargs(),
        ).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RsyncNotFoundError(f"rsync at {candidate} cannot run: {exc}") from exc
    match = re.search(r"rsync\s+version\s+v?(\S+)(?:\s+protocol version (\d+))?", out)
    if not match:
        raise RsyncNotFoundError(f"{candidate} does not look like rsync")
    info = RsyncInfo(
        path=candidate, version=match.group(1), protocol=int(match.group(2)) if match.group(2) else None
    )
    if info.version_tuple < MIN_VERSION:
        raise RsyncNotFoundError(f"rsync {info.version} is too old: RGCopy needs 3.1 or newer")
    return info


class TransferOptions(BaseModel):
    mode: Mode = "copy"
    conflict: Conflict = "overwrite"
    checksum: bool = False
    preserve: bool = True
    bwlimit: int = Field(0, ge=0, le=10_000_000)


def exclude_pattern(name: str) -> str:
    """An rsync rule matching exactly ``name`` (relative to the transfer root, as rsync prints it)."""

    escaped = "".join("\\" + char if char in "*?[\\" else char for char in name)
    return "/" + escaped


def build_command(
    rsync: str,
    sources: list[Path],
    destination: Path,
    options: TransferOptions,
    *,
    excludes: list[str] | None = None,
    verify: bool = False,
) -> list[str]:
    """rsync argv that puts every source *inside* ``destination``, like pasting in a file manager.

    ``excludes`` are files the user skipped. ``verify`` changes nothing: it lists, by content,
    the files that differ from the destination, under the same conflict rule as the copy.
    """

    # -a: recursive, links, permissions, times, group, owner, devices; -rlt is the portable subset
    argv = [rsync, "-a" if options.preserve else "-rlt"]
    if verify:
        argv += ["--checksum", "--dry-run", "--itemize-changes"]
    else:
        # One overall progress line plus the name of each transferred file
        argv.append("--info=progress2,name1")
    argv += [
        # Know the whole file list up front, so the overall percentage does not jump back
        "--no-inc-recursive",
        # Print file names as they are (UTF-8), not as \#ooo escapes
        "--8-bit-output",
        "--outbuf=L",
    ]
    if options.checksum and not verify:
        argv.append("--checksum")
    if options.bwlimit and not verify:
        argv.append(f"--bwlimit={options.bwlimit}")
    if options.conflict == "skip":
        argv.append("--ignore-existing")
    elif options.conflict == "update":
        argv.append("--update")
    elif options.conflict == "backup" and not verify:
        argv += ["--backup", f"--suffix={BACKUP_SUFFIX}"]
    if options.mode == "move" and not verify:
        argv.append("--remove-source-files")
    argv += [f"--exclude={exclude_pattern(name)}" for name in excludes or []]
    # "--" ends the options: a file named "-n" must not turn into a dry run
    argv.append("--")
    argv += [str(s) for s in sources]
    # Trailing slash: the destination is always a directory
    argv.append(str(destination).rstrip("/") + "/")
    return argv


def display_command(argv: list[str]) -> str:
    return shlex.join(argv)


class Progress(BaseModel):
    percent: float = 0.0
    bytes_done: int = 0
    total_bytes: int = 0
    files_done: int = 0
    total_files: int = 0
    # Bytes per second
    speed: float | None = None
    eta_s: float | None = None
    elapsed_s: float = 0.0
    # The file being transferred, relative to the destination, and how far it is
    current: str | None = None
    current_bytes: int = 0
    current_size: int | None = None


_UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}

# "  1.23G  45%   10.52MB/s    0:00:03 (xfr#3, to-chk=10/20)"
PROGRESS_RE = re.compile(
    r"^\s*(?P<bytes>[\d.,]+)(?P<bunit>[KMGTP]?)\s+(?P<pct>\d+)%\s+"
    r"(?P<speed>[\d.,]+)(?P<sunit>[kKMGTP]?)B/s\s+(?P<eta>\d+:\d{2}:\d{2})"
    r"(?:\s+\(xfr#(?P<xfr>\d+),\s+(?:to|ir)-chk=(?P<left>\d+)/(?P<total>\d+)\))?"
)


def _number(text: str, unit: str) -> float:
    # With LC_ALL=C rsync groups thousands with "," and uses "." for decimals
    return float(text.replace(",", "")) * _UNITS[unit.upper()]


@dataclass
class ProgressLine:
    bytes_done: int
    percent: int
    speed: float
    eta_s: int
    transferred: int | None
    to_check: int | None
    total_entries: int | None


def parse_progress_line(line: str) -> ProgressLine | None:
    match = PROGRESS_RE.match(line)
    if not match:
        return None
    hours, minutes, seconds = (int(p) for p in match.group("eta").split(":"))
    return ProgressLine(
        bytes_done=int(_number(match.group("bytes"), match.group("bunit"))),
        percent=int(match.group("pct")),
        speed=_number(match.group("speed"), match.group("sunit")),
        eta_s=hours * 3600 + minutes * 60 + seconds,
        transferred=int(match.group("xfr")) if match.group("xfr") else None,
        to_check=int(match.group("left")) if match.group("left") else None,
        total_entries=int(match.group("total")) if match.group("total") else None,
    )


# Lines rsync prints at the end or for its own housekeeping, not file names
_NOISE = (
    "sending incremental file list",
    "building file list",
    "sent ",
    "total size is",
    "created directory",
    "deleting ",
)


def is_file_name(line: str) -> bool:
    """A ``name1`` line naming a transferred file (directories end with ``/``)."""

    stripped = line.strip()
    if not stripped or stripped.endswith("/"):
        return False
    return not any(stripped.startswith(prefix) for prefix in _NOISE)
