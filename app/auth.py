"""Sessions, route guards and flash messages.

A session is an opaque random token in an HttpOnly, SameSite=Lax cookie that
maps to a row in the sessions table. Every request that carries the cookie
resolves the user in :class:`LoadSessionMiddleware`, so logout and role changes
take effect immediately.
"""

from __future__ import annotations

import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import config, db, security

logger = logging.getLogger("campaign.auth")

SESSION_COOKIE = config.SESSION_COOKIE


class AuthRequired(Exception):
    """Raised by guarded handlers; converted into a redirect to /login."""

    def __init__(self, next_path: str = "/") -> None:
        self.next_path = next_path
        super().__init__(next_path)


# --------------------------------------------------------------------------- #
# session lifecycle
# --------------------------------------------------------------------------- #

def create_session(conn, user_id: int) -> str:
    token = security.new_token()
    csrf = security.new_token(24)
    created = datetime.now(timezone.utc)
    expires = created + timedelta(days=config.SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, csrf_token, created_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (token, user_id, csrf, created.isoformat(timespec="seconds"),
         expires.isoformat(timespec="seconds")),
    )
    return token


def destroy_session(conn, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired_sessions(conn) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (db.now_iso(),))


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=config.SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure(),
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _load_session(token: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Resolve a cookie token into (session_row, user_row), dropping expired rows."""
    with db.connection() as conn:
        row = db.query_one(
            conn,
            "SELECT s.token, s.user_id, s.csrf_token, s.flash, s.flash_kind, s.expires_at,"
            "       u.email, u.display_name, u.role, u.faction_id,"
            "       f.name AS faction_name, f.slug AS faction_slug"
            "  FROM sessions s"
            "  JOIN users u ON u.id = s.user_id"
            "  LEFT JOIN factions f ON f.id = u.faction_id"
            " WHERE s.token = ?",
            (token,),
        )
        if row is None:
            return None
        if row["expires_at"] <= db.now_iso():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        session = {
            "token": row["token"],
            "user_id": row["user_id"],
            "csrf_token": row["csrf_token"],
            "flash": row["flash"],
            "flash_kind": row["flash_kind"],
        }
        user = {
            "id": row["user_id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "role": row["role"],
            "faction_id": row["faction_id"],
            "faction_name": row["faction_name"],
            "faction_slug": row["faction_slug"],
        }
        return session, user


class LoadSessionMiddleware:
    """Pure-ASGI middleware that attaches session + user to ``request.state``."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state.setdefault("session", None)
        state.setdefault("user", None)

        cookie_header = ""
        for key, value in scope.get("headers", []):
            if key == b"cookie":
                cookie_header = value.decode("latin-1")
                break
        token = _cookie_value(cookie_header, SESSION_COOKIE)
        if token:
            try:
                loaded = _load_session(token)
            except Exception:  # database unavailable must not 500 the whole site
                logger.exception("could not load session")
                loaded = None
            if loaded is not None:
                state["session"], state["user"] = loaded

        await self.app(scope, receive, send)


def _cookie_value(header: str, name: str) -> str | None:
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name and value:
            return value
    return None


# --------------------------------------------------------------------------- #
# helpers used by handlers and templates
# --------------------------------------------------------------------------- #

def current_user(request: Request) -> dict[str, Any] | None:
    return getattr(request.state, "user", None)


def current_session(request: Request) -> dict[str, Any] | None:
    return getattr(request.state, "session", None)


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise AuthRequired(next_path=str(request.url.path))
    return user


def require_organiser(request: Request) -> dict[str, Any]:
    user = require_user(request)
    if user["role"] != "organiser":
        from starlette.exceptions import HTTPException

        raise HTTPException(status_code=403, detail="Only a club organiser can do that.")
    return user


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    from urllib.parse import quote

    return RedirectResponse(f"/login?next={quote(target, safe='/')}", status_code=303)


def csrf_token_for(request: Request) -> str:
    session = current_session(request)
    return session["csrf_token"] if session else ""


def csrf_valid(request: Request, form: dict[str, str]) -> bool:
    session = current_session(request)
    if not session:
        return False
    submitted = form.get("csrf_token") or ""
    return bool(submitted) and hmac.compare_digest(submitted, session["csrf_token"])


# --------------------------------------------------------------------------- #
# flash messages (stored on the session row, consumed by the next render)
# --------------------------------------------------------------------------- #

def set_flash(request: Request, message: str, kind: str = "ok") -> None:
    session = current_session(request)
    if not session:
        return
    with db.connection() as conn:
        conn.execute(
            "UPDATE sessions SET flash = ?, flash_kind = ? WHERE token = ?",
            (message, kind, session["token"]),
        )
    session["flash"] = message
    session["flash_kind"] = kind


def take_flash(request: Request) -> dict[str, str] | None:
    session = current_session(request)
    if not session or not session.get("flash"):
        return None
    message = session["flash"]
    kind = session.get("flash_kind") or "ok"
    with db.connection() as conn:
        conn.execute(
            "UPDATE sessions SET flash = NULL, flash_kind = NULL WHERE token = ?",
            (session["token"],),
        )
    session["flash"] = None
    session["flash_kind"] = None
    return {"message": message, "kind": kind}
