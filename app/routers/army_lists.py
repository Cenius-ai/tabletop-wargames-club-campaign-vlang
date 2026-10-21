"""Army lists: index grouped by faction, detail with units, points enforcement."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import auth, db, queries, validation
from app.templating import render

MAX_LIST_NAME = 80
MAX_UNIT_NAME = 60


def _factions(conn) -> list[dict]:
    return [dict(row) for row in db.query_all(
        conn, "SELECT id, name, slug FROM factions ORDER BY name"
    )]


def _is_manager(user: dict, owner_id: int) -> bool:
    """Owner or club organiser may edit/delete a list."""
    return user["id"] == owner_id or user["role"] == "organiser"


def _detail_context(conn, user: dict, army_list: dict) -> dict:
    units = queries.army_list_units(conn, army_list["id"])
    total = sum(int(unit["subtotal"]) for unit in units)
    limit = int(army_list["points_limit"])
    return {
        "army_list": army_list,
        "units": units,
        "total_points": total,
        "remaining": max(limit - total, 0),
        "over_limit": total > limit,
        "near_limit": limit - total <= max(limit * 0.1, 25),
        "can_manage": _is_manager(user, army_list["owner_id"]),
        "navigator": queries.army_lists_with_totals(conn, owner_id=user["id"]),
        "unit_kinds": validation.UNIT_KINDS,
        "errors": {},
        "values": {"kind": validation.UNIT_KINDS[0]},
    }


async def index(request: Request):
    user = auth.require_user(request)
    with db.connection() as conn:
        lists = queries.army_lists_with_totals(conn)
        factions = _factions(conn)
    groups = queries.group_by_faction(lists)
    return render(request, "army_lists.html", {
        "groups": groups,
        "factions": factions,
        "list_count": len(lists),
        "errors": {},
        "values": {"faction": user["faction_slug"] or (factions[0]["slug"] if factions else ""),
                   "points_limit": "1000"},
    })


async def create(request: Request):
    user = auth.require_user(request)
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    errors: dict[str, str] = {}
    name = validation.text_value(form, "name", errors, label="List name", min_length=3,
                                 max_length=MAX_LIST_NAME)
    limit = validation.int_value(form, "points_limit", errors, label="Points limit",
                                 minimum=50, maximum=10000)
    notes = validation.optional_text(form, "notes", errors, label="Notes", max_length=300)

    with db.connection() as conn:
        factions = _factions(conn)
        slugs = [faction["slug"] for faction in factions]
        faction_slug = validation.choice_value(form, "faction", errors, label="faction",
                                               allowed=slugs)
        values = {"name": name, "points_limit": form.get("points_limit", ""),
                  "faction": faction_slug, "notes": notes or ""}

        if errors:
            lists = queries.army_lists_with_totals(conn)
            return render(request, "army_lists.html", {
                "groups": queries.group_by_faction(lists),
                "factions": factions,
                "list_count": len(lists),
                "errors": errors,
                "values": values,
            }, status_code=200)

        faction_id = int(next(f["id"] for f in factions if f["slug"] == faction_slug))
        cursor = conn.execute(
            "INSERT INTO army_lists (owner_id, faction_id, name, points_limit, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], faction_id, name, limit, notes, db.now_iso()),
        )
        new_id = int(cursor.lastrowid)

    auth.set_flash(request, f"Army list “{name}” created — add your first unit.")
    return RedirectResponse(f"/army-lists/{new_id}", status_code=303)


async def detail(request: Request):
    user = auth.require_user(request)
    list_id = int(request.path_params["list_id"])
    with db.connection() as conn:
        army_list = queries.get_army_list(conn, list_id)
        if army_list is None:
            raise HTTPException(status_code=404, detail="That army list does not exist.")
        context = _detail_context(conn, user, army_list)
    return render(request, "army_list_detail.html", context)


async def add_unit(request: Request):
    user = auth.require_user(request)
    list_id = int(request.path_params["list_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    errors: dict[str, str] = {}
    unit_name = validation.text_value(form, "name", errors, label="Unit name", min_length=2,
                                      max_length=MAX_UNIT_NAME)
    kind = validation.choice_value(form, "kind", errors, label="unit kind",
                                   allowed=validation.UNIT_KINDS)
    points = validation.int_value(form, "points", errors, label="Points per model",
                                  minimum=0, maximum=2000)
    qty = validation.int_value(form, "qty", errors, label="Models", minimum=1, maximum=100)
    values = {"name": unit_name, "kind": kind, "points": form.get("points", ""),
              "qty": form.get("qty", "")}

    with db.connection() as conn:
        army_list = queries.get_army_list(conn, list_id)
        if army_list is None:
            raise HTTPException(status_code=404, detail="That army list does not exist.")
        if not _is_manager(user, army_list["owner_id"]):
            raise HTTPException(status_code=403, detail="You can only edit your own army lists.")

        if not errors:
            units = queries.army_list_units(conn, list_id)
            current_total = sum(int(unit["subtotal"]) for unit in units)
            added = points * qty
            resulting = current_total + added
            if resulting > int(army_list["points_limit"]):
                errors["points"] = (
                    f"That would take the list to {resulting:,} of "
                    f"{int(army_list['points_limit']):,} pts — remove something first."
                )

        if errors:
            context = _detail_context(conn, user, army_list)
            context["errors"] = errors
            context["values"] = values
            return render(request, "army_list_detail.html", context, status_code=200)

        conn.execute(
            "INSERT INTO units (army_list_id, name, kind, points, qty) VALUES (?, ?, ?, ?, ?)",
            (list_id, unit_name, kind, points, qty),
        )
        total_after = sum(int(unit["subtotal"]) for unit in queries.army_list_units(conn, list_id))

    auth.set_flash(request, f"Added {unit_name} — {total_after:,} of "
                            f"{int(army_list['points_limit']):,} pts used.")
    return RedirectResponse(f"/army-lists/{list_id}", status_code=303)


async def delete_unit(request: Request):
    user = auth.require_user(request)
    list_id = int(request.path_params["list_id"])
    unit_id = int(request.path_params["unit_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    with db.connection() as conn:
        army_list = queries.get_army_list(conn, list_id)
        if army_list is None:
            raise HTTPException(status_code=404, detail="That army list does not exist.")
        if not _is_manager(user, army_list["owner_id"]):
            raise HTTPException(status_code=403, detail="You can only edit your own army lists.")
        unit = db.query_one(conn, "SELECT id, name FROM units WHERE id = ? AND army_list_id = ?",
                            (unit_id, list_id))
        if unit is None:
            raise HTTPException(status_code=404, detail="That unit is not on this list.")
        conn.execute("DELETE FROM units WHERE id = ? AND army_list_id = ?", (unit_id, list_id))
        remaining_total = sum(
            int(item["subtotal"]) for item in queries.army_list_units(conn, list_id)
        )

    auth.set_flash(request, f"Removed {unit['name']} — list is now {remaining_total:,} pts.")
    return RedirectResponse(f"/army-lists/{list_id}", status_code=303)


async def delete_list(request: Request):
    user = auth.require_user(request)
    list_id = int(request.path_params["list_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    with db.connection() as conn:
        army_list = queries.get_army_list(conn, list_id)
        if army_list is None:
            raise HTTPException(status_code=404, detail="That army list does not exist.")
        if not _is_manager(user, army_list["owner_id"]):
            raise HTTPException(status_code=403, detail="You can only delete your own army lists.")
        conn.execute("DELETE FROM army_lists WHERE id = ?", (list_id,))

    auth.set_flash(request, f"Army list “{army_list['name']}” deleted.")
    return RedirectResponse("/army-lists", status_code=303)
