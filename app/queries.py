"""Read queries shared by more than one screen."""

from __future__ import annotations

from typing import Any, Iterable

from app import db

LIST_SELECT = """
SELECT al.id, al.owner_id, al.faction_id, al.name, al.points_limit, al.notes, al.created_at,
       f.name AS faction_name, f.slug AS faction_slug,
       u.display_name AS owner_name,
       COALESCE(SUM(un.points * un.qty), 0) AS total_points,
       COALESCE(SUM(un.qty), 0)             AS model_count,
       COUNT(un.id)                          AS unit_count
  FROM army_lists al
  JOIN factions f ON f.id = al.faction_id
  JOIN users u ON u.id = al.owner_id
  LEFT JOIN units un ON un.army_list_id = al.id
"""


def army_lists_with_totals(conn, owner_id: int | None = None) -> list[dict[str, Any]]:
    """Every army list (or one member's lists) with its live points total."""
    if owner_id is None:
        sql = LIST_SELECT + " GROUP BY al.id ORDER BY f.name, al.name"
        rows = db.query_all(conn, sql)
    else:
        sql = LIST_SELECT + " WHERE al.owner_id = ? GROUP BY al.id ORDER BY f.name, al.name"
        rows = db.query_all(conn, sql, (owner_id,))
    return [dict(row) for row in rows]


def get_army_list(conn, list_id: int) -> dict[str, Any] | None:
    row = db.query_one(conn, LIST_SELECT + " WHERE al.id = ? GROUP BY al.id", (list_id,))
    return dict(row) if row is not None else None


def army_list_units(conn, list_id: int) -> list[dict[str, Any]]:
    rows = db.query_all(
        conn,
        "SELECT id, name, kind, points, qty, (points * qty) AS subtotal"
        "  FROM units WHERE army_list_id = ? ORDER BY kind, name",
        (list_id,),
    )
    return [dict(row) for row in rows]


def group_by_faction(lists: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group army lists into per-faction blocks, preserving faction name order."""
    groups: dict[str, dict[str, Any]] = {}
    for army_list in lists:
        key = army_list["faction_slug"]
        group = groups.setdefault(
            key,
            {"slug": key, "name": army_list["faction_name"], "lists": [], "total_points": 0},
        )
        group["lists"].append(army_list)
        group["total_points"] += int(army_list["total_points"] or 0)
    return list(groups.values())


def faction_standings(conn) -> list[dict[str, Any]]:
    rows = db.query_all(
        conn,
        "SELECT f.id, f.name, f.slug, f.colour, f.motto,"
        "       (SELECT COUNT(*) FROM territories t WHERE t.controlling_faction_id = f.id) AS held"
        "  FROM factions f ORDER BY f.name",
    )
    return [dict(row) for row in rows]


def territories(conn) -> list[dict[str, Any]]:
    rows = db.query_all(
        conn,
        "SELECT t.id, t.name, t.x, t.y, t.claimed_at,"
        "       f.name AS faction_name, f.slug AS faction_slug,"
        "       u.display_name AS claimant_name"
        "  FROM territories t"
        "  LEFT JOIN factions f ON f.id = t.controlling_faction_id"
        "  LEFT JOIN users u ON u.id = t.claimed_by_user_id"
        "  ORDER BY t.y, t.x",
    )
    return [dict(row) for row in rows]


def club_nights_with_counts(conn, from_date: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        conn,
        "SELECT cn.id, cn.date, cn.title, cn.location, cn.notes,"
        "       (SELECT COUNT(*) FROM bookings b WHERE b.club_night_id = cn.id) AS booked_count,"
        "       (SELECT COUNT(*) FROM \"tables\") AS table_count"
        "  FROM club_nights cn WHERE cn.date >= ? ORDER BY cn.date",
        (from_date,),
    )
    return [dict(row) for row in rows]


def night_tables(conn, night_id: int) -> list[dict[str, Any]]:
    rows = db.query_all(
        conn,
        "SELECT t.id, t.label, t.capacity,"
        "       b.id AS booking_id, b.user_id AS booked_user_id, b.notes AS booking_notes,"
        "       u.display_name AS booked_by, al.name AS army_list_name"
        "  FROM \"tables\" t"
        "  LEFT JOIN bookings b ON b.table_id = t.id AND b.club_night_id = ?"
        "  LEFT JOIN users u ON u.id = b.user_id"
        "  LEFT JOIN army_lists al ON al.id = b.army_list_id"
        "  ORDER BY t.label",
        (night_id,),
    )
    return [dict(row) for row in rows]
