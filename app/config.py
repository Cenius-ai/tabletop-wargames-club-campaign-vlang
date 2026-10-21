"""Runtime configuration for the Tabletop Wargames Club Campaign app.

Every value has a working default so the app boots on a fresh clone with no
`.env` present. Sessions are opaque random tokens stored in SQLite, so the app
needs no signing secret to be provisioned.
"""

from __future__ import annotations

import os

APP_NAME = "Tabletop Wargames Club Campaign"
CLUB_NAME = "Hollow Gate Wargames Club"
CLUB_SHORT = "Hollow Gate"

DEFAULT_PORT = 8000
SESSION_COOKIE = "campaign_session"
SESSION_TTL_DAYS = 14
MAX_FORM_BYTES = 64 * 1024


def port() -> int:
    """Port the server binds on: $PORT with the framework default of 8000."""
    raw = os.environ.get("PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def cookie_secure() -> bool:
    """HTTPS-only cookie flag, off by default because previews run plain http."""
    return os.environ.get("COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}
