"""FastAPI application factory."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Scope

from .. import __version__
from ..config import AppConfig
from ..engine.rsync import RsyncInfo, RsyncNotFoundError, discover
from ..fs import FileSystem, PathError
from ..jobs import JobManager, ManagerError
from ..settings import SettingsStore
from ..web import STATIC_DIR
from . import auth, routes
from .context import AppContext
from .events import events_ws

log = logging.getLogger("rgcopy")

_CSP_BASE = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; connect-src 'self' ws: wss:; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)
CONTENT_SECURITY_POLICY = f"{_CSP_BASE}; script-src 'self'"
# pywebview injects its JS bridge with eval(); only our own window loads the desktop server
DESKTOP_CONTENT_SECURITY_POLICY = f"{_CSP_BASE}; script-src 'self' 'unsafe-inline' 'unsafe-eval'"

MISSING_UI = (
    "<!doctype html><html><head><meta charset='utf-8'><title>RGCopy</title></head>"
    "<body style='font-family:system-ui;background:#0b0c10;color:#e6e6e9;display:grid;"
    "place-items:center;height:100vh'><div><h1>RGCopy API is running</h1>"
    "<p>The web UI has not been built yet. Run <code>make build</code> and restart.</p>"
    "<p><a style='color:#4f9dff' href='/api/docs'>API docs</a></p></div></body></html>"
)


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, csp: str = CONTENT_SECURITY_POLICY) -> None:
        super().__init__(app)
        self.csp = csp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", self.csp)
        return response


_HTML_TAG = re.compile(r"<html\b", re.IGNORECASE)


class SPAStaticFiles(StaticFiles):
    """Static SPA files: hashed assets are immutable, the HTML shell is always revalidated."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        if isinstance(response, FileResponse) and response.media_type == "text/html":
            response = _stamp_theme(response, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _stamp_theme(response: FileResponse, scope: Scope) -> Response:
    """Put the saved theme on ``<html data-theme>`` so the very first paint already uses it.

    The desktop app gets a new port (a new origin, hence empty localStorage) on every launch.
    """

    ctx = getattr(scope["app"].state, "ctx", None)
    if ctx is None:
        return response
    html = Path(response.path).read_text("utf-8")
    html = _HTML_TAG.sub(f'<html data-theme="{ctx.settings.current.theme}"', html, count=1)
    return HTMLResponse(html, status_code=response.status_code)


def _discover_rsync(config: AppConfig) -> tuple[RsyncInfo | None, str | None]:
    try:
        return discover(config.rsync_bin), None
    except RsyncNotFoundError as exc:
        log.error("%s", exc)
        return None, str(exc)


def create_app(
    config: AppConfig | None = None,
    *,
    on_ready: Callable[[AppContext], None] | None = None,
) -> FastAPI:
    """``on_ready`` runs once the context exists (the desktop launcher queues the pasted files)."""

    config = config or AppConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        rsync, rsync_error = _discover_rsync(config)
        settings = SettingsStore(config.settings_path)
        fs = FileSystem(config.roots)
        manager = JobManager(rsync=rsync, settings=settings, fs=fs)
        ctx = AppContext(config, rsync, rsync_error, settings, fs, manager)
        app.state.ctx = ctx
        await manager.start()
        if rsync:
            log.info("Using rsync %s (%s)", rsync.version, rsync.path)
        log.info("Roots: %s", ", ".join(str(r) for r in fs.roots) or "none")
        if on_ready:
            on_ready(ctx)
        try:
            yield
        finally:
            await manager.shutdown()

    app = FastAPI(
        title="RGCopy",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        SecurityHeaders, csp=DESKTOP_CONTENT_SECURITY_POLICY if config.desktop else CONTENT_SECURITY_POLICY
    )

    @app.exception_handler(ManagerError)
    async def manager_error(_: Request, exc: ManagerError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(PathError)
    async def path_error(_: Request, exc: PathError) -> JSONResponse:
        status_code = (
            403 if exc.code in ("outside_roots", "forbidden") else 404 if exc.code == "not_found" else 400
        )
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status_code)

    @app.exception_handler(ValidationError)
    async def validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse({"code": "invalid", "message": str(exc)}, status_code=422)

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router)
    app.include_router(routes.router, dependencies=[Depends(auth.require_auth)])
    app.add_api_websocket_route("/api/events", events_ws)

    static_dir = config.static_dir or STATIC_DIR
    if (Path(static_dir) / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False)
        async def missing_ui() -> HTMLResponse:
            return HTMLResponse(MISSING_UI)

    return app
