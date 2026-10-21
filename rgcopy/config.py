"""Runtime configuration from CLI flags and ``RGCOPY_*`` environment variables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

from .fs import filesystem_roots


def default_data_dir() -> Path:
    env = os.environ.get("RGCOPY_DATA_DIR")
    return Path(env) if env else Path(user_data_dir("rgcopy", appauthor=False))


def default_roots(desktop: bool) -> list[Path]:
    env = os.environ.get("RGCOPY_ROOTS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p.strip()]
    if desktop:
        # The desktop app runs as the logged-in user, like the file manager it replaces
        return filesystem_roots()
    roots = [Path.home()]
    if sys.platform.startswith("linux"):
        roots += [p for p in (Path("/media"), Path("/mnt"), Path("/run/media")) if p.is_dir()]
    return roots


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    # None disables authentication (only for trusted reverse-proxy setups)
    auth_token: str | None = None
    roots: list[Path] = field(default_factory=lambda: default_roots(desktop=False))
    data_dir: Path = field(default_factory=default_data_dir)
    rsync_bin: str | None = None
    desktop: bool = False
    static_dir: Path | None = None

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"


def auth_enabled_from_env() -> bool:
    return _env_bool("RGCOPY_AUTH", True)


def ui_autobuild_from_env() -> bool:
    """Rebuild a source checkout's web UI at startup when ``frontend/`` changed."""

    return _env_bool("RGCOPY_AUTOBUILD", True)
