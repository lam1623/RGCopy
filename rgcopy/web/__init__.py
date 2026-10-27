"""Location of the compiled single-page app, rebuilt on demand in a source checkout."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from ..engine.rsync import popen_kwargs

STATIC_DIR = Path(__file__).resolve().parent / "dist"
# Only present in a source checkout: wheels and the Docker image ship the built UI alone
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

log = logging.getLogger(__name__)

# Generated or third-party trees that are not inputs of the build
_SKIPPED_DIRS = frozenset({"node_modules", "dist"})
# Per npm command: a first `npm ci` downloads every dependency
_NPM_TIMEOUT = 600


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _newest_source(frontend_dir: Path) -> float:
    newest = 0.0
    for dirpath, dirnames, filenames in os.walk(frontend_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIRS and not d.startswith(".")]
        for name in filenames:
            newest = max(newest, _mtime(Path(dirpath, name)) or 0.0)
    return newest


def stale_reason(frontend_dir: Path = FRONTEND_DIR, static_dir: Path = STATIC_DIR) -> str | None:
    """Why the built UI does not match ``frontend/``: None when it does, or outside a source checkout.

    ``rgcopy/web/dist`` is not versioned, so a ``git pull`` or a branch switch updates the
    sources (and their modification times) while the app would keep serving the previous build.
    """

    if not (frontend_dir / "package.json").is_file():
        return None
    built = _mtime(static_dir / "index.html")
    if built is None:
        return "not built yet"
    if _newest_source(frontend_dir) > built:
        return "older than the sources in frontend/"
    return None


def _dependencies_outdated(frontend_dir: Path) -> bool:
    # npm writes node_modules/.package-lock.json on every install
    installed = _mtime(frontend_dir / "node_modules" / ".package-lock.json")
    locked = _mtime(frontend_dir / "package-lock.json")
    return installed is None or (locked is not None and locked > installed)


def _npm(npm: str, args: list[str], frontend_dir: Path) -> bool:
    command = f"npm {' '.join(args)}"
    try:
        result = subprocess.run(
            [npm, *args],
            cwd=frontend_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_NPM_TIMEOUT,
            check=False,
            **popen_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("`%s` failed (%s): keeping the previous web UI", command, exc)
        return False
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
        log.error("`%s` exited with %d: keeping the previous web UI\n%s", command, result.returncode, tail)
        return False
    return True


def ensure_built(
    frontend_dir: Path = FRONTEND_DIR, static_dir: Path = STATIC_DIR, *, enabled: bool = True
) -> bool:
    """Rebuild the UI of a source checkout when ``frontend/`` changed since the last build.

    Returns whether the UI that will be served is current. Never raises: when npm is missing
    or the build fails, the previous build keeps being served and the log says how to fix it.
    """

    reason = stale_reason(frontend_dir, static_dir)
    if reason is None:
        return True
    npm = shutil.which("npm")
    if not enabled or npm is None:
        log.warning("The web UI is %s: run `make build` (or `npm --prefix frontend run build`)", reason)
        return False
    log.warning("The web UI is %s, rebuilding it (RGCOPY_AUTOBUILD=off skips this)", reason)
    started = time.monotonic()
    steps = [["run", "build"]]
    if _dependencies_outdated(frontend_dir):
        steps.insert(0, ["ci", "--no-audit", "--no-fund"])
    if not all(_npm(npm, args, frontend_dir) for args in steps):
        return False
    log.info("Web UI rebuilt in %.0f s", time.monotonic() - started)
    return True
