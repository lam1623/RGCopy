"""Desktop mode: private local server plus a native window (pywebview) or the browser."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn

from . import instance
from .api import create_app
from .api.context import AppContext
from .config import AppConfig
from .jobs import ManagerError
from .settings import SettingsStore

log = logging.getLogger(__name__)

# Window color shown before the UI paints, matching --bg of each theme in index.css
WINDOW_BACKGROUNDS = {"light": "#f5f6f8", "dark": "#17191d"}


@dataclass
class PendingTransfer:
    """Files to queue as soon as the app is up (``rgcopy paste``, ``rgcopy copy --gui``)."""

    sources: list[str]
    destination: str
    options: dict[str, Any] = field(default_factory=dict)


def _window_background(config: AppConfig) -> str:
    theme = SettingsStore(config.settings_path).current.theme
    return WINDOW_BACKGROUNDS.get(theme, WINDOW_BACKGROUNDS["light"])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class NativeBridge:
    """Methods exposed to the web UI as ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._window: Any = None

    def attach(self, window: Any) -> None:
        self._window = window

    def _dialog(self, kind: str, **kwargs: Any) -> list[str]:
        import webview

        dialog_enum = getattr(webview, "FileDialog", None)
        dialog_type = getattr(dialog_enum, kind) if dialog_enum else getattr(webview, f"{kind}_DIALOG")
        result = self._window.create_file_dialog(dialog_type, **kwargs)
        return [str(p) for p in result] if result else []

    def pick_files(self) -> list[str]:
        return self._dialog("OPEN", allow_multiple=True)

    def pick_folder(self) -> str | None:
        folders = self._dialog("FOLDER")
        return folders[0] if folders else None

    def open_path(self, path: str) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(target)], stdin=subprocess.DEVNULL, start_new_session=True)
        return True

    def set_title(self, title: str) -> None:
        if self._window is not None:
            self._window.set_title(title)

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()


def _preferred_gui() -> str | None:
    """On Linux, pick the installed toolkit so pywebview does not try (and log) GTK first."""

    if not sys.platform.startswith("linux"):
        return None
    if importlib.util.find_spec("qtpy") and importlib.util.find_spec("PyQt6"):
        return "qt"
    if importlib.util.find_spec("gi"):
        return "gtk"
    return None


def _queue_pending(ctx: AppContext, pending: PendingTransfer | None) -> None:
    if pending is None:
        return

    async def add() -> None:
        try:
            await ctx.manager.add_transfer(pending.sources, pending.destination, pending.options)
        except ManagerError as exc:
            log.error("Cannot queue the pasted files: %s", exc.message)
        except Exception:
            log.exception("Cannot queue the pasted files")

    asyncio.get_running_loop().create_task(add())


def _start_server(
    config: AppConfig, pending: PendingTransfer | None, contexts: list[AppContext]
) -> tuple[uvicorn.Server, threading.Thread]:
    def ready(ctx: AppContext) -> None:
        contexts.append(ctx)
        _queue_pending(ctx, pending)

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(config, on_ready=ready), host=config.host, port=config.port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, name="rgcopy-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("The local RGCopy server did not start")
        time.sleep(0.05)
    return server, thread


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=20)


def hand_over(pending: PendingTransfer | None) -> bool:
    """Give the transfer to an already open RGCopy window. False when none is running."""

    running = instance.running()
    if running is None:
        return False
    try:
        if pending is not None:
            instance.call(
                running,
                "POST",
                "/api/jobs",
                {"sources": pending.sources, "destination": pending.destination, "options": pending.options},
            )
        instance.call(running, "POST", "/api/window/focus")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"RGCopy could not queue the files: {detail}", file=sys.stderr)
    except (OSError, urllib.error.URLError) as exc:
        log.warning("The running RGCopy did not answer (%s): opening a new window", exc)
        return False
    return True


def run_desktop(
    config: AppConfig, *, prefer_browser: bool = False, pending: PendingTransfer | None = None
) -> int:
    if os.environ.get("RGCOPY_SINGLE_INSTANCE", "1") != "0" and hand_over(pending):
        return 0

    config.host = "127.0.0.1"
    config.port = _free_port()
    config.auth_token = secrets.token_urlsafe(24)
    config.desktop = True
    contexts: list[AppContext] = []
    server, thread = _start_server(config, pending, contexts)
    me = instance.Instance(port=config.port, token=config.auth_token, pid=os.getpid())
    instance.publish(me)
    url = f"http://127.0.0.1:{config.port}/auth?token={config.auth_token}"

    webview: Any = None
    if not prefer_browser:
        try:
            webview = importlib.import_module("webview")
        except ImportError:
            print("pywebview is not installed; opening RGCopy in your browser instead.")

    try:
        if webview is None:
            print(f"RGCopy is running at {url}\nPress Ctrl+C to quit.")
            webbrowser.open(url)
            while thread.is_alive():
                thread.join(0.5)
            return 0
        bridge = NativeBridge()
        window = webview.create_window(
            "RGCopy",
            url,
            js_api=bridge,
            # A copy dialog, not a full-screen app
            width=760,
            height=600,
            min_size=(520, 420),
            background_color=_window_background(config),
        )
        bridge.attach(window)

        def focus() -> None:
            # Un-minimize and raise: a second paste should bring the window back
            for action in ("restore", "show"):
                with contextlib.suppress(Exception):
                    getattr(window, action)()
            with contextlib.suppress(Exception):
                window.on_top = True
                window.on_top = False

        for ctx in contexts:
            ctx.focus_window = focus
        webview.start(gui=_preferred_gui(), private_mode=False, storage_path=str(config.data_dir / "webview"))
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        instance.withdraw(me)
        _stop_server(server, thread)
