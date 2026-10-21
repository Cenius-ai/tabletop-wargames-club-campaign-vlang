"""Server-side form validation shared by every mutating route.

Each helper records a field-level message in ``errors`` and returns ``None``
when the value is unusable, so handlers can re-render the form at HTTP 200 with
the values the member typed still in place.
"""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

UNIT_KINDS = ("Infantry", "Cavalry", "Elite", "Hero", "War Machine", "Monster")


async def read_form(request) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body (no python-multipart needed)."""
    from starlette.exceptions import HTTPException

    from app import config

    body = await request.body()
    if len(body) > config.MAX_FORM_BYTES:
        raise HTTPException(status_code=413, detail="That form submission is too large.")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    from urllib.parse import parse_qs

    parsed = parse_qs(text, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def text_value(
    form: dict[str, str],
    field: str,
    errors: dict[str, str],
    *,
    label: str,
    min_length: int = 1,
    max_length: int = 120,
) -> str:
    raw = (form.get(field) or "").strip()
    if len(raw) < min_length:
        errors[field] = f"{label} is required." if min_length <= 1 else f"{label} is too short."
        return raw
    if len(raw) > max_length:
        errors[field] = f"{label} must be {max_length} characters or fewer."
        return raw[:max_length]
    return raw


def optional_text(
    form: dict[str, str],
    field: str,
    errors: dict[str, str],
    *,
    label: str,
    max_length: int = 200,
) -> str | None:
    raw = (form.get(field) or "").strip()
    if not raw:
        return None
    if len(raw) > max_length:
        errors[field] = f"{label} must be {max_length} characters or fewer."
        return raw[:max_length]
    return raw


def int_value(
    form: dict[str, str],
    field: str,
    errors: dict[str, str],
    *,
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    raw = (form.get(field) or "").strip()
    if not raw:
        errors[field] = f"{label} is required."
        return None
    try:
        value = int(raw)
    except ValueError:
        errors[field] = f"{label} must be a whole number."
        return None
    if minimum is not None and value < minimum:
        errors[field] = f"{label} must be at least {minimum}."
        return None
    if maximum is not None and value > maximum:
        errors[field] = f"{label} must be {maximum} or less."
        return None
    return value


def choice_value(
    form: dict[str, str],
    field: str,
    errors: dict[str, str],
    *,
    label: str,
    allowed: tuple[str, ...] | list[str],
) -> str:
    raw = (form.get(field) or "").strip()
    if raw not in allowed:
        errors[field] = f"Choose a {label}."
        return allowed[0]
    return raw


def email_value(form: dict[str, str], field: str, errors: dict[str, str]) -> str:
    raw = (form.get(field) or "").strip().lower()
    if not raw:
        errors[field] = "Email is required."
        return raw
    if len(raw) > 120 or not EMAIL_RE.match(raw):
        errors[field] = "Enter a valid email address, like rowan@ironvale.club."
        return raw
    return raw


def password_value(form: dict[str, str], field: str, errors: dict[str, str]) -> str:
    raw = form.get(field) or ""
    if not raw:
        errors[field] = "Password is required."
        return raw
    if len(raw) < 8:
        errors[field] = "Use at least 8 characters for your password."
        return raw
    if len(raw) > 200:
        errors[field] = "That password is too long (200 characters maximum)."
        return raw[:200]
    return raw


def first_error(errors: dict[str, str]) -> str | None:
    for message in errors.values():
        return message
    return None


def as_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}
