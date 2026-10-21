"""Idempotent demo seed: factions, map, club nights, demo accounts, army lists.

Runs automatically on the normal boot path (see ``app.db.init_db``) and can be
re-run safely by hand: ``python3 -m app.seed``. It skips itself when the club
already has accounts, so restarts never duplicate data, and it never starts the
HTTP server.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app import db, security

logger = logging.getLogger("campaign.seed")

FACTIONS = (
    ("Ironvale Compact", "ironvale", "#528a54", "Hold the line, hold the ford."),
    ("Ashen Choir", "ashen-choir", "#7a4d8f", "Every silence is a hymn."),
    ("Saltmarsh Freeblades", "saltmarsh", "#b06a2c", "Paid in silver, sworn to none."),
    ("Obsidian Pact", "obsidian-pact", "#3a4a63", "The deep remembers."),
)

# display name, email, password, role, faction slug
USERS = (
    ("Cenius Vale", "cenius@cenius.ai", "cenius", "organiser", "ironvale"),
    ("Rowan Ashby", "rowan@ironvale.club", "wargames", "member", "ironvale"),
    ("Marek Dolan", "marek@ashenchoir.club", "wargames", "member", "ashen-choir"),
)

# name, x, y, faction slug (or None), claimant email (or None), days since claim
TERRITORIES = (
    ("Hollow Gate", 0, 0, "ironvale", "cenius@cenius.ai", 12),
    ("Ashfall Ford", 1, 0, None, None, None),
    ("Greyfen Marsh", 2, 0, "saltmarsh", None, 9),
    ("Iron Bridge", 3, 0, "ironvale", "rowan@ironvale.club", 7),
    ("Warden's Rest", 4, 0, None, None, None),
    ("Saltcliff", 5, 0, None, None, None),
    ("Thornwood", 6, 0, "ashen-choir", "marek@ashenchoir.club", 5),
    ("Blackreef", 7, 0, None, None, None),
    ("Copper Hollow", 0, 1, None, None, None),
    ("Nettleford", 1, 1, None, None, None),
    ("Sable Ridge", 2, 1, "obsidian-pact", None, 3),
    ("Vane's Crossing", 3, 1, None, None, None),
    ("Marrow Bog", 4, 1, None, None, None),
    ("Old Kestrel Keep", 5, 1, "ironvale", None, 2),
    ("Harrow Point", 6, 1, None, None, None),
    ("Mistvale", 7, 1, None, None, None),
    ("Tallow Creek", 0, 2, None, None, None),
    ("Redstone Quarry", 1, 2, None, None, None),
    ("Cinder Pass", 2, 2, None, None, None),
    ("Dunmoor", 3, 2, None, None, None),
    ("Gullhaven", 4, 2, None, None, None),
    ("Bramble Hill", 5, 2, None, None, None),
    ("Sundered Bridge", 6, 2, None, None, None),
    ("Last Lantern", 7, 2, None, None, None),
)

TABLES = (
    ("Table 1", 4),
    ("Table 2", 4),
    ("Table 3", 4),
    ("Table 4", 4),
    ("Table 5", 6),
    ("Table 6", 8),
)

# days from today, title, location, notes
CLUB_NIGHTS = (
    (3, "Club Night — Escalation League Round 3", "The Old Library, Room 2",
     "500-point games. Bring two printed copies of your list and your dice."),
    (10, "Painting Bench & Pick-Up Games", "The Old Library, Room 2",
     "Brush bar opens at 18:00. Loan armies available for anyone trying a new faction."),
    (17, "Campaign Night: The Hollow Gate", "The Old Library, Main Hall",
     "Territory battles count double this week. Organiser table handles disputes."),
    (24, "Newcomer Intro Night", "The Old Library, Room 2",
     "No experience needed. We start with a 30-minute rules walkthrough at 18:30."),
    (31, "Season Finale — 2000pt Clash", "The Old Library, Main Hall",
     "Doors 17:30, first round 18:15. Bring terrain if you have any."),
)

# name, owner email, faction slug, points limit, notes, units (name, kind, points/model, models)
ARMY_LISTS = (
    ("Fourth Company Spearhead", "rowan@ironvale.club", "ironvale", 500,
     "Escalation league list. Built to hold the centre and shoot the flanks.",
     (
         ("Warden Captain", "Hero", 120, 1),
         ("Ironvale Halberdiers", "Infantry", 11, 10),
         ("Longbow Archers", "Infantry", 9, 8),
         ("Ironwatch Sentinels", "Elite", 25, 6),
     )),
    ("The Quiet Procession", "marek@ashenchoir.club", "ashen-choir", 1500,
     "Slow, patient and very hard to shift once the wraiths are in place.",
     (
         ("Cantor of the Pale Choir", "Hero", 145, 1),
         ("Ash Wraiths", "Infantry", 13, 12),
         ("Bone Chariot", "Cavalry", 95, 2),
         ("Sorrow Standard", "Elite", 70, 1),
     )),
    ("Cenius's Vanguard", "cenius@cenius.ai", "ironvale", 2000,
     "Campaign list for the season. Still tinkering with the artillery slot.",
     (
         ("Marshal Cenius", "Hero", 180, 1),
         ("Ironvale Greatswords", "Elite", 18, 10),
         ("Border Riders", "Cavalry", 26, 5),
         ("Field Trebuchet", "War Machine", 160, 1),
     )),
)

# club night index, table label, member email, army list name (or None), note, days ago
BOOKINGS = (
    (0, "Table 2", "rowan@ironvale.club", "Fourth Company Spearhead",
     "Escalation league, 500 pts against Marek.", 2),
    (1, "Table 5", "marek@ashenchoir.club", "The Quiet Procession",
     "Painting first, then a practice game.", 1),
    (2, "Table 1", "cenius@cenius.ai", "Cenius's Vanguard",
     "Running the campaign map table — open to challengers.", 1),
)


def _timestamp(days_ago: int = 0, hours_ago: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return moment.isoformat(timespec="seconds")


def _insert_factions(conn) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name, slug, colour, motto in FACTIONS:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO factions (name, slug, colour, motto) VALUES (?, ?, ?, ?)",
            (name, slug, colour, motto),
        )
        if cursor.lastrowid:
            ids[slug] = int(cursor.lastrowid)
        else:
            row = db.query_one(conn, "SELECT id FROM factions WHERE slug = ?", (slug,))
            ids[slug] = int(row["id"])
    return ids


def _insert_users(conn, faction_ids: dict[str, int]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for index, (display_name, email, password, role, faction_slug) in enumerate(USERS):
        cursor = conn.execute(
            "INSERT OR IGNORE INTO users (email, password_hash, display_name, faction_id, role, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (email, security.hash_password(password), display_name,
             faction_ids.get(faction_slug), role, _timestamp(days_ago=40 - index * 5)),
        )
        if cursor.lastrowid:
            ids[email] = int(cursor.lastrowid)
        else:
            row = db.query_one(conn, "SELECT id FROM users WHERE email = ?", (email,))
            ids[email] = int(row["id"])
    return ids


def _insert_territories(conn, faction_ids: dict[str, int], user_ids: dict[str, int]) -> None:
    for name, x, y, faction_slug, claimant_email, days_ago in TERRITORIES:
        conn.execute(
            "INSERT OR IGNORE INTO territories"
            " (name, x, y, controlling_faction_id, claimed_by_user_id, claimed_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                name, x, y,
                faction_ids.get(faction_slug) if faction_slug else None,
                user_ids.get(claimant_email) if claimant_email else None,
                _timestamp(days_ago=days_ago) if days_ago is not None else None,
            ),
        )


def _insert_tables(conn) -> dict[str, int]:
    ids: dict[str, int] = {}
    for label, capacity in TABLES:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO \"tables\" (label, capacity) VALUES (?, ?)", (label, capacity)
        )
        if cursor.lastrowid:
            ids[label] = int(cursor.lastrowid)
        else:
            row = db.query_one(conn, 'SELECT id FROM "tables" WHERE label = ?', (label,))
            ids[label] = int(row["id"])
    return ids


def _insert_club_nights(conn) -> list[int]:
    ids: list[int] = []
    today = datetime.now(timezone.utc).date()
    for offset, title, location, notes in CLUB_NIGHTS:
        night_date = (today + timedelta(days=offset)).isoformat()
        existing = db.query_one(
            conn, "SELECT id FROM club_nights WHERE date = ? AND title = ?", (night_date, title)
        )
        if existing is not None:
            ids.append(int(existing["id"]))
            continue
        cursor = conn.execute(
            "INSERT INTO club_nights (date, title, location, notes) VALUES (?, ?, ?, ?)",
            (night_date, title, location, notes),
        )
        ids.append(int(cursor.lastrowid))
    return ids


def _insert_army_lists(conn, user_ids: dict[str, int], faction_ids: dict[str, int]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name, owner_email, faction_slug, limit, notes, units in ARMY_LISTS:
        existing = db.query_one(conn, "SELECT id FROM army_lists WHERE name = ?", (name,))
        if existing is not None:
            ids[name] = int(existing["id"])
            continue
        cursor = conn.execute(
            "INSERT INTO army_lists (owner_id, faction_id, name, points_limit, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_ids[owner_email], faction_ids[faction_slug], name, limit, notes,
             _timestamp(days_ago=18)),
        )
        list_id = int(cursor.lastrowid)
        ids[name] = list_id
        for unit_name, kind, points, qty in units:
            conn.execute(
                "INSERT INTO units (army_list_id, name, kind, points, qty) VALUES (?, ?, ?, ?, ?)",
                (list_id, unit_name, kind, points, qty),
            )
    return ids


def _insert_bookings(conn, night_ids: list[int], table_ids: dict[str, int],
                     user_ids: dict[str, int], list_ids: dict[str, int]) -> None:
    for night_index, table_label, member_email, list_name, note, days_ago in BOOKINGS:
        if night_index >= len(night_ids):
            continue
        night_id = night_ids[night_index]
        table_id = table_ids.get(table_label)
        if table_id is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO bookings"
            " (club_night_id, table_id, user_id, army_list_id, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (night_id, table_id, user_ids[member_email],
             list_ids.get(list_name) if list_name else None, note, _timestamp(days_ago=days_ago)),
        )


def _seed(conn) -> None:
    faction_ids = _insert_factions(conn)
    user_ids = _insert_users(conn, faction_ids)
    _insert_territories(conn, faction_ids, user_ids)
    table_ids = _insert_tables(conn)
    night_ids = _insert_club_nights(conn)
    list_ids = _insert_army_lists(conn, user_ids, faction_ids)
    _insert_bookings(conn, night_ids, table_ids, user_ids, list_ids)


def seed_if_empty() -> bool:
    """Seed the demo club once. Returns True when this call inserted the data."""
    with db.connection() as conn:
        db.apply_schema(conn)
        users = db.query_scalar(conn, "SELECT COUNT(*) FROM users") or 0
        if users:
            return False
        _seed(conn)
        logger.info("seeded demo club: factions, 24 territories, 5 club nights, 3 accounts, 3 army lists")
        return True


def main() -> None:
    """CLI entrypoint (``python3 -m app.seed``): seed then exit. Never serves."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seeded = seed_if_empty()
    print("seeded demo data" if seeded else "demo data already present — nothing to do")


if __name__ == "__main__":
    main()
