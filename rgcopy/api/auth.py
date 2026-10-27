"""Token authentication: an HttpOnly session cookie or an ``Authorization: Bearer`` header."""

from __future__ import annotations

import hmac
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from starlette.requests import HTTPConnection

COOKIE_NAME = "rgcopy_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

router = APIRouter()


class LoginRequest(BaseModel):
    token: str


def _expected_token(conn: HTTPConnection) -> str | None:
    token: str | None = conn.app.state.ctx.config.auth_token
    return token


def _supplied_tokens(conn: HTTPConnection) -> list[str]:
    """Every credential the request carries: Bearer header, session cookie, WebSocket ``?token``."""

    tokens = []
    scheme, _, value = conn.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        tokens.append(value.strip())
    cookie = conn.cookies.get(COOKIE_NAME)
    if cookie:
        tokens.append(cookie)
    if conn.scope["type"] == "websocket" and conn.query_params.get("token"):
        tokens.append(conn.query_params["token"])
    return tokens


def _matches(supplied: str | None, expected: str) -> bool:
    return bool(supplied) and hmac.compare_digest(str(supplied).encode(), expected.encode())


def is_authenticated(conn: HTTPConnection) -> bool:
    expected = _expected_token(conn)
    # Any valid credential is enough: a stale cookie must not mask a fresh Bearer token
    return expected is None or any(_matches(token, expected) for token in _supplied_tokens(conn))


def origin_allowed(conn: HTTPConnection) -> bool:
    """Reject cross-site WebSocket handshakes (browsers always send Origin)."""

    origin = conn.headers.get("origin")
    if not origin:
        return True
    extra = {
        o.strip().rstrip("/") for o in os.environ.get("RGCOPY_ALLOWED_ORIGINS", "").split(",") if o.strip()
    }
    if origin.rstrip("/") in extra:
        return True
    return urlsplit(origin).netloc == conn.headers.get("host", "")


async def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


def _set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, bool]:
    return {"required": _expected_token(request) is not None, "authenticated": is_authenticated(request)}


@router.post("/api/auth/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(payload: LoginRequest, request: Request, response: Response) -> None:
    expected = _expected_token(request)
    if expected is None:
        return
    if not _matches(payload.token.strip(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    _set_session(response, request, expected)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth", include_in_schema=False)
async def auth_link(request: Request, token: str = "") -> RedirectResponse:
    """One-click login used by the desktop launcher and the URL printed by ``rgcopy serve``."""

    expected = _expected_token(request)
    if expected is not None and not _matches(token, expected):
        return RedirectResponse("/?auth=failed", status_code=status.HTTP_303_SEE_OTHER)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    if expected is not None:
        _set_session(response, request, expected)
    return response
