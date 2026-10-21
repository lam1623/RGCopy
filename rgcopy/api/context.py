"""Shared application state handed to request handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from starlette.requests import HTTPConnection

from ..config import AppConfig
from ..engine.rsync import RsyncInfo
from ..fs import FileSystem
from ..jobs import JobManager
from ..settings import SettingsStore


@dataclass
class AppContext:
    config: AppConfig
    rsync: RsyncInfo | None
    rsync_error: str | None
    settings: SettingsStore
    fs: FileSystem
    manager: JobManager
    # Set by the desktop launcher: brings its window to the front
    focus_window: Callable[[], None] | None = field(default=None)


async def get_ctx(conn: HTTPConnection) -> AppContext:
    ctx: AppContext = conn.app.state.ctx
    return ctx
