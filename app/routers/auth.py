"""Registration, sign-in and sign-out."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import auth, db, security, validation
from app.templating import render

logger = logging.getLogger("campaign.auth")

# In-process, windowed brute-force guard: one boot, one process, no extra store.
LOGIN_LIMIT = 40
LOGIN_WINDOW_SECONDS = 300
_login_attempts: dict[str, list[float]] = {}
_DUMMY_HASH = security.hash_password("not-a-real-password")


def _client_key(request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    return f"login:{client}"


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    stamps = [stamp for stamp in _login_attempts.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    _login_attempts[key] = stamps
    return len(stamps) >= LOGIN_LIMIT


def _record_attempt(key: str) -> None:
    _login_attempts.setdefault(key, []).append(time.monotonic())


def safe_next(raw: str | None) -> str:
    """Only same-origin absolute paths are honoured as a post-login destination."""
    if not raw:
        return "/"
    cleaned = raw.strip()
    if not cleaned.startswith("/") or cleaned.startswith("//"):
        return "/"
    return cleaned


def _factions(conn) -> list[dict]:
    return [dict(row) for row in db.query_all(conn, "SELECT id, name, slug FROM factions ORDER BY name")]


def _faction_id_for_slug(conn, slug: str) -> int | None:
    row = db.query_one(conn, "SELECT id FROM factions WHERE slug = ?", (slug,))
    return int(row["id"]) if row else None


def login_url_for(next_path: str) -> str:
    return f"/login?next={quote(next_path, safe='/')}"


async def login_page(request: Request):
    if auth.current_user(request):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", {
        "next_path": safe_next(request.query_params.get("next")),
        "values": {"email": ""},
        "errors": {},
    })


async def login_submit(request: Request):
    form = await validation.read_form(request)
    # The demo quick-sign-in buttons post dedicated field names so they never
    # collide with the real email/password inputs.
    email = (form.get("email") or form.get("demo_email") or "").strip().lower()
    password = form.get("password") or form.get("demo_password") or ""
    next_path = safe_next(form.get("next"))
    values = {"email": email, "next_path": next_path}
    key = _client_key(request)

    if _rate_limited(key):
        return render(request, "login.html", {
            "values": values,
            "errors": {"form": "Too many sign-in attempts. Wait a few minutes and try again."},
        }, status_code=429)

    def failed():
        _record_attempt(key)
        return render(request, "login.html", {
            "values": values,
            "errors": {"form": "Email or password is not correct."},
        })

    if not email or not password:
        return failed()

    with db.connection() as conn:
        row = db.query_one(conn, "SELECT id, password_hash FROM users WHERE email = ?", (email,))
        if row is None:
            security.verify_password(password, _DUMMY_HASH)  # keep the timing even
            return failed()
        if not security.verify_password(password, row["password_hash"]):
            return failed()
        auth.purge_expired_sessions(conn)
        token = auth.create_session(conn, int(row["id"]))

    response = RedirectResponse(next_path, status_code=303)
    auth.set_session_cookie(response, token)
    return response


async def register_page(request: Request):
    if auth.current_user(request):
        return RedirectResponse("/", status_code=303)
    with db.connection() as conn:
        factions = _factions(conn)
        club_is_new = (db.query_scalar(conn, "SELECT COUNT(*) FROM users") or 0) == 0
    return render(request, "register.html", {
        "factions": factions,
        "club_is_new": club_is_new,
        "values": {"display_name": "", "email": "", "faction": factions[0]["slug"] if factions else ""},
        "errors": {},
    })


async def register_submit(request: Request):
    form = await validation.read_form(request)
    errors: dict[str, str] = {}

    with db.connection() as conn:
        factions = _factions(conn)
        slugs = [faction["slug"] for faction in factions]
        display_name = validation.text_value(
            form, "display_name", errors, label="Display name", min_length=2, max_length=60
        )
        email = validation.email_value(form, "email", errors)
        password = validation.password_value(form, "password", errors)
        faction_slug = validation.choice_value(
            form, "faction", errors, label="faction", allowed=slugs
        )

        values = {"display_name": display_name, "email": email, "faction": faction_slug}
        if email and db.query_one(conn, "SELECT id FROM users WHERE email = ?", (email,)):
            errors["email"] = "That email is already registered — sign in instead."

        if errors:
            club_is_new = (db.query_scalar(conn, "SELECT COUNT(*) FROM users") or 0) == 0
            return render(request, "register.html", {
                "factions": factions,
                "club_is_new": club_is_new,
                "values": values,
                "errors": errors,
            }, status_code=200)

        first_account = (db.query_scalar(conn, "SELECT COUNT(*) FROM users") or 0) == 0
        role = "organiser" if first_account else "member"
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, display_name, faction_id, role, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (email, security.hash_password(password), display_name,
             _faction_id_for_slug(conn, faction_slug), role, db.now_iso()),
        )
        user_id = int(cursor.lastrowid)
        token = auth.create_session(conn, user_id)
        faction_name = db.query_scalar(conn, "SELECT name FROM factions WHERE slug = ?",
                                       (faction_slug,))
        welcome = (
            "Welcome to the club — as the first account you are the organiser."
            if first_account
            else f"Welcome to the campaign, {display_name} of the {faction_name}."
        )
        conn.execute(
            "UPDATE sessions SET flash = ?, flash_kind = 'ok' WHERE token = ?", (welcome, token)
        )

    logger.info("registered member id=%s role=%s", user_id, role)
    response = RedirectResponse("/", status_code=303)
    auth.set_session_cookie(response, token)
    return response


async def logout(request: Request):
    auth.require_user(request)
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in and try again.")
    session = auth.current_session(request)
    with db.connection() as conn:
        auth.destroy_session(conn, session["token"])
    response = RedirectResponse("/login", status_code=303)
    auth.clear_session_cookie(response)
    return response
