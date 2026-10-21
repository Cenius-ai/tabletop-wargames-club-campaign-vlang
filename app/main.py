"""Hollow Gate Wargames Club Campaign — Starlette application.

Run it with::

    uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

The database schema and demo seed run on the normal boot path, so a fresh
clone boots straight into a populated club with no manual setup step.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app import auth, config, db
from app.auth import AuthRequired, LoadSessionMiddleware
from app.routers import army_lists, bookings, campaign, dashboard
from app.routers import auth as auth_routes
from app.templating import render

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("campaign")

STATIC_DIR = Path(__file__).resolve().parent / "static"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "style-src 'self'; "
    "script-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'"
)

SECURITY_HEADERS = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware:
    """Adds the standard hardening headers to every response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


@asynccontextmanager
async def lifespan(app: Starlette):
    db.init_db()
    logger.info("%s ready on 0.0.0.0:%s", config.APP_NAME, config.port())
    yield


async def health(request):
    return PlainTextResponse("ok")


async def root_redirect(request):
    """Kept for clarity: the dashboard route handles auth itself."""
    return RedirectResponse("/login", status_code=303)


async def auth_required_handler(request, exc: AuthRequired):
    return auth.login_redirect(request)


async def http_exception_handler(request, exc: HTTPException):
    titles = {
        400: "That request could not be understood",
        403: "Not allowed",
        404: "We could not find that page",
        413: "That submission was too large",
    }
    if exc.status_code in {301, 302, 303, 307, 308}:
        location = (exc.headers or {}).get("location", "/")
        return RedirectResponse(location, status_code=exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else titles.get(
        exc.status_code, "Something went wrong"
    )
    return render(request, "error.html", {
        "status": exc.status_code,
        "title": titles.get(exc.status_code, "Something went wrong"),
        "message": message,
    }, status_code=exc.status_code)


async def server_error_handler(request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
    return render(request, "error.html", {
        "status": 500,
        "title": "Something went wrong",
        "message": "The club server hit an unexpected problem. Try again in a moment.",
    }, status_code=500)


routes = [
    Route("/", dashboard.index, methods=["GET"]),
    Route("/health", health, methods=["GET"]),
    Route("/login", auth_routes.login_page, methods=["GET"]),
    Route("/login", auth_routes.login_submit, methods=["POST"]),
    Route("/register", auth_routes.register_page, methods=["GET"]),
    Route("/register", auth_routes.register_submit, methods=["POST"]),
    Route("/logout", auth_routes.logout, methods=["POST"]),
    Route("/army-lists", army_lists.index, methods=["GET"]),
    Route("/army-lists", army_lists.create, methods=["POST"]),
    Route("/army-lists/{list_id:int}", army_lists.detail, methods=["GET"]),
    Route("/army-lists/{list_id:int}/units", army_lists.add_unit, methods=["POST"]),
    Route("/army-lists/{list_id:int}/units/{unit_id:int}/delete", army_lists.delete_unit,
          methods=["POST"]),
    Route("/army-lists/{list_id:int}/delete", army_lists.delete_list, methods=["POST"]),
    Route("/campaign", campaign.map_page, methods=["GET"]),
    Route("/campaign/territories/{territory_id:int}/claim", campaign.claim, methods=["POST"]),
    Route("/campaign/territories/{territory_id:int}/assign", campaign.assign, methods=["POST"]),
    Route("/club-nights", bookings.club_nights_page, methods=["GET"]),
    Route("/club-nights/{night_id:int}/book", bookings.book, methods=["POST"]),
    Route("/bookings/{booking_id:int}/cancel", bookings.cancel, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

middleware = [
    Middleware(SecurityHeadersMiddleware),
    Middleware(LoadSessionMiddleware),
]

exception_handlers = {
    AuthRequired: auth_required_handler,
    HTTPException: http_exception_handler,
    500: server_error_handler,
}

app = Starlette(
    routes=routes,
    middleware=middleware,
    exception_handlers=exception_handlers,
    lifespan=lifespan,
)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=config.port(), log_level="info")
