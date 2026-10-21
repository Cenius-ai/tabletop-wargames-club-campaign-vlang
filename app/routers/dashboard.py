"""Personal dashboard: everything a member needs in one screen."""

from __future__ import annotations

from datetime import date

from starlette.requests import Request

from app import auth, db, queries
from app.templating import render


def _upcoming_bookings(conn, user_id: int) -> list[dict]:
    rows = db.query_all(
        conn,
        "SELECT b.id, b.notes, cn.id AS night_id, cn.date, cn.title, cn.location,"
        "       t.label AS table_label, al.name AS army_list_name"
        "  FROM bookings b"
        "  JOIN club_nights cn ON cn.id = b.club_night_id"
        "  JOIN \"tables\" t ON t.id = b.table_id"
        "  LEFT JOIN army_lists al ON al.id = b.army_list_id"
        " WHERE b.user_id = ? AND cn.date >= ?"
        " ORDER BY cn.date",
        (user_id, date.today().isoformat()),
    )
    return [dict(row) for row in rows]


def _club_totals(conn) -> dict:
    return {
        "members": db.query_scalar(conn, "SELECT COUNT(*) FROM users") or 0,
        "lists": db.query_scalar(conn, "SELECT COUNT(*) FROM army_lists") or 0,
        "undefended": db.query_scalar(
            conn, "SELECT COUNT(*) FROM territories WHERE controlling_faction_id IS NULL"
        ) or 0,
        "bookings": db.query_scalar(
            conn,
            "SELECT COUNT(*) FROM bookings b JOIN club_nights cn ON cn.id = b.club_night_id"
            " WHERE cn.date >= ?",
            (date.today().isoformat(),),
        ) or 0,
    }


async def index(request: Request):
    user = auth.require_user(request)
    today = date.today().isoformat()

    with db.connection() as conn:
        my_lists = queries.army_lists_with_totals(conn, owner_id=user["id"])
        faction = None
        if user["faction_id"] is not None:
            row = db.query_one(
                conn,
                "SELECT id, name, slug, colour, motto FROM factions WHERE id = ?",
                (user["faction_id"],),
            )
            faction = dict(row) if row else None
        held = 0
        if faction:
            held = db.query_scalar(
                conn, "SELECT COUNT(*) FROM territories WHERE controlling_faction_id = ?",
                (faction["id"],),
            ) or 0
        claimable = db.query_scalar(
            conn, "SELECT COUNT(*) FROM territories WHERE controlling_faction_id IS NULL"
        ) or 0
        bookings = _upcoming_bookings(conn, user["id"])
        nights = queries.club_nights_with_counts(conn, today)
        next_night = nights[0] if nights else None
        totals = _club_totals(conn) if user["role"] == "organiser" else None

    committed = sum(int(item["total_points"]) for item in my_lists)
    capacity = sum(int(item["points_limit"]) for item in my_lists)

    return render(request, "dashboard.html", {
        "my_lists": my_lists,
        "faction": faction,
        "held_territories": held,
        "claimable_territories": claimable,
        "bookings": bookings,
        "next_night": next_night,
        "totals": totals,
        "committed_points": committed,
        "points_capacity": capacity,
    })
