"""Club nights: table grid, booking and cancellation."""

from __future__ import annotations

import sqlite3
from datetime import date

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import auth, db, queries, validation
from app.templating import render


def _return_path(raw: str | None, default: str = "/club-nights") -> str:
    cleaned = (raw or "").strip()
    if cleaned in {"/", default}:
        return cleaned
    if cleaned.startswith("/club-nights"):
        return cleaned
    return default


def _nights_context(conn, user: dict, night_id: int | None = None,
                    errors: dict[str, str] | None = None,
                    values: dict[str, str] | None = None) -> dict:
    nights = queries.club_nights_with_counts(conn, date.today().isoformat())
    selected = None
    if nights:
        if night_id is not None:
            selected = next((night for night in nights if night["id"] == night_id), None)
        if selected is None:
            selected = nights[0]

    tables = queries.night_tables(conn, selected["id"]) if selected else []
    free_tables = [table for table in tables if table["booking_id"] is None]
    my_booking = next((t for t in tables if t["booked_user_id"] == user["id"]), None)
    my_lists = queries.army_lists_with_totals(conn, owner_id=user["id"])

    return {
        "nights": nights,
        "selected": selected,
        "tables": tables,
        "free_tables": free_tables,
        "my_booking": my_booking,
        "my_lists": my_lists,
        "is_organiser": user["role"] == "organiser",
        "errors": errors or {},
        "values": values or {"army_list_id": "", "notes": ""},
    }


async def club_nights_page(request: Request):
    user = auth.require_user(request)
    raw_night = (request.query_params.get("night") or "").strip()
    night_id = int(raw_night) if raw_night.isdigit() else None
    with db.connection() as conn:
        context = _nights_context(conn, user, night_id)
    return render(request, "club_nights.html", context)


async def book(request: Request):
    user = auth.require_user(request)
    night_id = int(request.path_params["night_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    errors: dict[str, str] = {}
    raw_table = (form.get("table_id") or "").strip()
    table_id = int(raw_table) if raw_table.isdigit() else None
    raw_list = (form.get("army_list_id") or "").strip()
    army_list_id = int(raw_list) if raw_list.isdigit() else None
    note = validation.optional_text(form, "notes", errors, label="Note", max_length=200)
    values = {"army_list_id": raw_list, "notes": note or ""}

    with db.connection() as conn:
        night = db.query_one(
            conn, "SELECT id, date, title, location FROM club_nights WHERE id = ?", (night_id,)
        )
        if night is None:
            raise HTTPException(status_code=404, detail="That club night is not scheduled.")

        if night["date"] < date.today().isoformat():
            errors["form"] = "That club night has already happened."
        elif table_id is None:
            errors["form"] = "Choose a table to book."
        else:
            tables = queries.night_tables(conn, night_id)
            free_ids = {t["id"] for t in tables if t["booking_id"] is None}
            if not free_ids:
                errors["form"] = f"All {len(tables)} tables are booked for {night['date']}."
            elif table_id not in free_ids:
                chosen = next((t for t in tables if t["id"] == table_id), None)
                label = chosen["label"] if chosen else "That table"
                errors["form"] = f"{label} is already booked for {night['date']} — pick a free one."
            elif any(t["booked_user_id"] == user["id"] for t in tables):
                errors["form"] = "You already have a table that night — cancel it first to move tables."

        if not errors and army_list_id is not None:
            owned = db.query_one(
                conn, "SELECT id FROM army_lists WHERE id = ? AND owner_id = ?",
                (army_list_id, user["id"]),
            )
            if owned is None:
                errors["army_list_id"] = "Pick one of your own army lists, or leave it blank."
                army_list_id = None

        if errors:
            context = _nights_context(conn, user, night_id, errors, values)
            return render(request, "club_nights.html", context, status_code=200)

        try:
            conn.execute(
                "INSERT INTO bookings (club_night_id, table_id, user_id, army_list_id, notes, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (night_id, table_id, user["id"], army_list_id, note, db.now_iso()),
            )
        except sqlite3.IntegrityError:
            context = _nights_context(conn, user, night_id, {
                "form": "That table was booked by someone else a moment ago — pick another."
            }, values)
            return render(request, "club_nights.html", context, status_code=200)

        label = db.query_scalar(conn, 'SELECT label FROM "tables" WHERE id = ?', (table_id,))

    auth.set_flash(request, f"Table {label} booked for {night['date']} — see you there.")
    return RedirectResponse(f"/club-nights?night={night_id}", status_code=303)


async def cancel(request: Request):
    user = auth.require_user(request)
    booking_id = int(request.path_params["booking_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")
    return_to = _return_path(form.get("return_to"))

    with db.connection() as conn:
        booking = db.query_one(
            conn,
            "SELECT b.id, b.user_id, b.club_night_id, t.label, cn.date, u.display_name"
            "  FROM bookings b"
            "  JOIN \"tables\" t ON t.id = b.table_id"
            "  JOIN club_nights cn ON cn.id = b.club_night_id"
            "  JOIN users u ON u.id = b.user_id"
            " WHERE b.id = ?",
            (booking_id,),
        )
        if booking is None:
            raise HTTPException(status_code=404, detail="That booking no longer exists.")
        if booking["user_id"] != user["id"] and user["role"] != "organiser":
            raise HTTPException(
                status_code=403,
                detail="You can only cancel your own bookings — ask an organiser to help.",
            )
        conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))

    if booking["user_id"] == user["id"]:
        message = f"Booking cancelled — {booking['label']} is free again for {booking['date']}."
    else:
        message = (f"Cancelled {booking['display_name']}'s booking — {booking['label']} is free"
                   f" again for {booking['date']}.")
    auth.set_flash(request, message)
    return RedirectResponse(return_to, status_code=303)
