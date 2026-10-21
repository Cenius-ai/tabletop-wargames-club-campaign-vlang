"""Campaign map: 24 territories, member claims, organiser arbitration."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import auth, db, queries, validation
from app.templating import render


def _campaign_context(conn, user: dict, errors: dict[str, str] | None = None) -> dict:
    territories = queries.territories(conn)
    standings = queries.faction_standings(conn)
    undefended = [tile for tile in territories if tile["faction_slug"] is None]
    recent = sorted(
        (tile for tile in territories if tile["claimed_at"]),
        key=lambda tile: tile["claimed_at"],
        reverse=True,
    )[:6]
    return {
        "territories": territories,
        "standings": standings,
        "undefended_count": len(undefended),
        "held_count": len(territories) - len(undefended),
        "recent_claims": recent,
        "factions": [dict(row) for row in db.query_all(
            conn, "SELECT id, name, slug FROM factions ORDER BY name"
        )],
        "is_organiser": user["role"] == "organiser",
        "errors": errors or {},
    }


async def map_page(request: Request):
    user = auth.require_user(request)
    with db.connection() as conn:
        context = _campaign_context(conn, user)
    return render(request, "campaign.html", context)


async def claim(request: Request):
    user = auth.require_user(request)
    territory_id = int(request.path_params["territory_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    with db.connection() as conn:
        territory = db.query_one(
            conn,
            "SELECT t.id, t.name, t.controlling_faction_id, f.name AS faction_name"
            "  FROM territories t LEFT JOIN factions f ON f.id = t.controlling_faction_id"
            " WHERE t.id = ?",
            (territory_id,),
        )
        if territory is None:
            raise HTTPException(status_code=404, detail="That territory is not on the map.")

        if user["faction_id"] is None:
            return render(request, "campaign.html", _campaign_context(conn, user, {
                "form": "Pick a faction on your account before claiming territory.",
            }), status_code=200)

        if territory["controlling_faction_id"] is not None:
            return render(request, "campaign.html", _campaign_context(conn, user, {
                "form": f"{territory['name']} is already held by the "
                        f"{territory['faction_name']} — ask an organiser to arbitrate.",
            }), status_code=200)

        cursor = conn.execute(
            "UPDATE territories SET controlling_faction_id = ?, claimed_by_user_id = ?, claimed_at = ?"
            " WHERE id = ? AND controlling_faction_id IS NULL",
            (user["faction_id"], user["id"], db.now_iso(), territory_id),
        )
        if cursor.rowcount == 0:
            return render(request, "campaign.html", _campaign_context(conn, user, {
                "form": f"{territory['name']} was taken moments ago — try another territory.",
            }), status_code=200)
        faction_name = user["faction_name"] or "your faction"

    auth.set_flash(request, f"You claimed {territory['name']} for the {faction_name}.")
    return RedirectResponse("/campaign", status_code=303)


async def assign(request: Request):
    user = auth.require_organiser(request)
    territory_id = int(request.path_params["territory_id"])
    form = await validation.read_form(request)
    if not auth.csrf_valid(request, form):
        raise HTTPException(status_code=403, detail="Your session expired — please sign in again.")

    faction_slug = (form.get("faction") or "").strip()

    with db.connection() as conn:
        territory = db.query_one(conn, "SELECT id, name FROM territories WHERE id = ?",
                                 (territory_id,))
        if territory is None:
            raise HTTPException(status_code=404, detail="That territory is not on the map.")

        if not faction_slug:
            conn.execute(
                "UPDATE territories SET controlling_faction_id = NULL, claimed_by_user_id = NULL,"
                " claimed_at = NULL WHERE id = ?",
                (territory_id,),
            )
            message = f"{territory['name']} is undefended again."
        else:
            faction = db.query_one(conn, "SELECT id, name FROM factions WHERE slug = ?",
                                   (faction_slug,))
            if faction is None:
                return render(request, "campaign.html", _campaign_context(conn, user, {
                    "form": "Choose one of the four club factions.",
                }), status_code=200)
            conn.execute(
                "UPDATE territories SET controlling_faction_id = ?, claimed_by_user_id = NULL,"
                " claimed_at = ? WHERE id = ?",
                (faction["id"], db.now_iso(), territory_id),
            )
            message = f"{territory['name']} assigned to the {faction['name']}."

    auth.set_flash(request, message)
    return RedirectResponse("/campaign", status_code=303)
