"""Command line entry point: desktop app, web server, headless copies and file manager paste."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__, clipboard, integration
from .config import (
    AppConfig,
    auth_enabled_from_env,
    default_data_dir,
    default_roots,
    ui_autobuild_from_env,
)
from .engine.rsync import RsyncNotFoundError, discover
from .fs import FileSystem, PathError, filesystem_roots
from .jobs import JobManager, JobStatus, ManagerError
from .settings import Settings, SettingsStore
from .web import ensure_built

CONFLICTS = ["overwrite", "skip", "update", "backup"]


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rsync", help="Path to the rsync binary (default: $RGCOPY_RSYNC or PATH)")
    parser.add_argument("--data-dir", type=Path, help="Where settings live (default: $RGCOPY_DATA_DIR)")
    parser.add_argument("--log-level", default=os.environ.get("RGCOPY_LOG_LEVEL", "info"))


def _transfer_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--conflict",
        choices=CONFLICTS,
        help="existing files: overwrite (default), skip, update (only newer) or backup (keep the old one)",
    )
    parser.add_argument("--checksum", action="store_true", help="compare files by content, not size and date")
    parser.add_argument("--no-preserve", action="store_true", help="do not keep permissions, owner and group")
    parser.add_argument("--bwlimit", type=int, help="bandwidth limit in KiB/s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rgcopy", description="File copy queue for Linux powered by rsync.")
    parser.add_argument("--version", action="version", version=f"rgcopy {__version__}")
    sub = parser.add_subparsers(dest="command")

    desktop = sub.add_parser("desktop", help="open the desktop app (default)")
    desktop.add_argument(
        "--browser", action="store_true", help="use the web browser instead of a native window"
    )
    desktop.add_argument("--root", action="append", default=[], help="restrict browsing to this folder")
    _common(desktop)

    serve = sub.add_parser("serve", help="run the web UI/API server (Docker, NAS, headless)")
    serve.add_argument("--host", default=os.environ.get("RGCOPY_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("RGCOPY_PORT", "8000")))
    serve.add_argument(
        "--token", default=os.environ.get("RGCOPY_TOKEN"), help="access token (default: random)"
    )
    serve.add_argument("--no-auth", action="store_true", help="disable authentication (trusted proxies only)")
    serve.add_argument("--root", action="append", default=[], help="folder the UI may access (repeatable)")
    serve.add_argument("--open", action="store_true", help="open the UI in the default browser")
    _common(serve)

    for name, help_text in (
        ("copy", "copy files from the terminal"),
        ("move", "move files from the terminal"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("sources", nargs="+", type=Path)
        command.add_argument("destination", type=Path, help="folder that receives the files")
        _transfer_flags(command)
        command.add_argument("--gui", action="store_true", help="show the transfer in the desktop app")
        _common(command)

    paste = sub.add_parser("paste", help="paste the files copied or cut in the file manager")
    paste.add_argument(
        "destination",
        nargs="?",
        help="folder or file:// URI (default: the file manager's folder, else the current one)",
    )
    paste.add_argument("--headless", action="store_true", help="copy in the terminal, without a window")
    _transfer_flags(paste)
    _common(paste)

    integrate = sub.add_parser(
        "integrate", help='add RGCopy to the menu and "Paste with RGCopy" to the file managers'
    )
    integrate.add_argument("--uninstall", action="store_true", help="remove what `integrate` added")
    integrate.add_argument(
        "--no-takeover",
        action="store_true",
        help="leave Ctrl+V to the file manager (RGCopy pastes with Ctrl+Shift+V or the Scripts menu)",
    )
    integrate.add_argument(
        "--accel",
        default=integration.DEFAULT_ACCEL,
        help=f"extra Nautilus shortcut, '' for none (default: {integration.DEFAULT_ACCEL})",
    )
    return parser


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _config(args: argparse.Namespace, *, desktop: bool) -> AppConfig:
    roots = getattr(args, "root", None)
    return AppConfig(
        roots=[Path(p) for p in roots] if roots else default_roots(desktop),
        data_dir=args.data_dir or default_data_dir(),
        rsync_bin=args.rsync,
    )


def _options(args: argparse.Namespace, *, move: bool) -> dict[str, Any]:
    options: dict[str, Any] = {"mode": "move" if move else "copy"}
    if args.conflict:
        options["conflict"] = args.conflict
    if args.checksum:
        options["checksum"] = True
    if args.no_preserve:
        options["preserve"] = False
    if args.bwlimit is not None:
        options["bwlimit"] = max(0, args.bwlimit)
    return options


def cmd_desktop(args: argparse.Namespace, pending: Any = None) -> int:
    from .desktop import run_desktop

    _setup_logging(args.log_level)
    ensure_built(enabled=ui_autobuild_from_env())
    return run_desktop(
        _config(args, desktop=True), prefer_browser=getattr(args, "browser", False), pending=pending
    )


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    _setup_logging(args.log_level)
    ensure_built(enabled=ui_autobuild_from_env())
    config = _config(args, desktop=False)
    config.host, config.port = args.host, args.port
    auth = auth_enabled_from_env() and not args.no_auth
    config.auth_token = (args.token or secrets.token_urlsafe(24)) if auth else None

    shown_host = "localhost" if args.host in ("0.0.0.0", "::", "") else args.host
    url = f"http://{shown_host}:{args.port}/"
    if config.auth_token:
        url += f"auth?token={config.auth_token}"
    else:
        logging.getLogger("rgcopy").warning("Authentication is DISABLED: only use behind a trusted proxy")
    print(f"\n  RGCopy {__version__} → {url}\n", flush=True)
    if args.open:
        import webbrowser

        webbrowser.open(url)
    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


def _fmt_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60:02d}:{rest % 60:02d}"


async def _transfer(
    sources: list[str], destination: str, options: dict[str, Any], args: argparse.Namespace
) -> int:
    try:
        rsync = discover(args.rsync)
    except RsyncNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    manager = JobManager(
        rsync=rsync,
        # Nobody answers a question in a terminal: existing files follow --conflict (default: replace)
        settings=SettingsStore(None, Settings(auto_start=False, conflict="overwrite")),
        fs=FileSystem(filesystem_roots()),
    )
    await manager.start()
    events = manager.subscribe()
    try:
        try:
            job = await manager.add_transfer(sources, destination, options)
        except (ManagerError, PathError) as exc:
            print(f"error: {exc.message}", file=sys.stderr)
            return 2
        interactive = sys.stdout.isatty()
        verb = "Moving" if options.get("mode") == "move" else "Copying"
        while True:
            event = await events.get()
            if event["type"] == "job" and event["job"]["id"] == job.id:
                data = event["job"]
                status = data["status"]
                if status == JobStatus.QUEUED and not manager.queue_running:
                    total = _fmt_bytes(data["total_bytes"])
                    print(
                        f"{verb} {data['total_files']} files ({total}) to {data['destination']}", flush=True
                    )
                    manager.start_queue()
                elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED):
                    if interactive:
                        print("\r\033[K", end="")
                    progress = data["progress"]
                    if status == JobStatus.COMPLETED:
                        took = _fmt_time(progress["elapsed_s"])
                        note = f" ({data['warning']})" if data.get("warning") else ""
                        print(f"Done: {_fmt_bytes(progress['bytes_done'])} in {took}{note}")
                        return 0
                    print(f"{status}: {data.get('error') or ''}", file=sys.stderr)
                    return 1
            elif event["type"] == "progress" and interactive:
                for item in event["items"]:
                    if item["id"] != job.id:
                        continue
                    p = item["progress"]
                    speed = f"{_fmt_bytes(p['speed'])}/s" if p.get("speed") else "…"
                    current = (p.get("current") or "")[-40:]
                    eta = _fmt_time(p.get("eta_s"))
                    print(
                        f"\r\033[K{p['percent']:5.1f}%  {_fmt_bytes(p['bytes_done'])} of "
                        f"{_fmt_bytes(p['total_bytes'])}  {speed}  ETA {eta}  {current}",
                        end="",
                        flush=True,
                    )
    finally:
        manager.unsubscribe(events)
        await manager.shutdown()


def _run_transfer(
    sources: list[str], destination: str, options: dict[str, Any], args: argparse.Namespace
) -> int:
    logging.basicConfig(level=logging.WARNING)
    try:
        return asyncio.run(_transfer(sources, destination, options, args))
    except KeyboardInterrupt:
        print("\nCanceled.", file=sys.stderr)
        return 130


def cmd_copy(args: argparse.Namespace) -> int:
    sources = [str(p.absolute()) for p in args.sources]
    destination = str(args.destination.absolute())
    options = _options(args, move=args.command == "move")
    if args.gui:
        from .desktop import PendingTransfer

        return cmd_desktop(args, PendingTransfer(sources, destination, options))
    return _run_transfer(sources, destination, options, args)


def _notify(title: str, body: str) -> None:
    """Scripts run from a file manager have no terminal: tell the user on the desktop."""

    print(f"{title}: {body}", file=sys.stderr)
    if shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "--app-name=RGCopy", f"--icon={integration.APP_ID}", title, body],
            check=False,
            stdin=subprocess.DEVNULL,
        )


def cmd_paste(args: argparse.Namespace) -> int:
    from .clipboard import uri_to_path

    if args.destination:
        destination = uri_to_path(args.destination) or args.destination
    else:
        destination = integration.destination_from_env() or os.getcwd()
    destination = str(Path(destination).absolute())
    files = clipboard.read()
    if files.source is None:
        _notify("RGCopy", "Cannot read the clipboard: install wl-clipboard (Wayland) or xclip (X11)")
        return 2
    if not files.paths:
        _notify("RGCopy", "There are no copied files to paste")
        return 1
    options = _options(args, move=files.action == "cut")
    if args.headless:
        return _run_transfer(files.paths, destination, options, args)
    from .desktop import PendingTransfer

    return cmd_desktop(args, PendingTransfer(files.paths, destination, options))


def cmd_integrate(args: argparse.Namespace) -> int:
    if args.uninstall:
        closed = integration.quit_file_managers(["nemo", "caja"])
        for path in integration.uninstall():
            print(f"Removed {path}")
        warnings: list[str] = []
    else:
        takeover = not args.no_takeover
        closed = integration.quit_file_managers(["nautilus", "nemo", "caja"] if takeover else [])
        paths, warnings = integration.install(args.accel or None, takeover=takeover)
        for path in paths:
            print(f"Installed {path}")
        if takeover:
            print("\nCtrl+C / Ctrl+X in the file manager, then Ctrl+V: RGCopy copies or moves the files.")
        print('"Paste with RGCopy" is also in the right-click menu, under Scripts.')
    for warning in warnings:
        print(f"\nwarning: {warning}", file=sys.stderr)
    if closed:
        print(f"\nClosed {', '.join(closed)} so the change applies: open it again.")
    else:
        print("\nRestart the file manager if it is open (e.g. `nautilus -q`).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["desktop", *(argv or sys.argv[1:])])
    handlers = {
        "desktop": cmd_desktop,
        "serve": cmd_serve,
        "copy": cmd_copy,
        "move": cmd_copy,
        "paste": cmd_paste,
        "integrate": cmd_integrate,
    }
    return handlers[args.command](args)
