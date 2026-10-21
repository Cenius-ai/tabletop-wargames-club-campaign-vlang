"""Jinja2 wiring: one template environment, shared context and display filters."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from starlette.templating import Jinja2Templates

from app import auth, config

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --------------------------------------------------------------------------- #
# display filters
# --------------------------------------------------------------------------- #

def fmt_points(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def fmt_short_date(value: Any) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%a %d %b").replace(" 0", " ")


def fmt_long_date(value: Any) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%A %d %B %Y").replace(" 0", " ")


def fmt_clock(value: Any) -> str:
    """Humanised timestamp: just now / N minutes ago / N days ago / a date."""
    if not value:
        return "—"
    if isinstance(value, date) and not isinstance(value, datetime):
        return fmt_short_date(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return fmt_short_date(value)
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if seconds < 86400 * 7:
        days = int(seconds // 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    return parsed.strftime("%d %b %Y").lstrip("0")


def fmt_initials(name: Any) -> str:
    parts = [part for part in str(name or "").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def fmt_percent(part: Any, whole: Any) -> int:
    try:
        whole_value = int(whole)
        if whole_value <= 0:
            return 0
        return max(0, min(100, round(int(part) * 100 / whole_value)))
    except (TypeError, ValueError):
        return 0


templates.env.filters["points"] = fmt_points
templates.env.filters["short_date"] = fmt_short_date
templates.env.filters["long_date"] = fmt_long_date
templates.env.filters["clock"] = fmt_clock
templates.env.filters["initials"] = fmt_initials
templates.env.filters["percent"] = fmt_percent
templates.env.globals.update(app_name=config.APP_NAME, club_name=config.CLUB_NAME,
                            club_short=config.CLUB_SHORT)


# --------------------------------------------------------------------------- #
# render helper
# --------------------------------------------------------------------------- #

def render(request, template_name: str, context: dict[str, Any] | None = None,
           *, status_code: int = 200, headers: dict[str, str] | None = None):
    ctx: dict[str, Any] = {
        "user": auth.current_user(request),
        "csrf_token": auth.csrf_token_for(request),
        "flash": auth.take_flash(request),
        "today": date.today(),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(
        request, template_name, ctx, status_code=status_code, headers=headers
    )
