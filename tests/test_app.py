"""Test suite for the Tabletop Wargames Club Campaign app.

Runs with ``python3 -m pytest`` against an isolated temporary SQLite file that is
seeded once, then copied per test. No network, no external services.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3

import pytest
from starlette.testclient import TestClient

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

DEMO_ORGANISER = ("cenius@cenius.ai", "cenius")
DEMO_MEMBER = ("rowan@ironvale.club", "wargames")
OTHER_MEMBER = ("marek@ashenchoir.club", "wargames")


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    """Seed one database for the whole session; each test copies it."""
    from app import db

    template = tmp_path_factory.mktemp("seed") / "template.db"
    os.environ["CAMPAIGN_DB"] = str(template)
    db.init_db()
    assert template.exists()
    return template


@pytest.fixture()
def db_path(tmp_path, monkeypatch, seeded_template):
    target = tmp_path / "campaign-test.db"
    shutil.copy(seeded_template, target)
    monkeypatch.setenv("CAMPAIGN_DB", str(target))
    yield target


@pytest.fixture()
def client(db_path):
    from app.main import app
    from app.routers import auth as auth_routes

    auth_routes._login_attempts.clear()
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match, "no csrf token in page"
    return match.group(1)


def sign_in(client: TestClient, credentials=DEMO_ORGANISER):
    email, password = credentials
    response = client.post("/login", data={"email": email, "password": password})
    assert response.status_code == 303, response.text
    return response


def fetch(client: TestClient, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response.text


def row(db_file, sql: str, params=()):
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #

def test_root_redirects_to_login_when_signed_out(client):
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_login_page_shows_demo_credentials(client):
    html = fetch(client, "/login")
    assert "Demo: cenius@cenius.ai / cenius" in html
    assert 'name="email"' in html
    assert 'type="password"' in html


def test_login_success_reaches_dashboard(client):
    sign_in(client)
    html = fetch(client, "/")
    assert "Cenius Vale" in html
    assert "Organiser view" in html
    assert "My army lists" in html


def test_login_failure_is_generic_and_keeps_email(client):
    response = client.post("/login", data={"email": DEMO_ORGANISER[0], "password": "wrong-password"})
    assert response.status_code == 200
    assert "Email or password is not correct" in response.text
    assert DEMO_ORGANISER[0] in response.text


def test_login_unknown_email_says_the_same_thing(client):
    response = client.post("/login", data={"email": "nobody@example.com", "password": "whatever"})
    assert response.status_code == 200
    assert "Email or password is not correct" in response.text


def test_logout_ends_the_session(client):
    sign_in(client)
    html = fetch(client, "/")
    response = client.post("/logout", data={"csrf_token": csrf(html)})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/").status_code == 303


def test_register_creates_member_account(client, db_path):
    response = client.post("/register", data={
        "display_name": "Ines Varga",
        "email": "ines@ironvale.club",
        "password": "stonewall",
        "faction": "ironvale",
    })
    assert response.status_code == 303
    html = fetch(client, "/")
    assert "Ines Varga" in html
    assert "Member" in html
    assert row(db_path, "SELECT role FROM users WHERE email = ?", ("ines@ironvale.club",))["role"] == "member"


def test_first_account_on_empty_club_is_organiser(client, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    response = client.post("/register", data={
        "display_name": "First Founder",
        "email": "founder@club.example",
        "password": "stonewall",
        "faction": "saltmarsh",
    })
    assert response.status_code == 303
    assert row(db_path, "SELECT role FROM users WHERE email = ?",
               ("founder@club.example",))["role"] == "organiser"
    assert "Organiser view" in fetch(client, "/")


def test_register_rejects_duplicate_email_and_keeps_values(client):
    response = client.post("/register", data={
        "display_name": "Copy Cat",
        "email": DEMO_ORGANISER[0],
        "password": "stonewall",
        "faction": "ironvale",
    })
    assert response.status_code == 200
    assert "That email is already registered" in response.text
    assert "Copy Cat" in response.text


def test_register_rejects_short_password(client):
    response = client.post("/register", data={
        "display_name": "Short Pass",
        "email": "short@club.example",
        "password": "abc",
        "faction": "ironvale",
    })
    assert response.status_code == 200
    assert "at least 8 characters" in response.text


# --------------------------------------------------------------------------- #
# seed data
# --------------------------------------------------------------------------- #

def test_seed_populates_every_screen(db_path):
    assert row(db_path, "SELECT COUNT(*) AS n FROM factions")["n"] == 4
    assert row(db_path, "SELECT COUNT(*) AS n FROM territories")["n"] == 24
    assert row(db_path, "SELECT COUNT(*) AS n FROM club_nights")["n"] == 5
    assert row(db_path, "SELECT COUNT(*) AS n FROM \"tables\"")["n"] == 6
    assert row(db_path, "SELECT COUNT(*) AS n FROM army_lists")["n"] == 3
    assert row(db_path, "SELECT COUNT(*) AS n FROM bookings")["n"] == 3
    assert row(db_path,
               "SELECT COUNT(*) AS n FROM territories WHERE controlling_faction_id IS NOT NULL")["n"] == 6


def test_seed_is_idempotent(db_path):
    from app import seed

    os.environ["CAMPAIGN_DB"] = str(db_path)
    assert seed.seed_if_empty() is False
    assert row(db_path, "SELECT COUNT(*) AS n FROM users")["n"] == 3


def test_campaign_page_renders_all_tiles(client):
    sign_in(client)
    html = fetch(client, "/campaign")
    assert html.count('role="listitem"') == 24
    assert "Undefended" in html
    assert "Ironvale Compact" in html
    assert "/claim" in html


def test_club_nights_page_renders_tables_and_bookings(client):
    sign_in(client)
    html = fetch(client, "/club-nights")
    assert html.count("table-card") >= 6
    for label in ("Table 1", "Table 2", "Table 6"):
        assert label in html
    assert "Rowan Ashby" in html


# --------------------------------------------------------------------------- #
# army lists
# --------------------------------------------------------------------------- #

def _create_list(client, name="Ironvale 1000", limit="1000", faction="ironvale") -> int:
    html = fetch(client, "/army-lists")
    response = client.post("/army-lists", data={
        "csrf_token": csrf(html), "name": name, "faction": faction,
        "points_limit": limit, "notes": "Test list",
    })
    assert response.status_code == 303, response.text
    return int(response.headers["location"].rsplit("/", 1)[1])


def test_create_army_list_appears_on_index(client):
    sign_in(client)
    list_id = _create_list(client, name="Ironvale 1000")
    html = fetch(client, "/army-lists")
    assert "Ironvale 1000" in html
    assert "0 / 1,000" in html.replace("\n", " ") or "1,000" in html
    assert row_path(client, f"/army-lists/{list_id}").status_code == 200


def row_path(client, path):
    return client.get(path)


def test_create_army_list_validation_keeps_values(client):
    sign_in(client)
    html = fetch(client, "/army-lists")
    response = client.post("/army-lists", data={
        "csrf_token": csrf(html), "name": "ab", "faction": "ironvale",
        "points_limit": "0", "notes": "kept note",
    })
    assert response.status_code == 200
    assert "List name" in response.text
    assert "kept note" in response.text
    assert "Points limit must be at least 50" in response.text


def test_unit_points_total_and_over_limit_rejection(client):
    sign_in(client)
    list_id = _create_list(client, name="Points Probe")
    detail = fetch(client, f"/army-lists/{list_id}")
    token = csrf(detail)

    response = client.post(f"/army-lists/{list_id}/units", data={
        "csrf_token": token, "name": "Halberdiers", "kind": "Infantry",
        "points": "12", "qty": "10",
    })
    assert response.status_code == 303
    detail = fetch(client, f"/army-lists/{list_id}")
    assert "120" in detail
    assert "880" in detail  # remaining

    response = client.post(f"/army-lists/{list_id}/units", data={
        "csrf_token": csrf(detail), "name": "Greatswords", "kind": "Elite",
        "points": "100", "qty": "10",
    })
    assert response.status_code == 200
    assert "That would take the list to 1,120 of 1,000 pts" in response.text
    assert row_single(client, f"/army-lists/{list_id}", "Greatswords") is False


def row_single(client, path, needle) -> bool:
    return needle in fetch(client, path)


def test_remove_unit_recalculates_total(client):
    sign_in(client)
    list_id = _create_list(client, name="Removal Probe")
    detail = fetch(client, f"/army-lists/{list_id}")
    client.post(f"/army-lists/{list_id}/units", data={
        "csrf_token": csrf(detail), "name": "Archers", "kind": "Infantry",
        "points": "9", "qty": "8",
    })
    detail = fetch(client, f"/army-lists/{list_id}")
    unit_id = re.search(rf'/army-lists/{list_id}/units/(\d+)/delete', detail).group(1)
    response = client.post(f"/army-lists/{list_id}/units/{unit_id}/delete",
                           data={"csrf_token": csrf(detail)})
    assert response.status_code == 303
    detail = fetch(client, f"/army-lists/{list_id}")
    assert f"/army-lists/{list_id}/units/" not in detail
    assert "Removed Archers" in detail  # flash confirms the removal


def test_cannot_touch_another_members_list(client):
    sign_in(client, DEMO_MEMBER)
    list_id = _create_list(client, name="Rowans Secret Plan", faction="ironvale")
    client.post("/logout", data={"csrf_token": csrf(fetch(client, "/"))})

    sign_in(client, OTHER_MEMBER)
    detail = fetch(client, f"/army-lists/{list_id}")
    assert "read-only for you" in detail
    token = csrf(detail)
    response = client.post(f"/army-lists/{list_id}/units", data={
        "csrf_token": token, "name": "Infiltrators", "kind": "Infantry",
        "points": "10", "qty": "1",
    })
    assert response.status_code == 403
    response = client.post(f"/army-lists/{list_id}/delete", data={"csrf_token": token})
    assert response.status_code == 403


def test_delete_list_removes_it(client):
    sign_in(client)
    list_id = _create_list(client, name="Disposable List")
    detail = fetch(client, f"/army-lists/{list_id}")
    response = client.post(f"/army-lists/{list_id}/delete", data={"csrf_token": csrf(detail)})
    assert response.status_code == 303
    assert f'href="/army-lists/{list_id}"' not in fetch(client, "/army-lists")
    assert client.get(f"/army-lists/{list_id}").status_code == 404


def test_unknown_list_renders_friendly_404(client):
    sign_in(client)
    response = client.get("/army-lists/9999")
    assert response.status_code == 404
    assert "We could not find that page" in response.text


# --------------------------------------------------------------------------- #
# campaign
# --------------------------------------------------------------------------- #

def _undefended_id(db_file) -> int:
    return row(db_file, "SELECT id FROM territories WHERE controlling_faction_id IS NULL "
                        "ORDER BY y, x LIMIT 1")["id"]


def test_claim_undefended_territory(client, db_path):
    sign_in(client)
    html = fetch(client, "/campaign")
    token = csrf(html)
    territory_id = _undefended_id(db_path)
    response = client.post(f"/campaign/territories/{territory_id}/claim",
                           data={"csrf_token": token})
    assert response.status_code == 303
    held = row(db_path, "SELECT f.slug AS slug, t.claimed_by_user_id AS uid FROM territories t"
                        " LEFT JOIN factions f ON f.id = t.controlling_faction_id WHERE t.id = ?",
               (territory_id,))
    assert held["slug"] == "ironvale"
    assert held["uid"] is not None
    assert "You claimed" in fetch(client, "/campaign")


def test_claim_held_territory_is_refused(client, db_path):
    sign_in(client, DEMO_MEMBER)  # Ironvale
    held_id = row(db_path, "SELECT t.id FROM territories t JOIN factions f ON f.id = t.controlling_faction_id"
                           " WHERE f.slug = 'ashen-choir' LIMIT 1")["id"]
    html = fetch(client, "/campaign")
    response = client.post(f"/campaign/territories/{held_id}/claim",
                           data={"csrf_token": csrf(html)})
    assert response.status_code == 200
    assert "already held by the Ashen Choir" in response.text


def test_member_cannot_use_organiser_override(client, db_path):
    sign_in(client, DEMO_MEMBER)
    territory_id = _undefended_id(db_path)
    html = fetch(client, "/campaign")
    response = client.post(f"/campaign/territories/{territory_id}/assign",
                           data={"csrf_token": csrf(html), "faction": "ashen-choir"})
    assert response.status_code == 403
    still_open = row(db_path, "SELECT controlling_faction_id FROM territories WHERE id = ?",
                     (territory_id,))
    assert still_open["controlling_faction_id"] is None


def test_organiser_can_assign_and_clear(client, db_path):
    sign_in(client)
    territory_id = _undefended_id(db_path)
    html = fetch(client, "/campaign")
    token = csrf(html)
    assert client.post(f"/campaign/territories/{territory_id}/assign",
                       data={"csrf_token": token, "faction": "saltmarsh"}).status_code == 303
    assert row(db_path, "SELECT f.slug AS slug FROM territories t JOIN factions f"
                        " ON f.id = t.controlling_faction_id WHERE t.id = ?",
               (territory_id,))["slug"] == "saltmarsh"

    assert client.post(f"/campaign/territories/{territory_id}/assign",
                       data={"csrf_token": token, "faction": ""}).status_code == 303
    assert row(db_path, "SELECT controlling_faction_id FROM territories WHERE id = ?",
               (territory_id,))["controlling_faction_id"] is None
    assert "undefended again" in fetch(client, "/campaign")


# --------------------------------------------------------------------------- #
# club nights
# --------------------------------------------------------------------------- #

def _free_table_and_night(db_file):
    night = row(db_file, "SELECT id, date FROM club_nights WHERE date >= date('now') ORDER BY date LIMIT 1")
    table = row(db_file,
                "SELECT id FROM \"tables\" WHERE id NOT IN"
                " (SELECT table_id FROM bookings WHERE club_night_id = ?) ORDER BY label LIMIT 1",
                (night["id"],))
    return night["id"], table["id"]


def test_book_free_table(client, db_path):
    sign_in(client)
    night_id, table_id = _free_table_and_night(db_path)
    html = fetch(client, "/club-nights")
    token = csrf(html)
    response = client.post(f"/club-nights/{night_id}/book", data={
        "csrf_token": token, "table_id": str(table_id), "army_list_id": "", "notes": "Practice game",
    })
    assert response.status_code == 303
    booking = row(db_path, "SELECT b.id, u.email AS email FROM bookings b JOIN users u ON u.id = b.user_id"
                           " WHERE b.club_night_id = ? AND b.table_id = ?", (night_id, table_id))
    assert booking["email"] == DEMO_ORGANISER[0]
    page = fetch(client, f"/club-nights?night={night_id}")
    assert "Practice game" in page


def test_booking_refuses_taken_table_and_second_table(client, db_path):
    sign_in(client, DEMO_ORGANISER)
    mine = row(db_path, "SELECT club_night_id AS night, table_id AS table_id FROM bookings"
                        " WHERE user_id = (SELECT id FROM users WHERE email = ?) LIMIT 1",
               (DEMO_ORGANISER[0],))
    night_id = mine["night"]

    # A second table on the same night is refused.
    free_table = row(db_path, "SELECT id FROM \"tables\" WHERE id NOT IN"
                              " (SELECT table_id FROM bookings WHERE club_night_id = ?)"
                              " ORDER BY label LIMIT 1", (night_id,))["id"]
    html = fetch(client, f"/club-nights?night={night_id}")
    response = client.post(f"/club-nights/{night_id}/book", data={
        "csrf_token": csrf(html), "table_id": str(free_table), "army_list_id": "", "notes": "",
    })
    assert response.status_code == 200
    assert "already have a table that night" in response.text
    assert row(db_path, "SELECT COUNT(*) AS n FROM bookings WHERE table_id = ? AND club_night_id = ?",
               (free_table, night_id))["n"] == 0

    # A table held by somebody else is refused for a member without a booking.
    sign_in(client, OTHER_MEMBER)
    taken = row(db_path, "SELECT table_id AS t FROM bookings WHERE club_night_id = ?"
                         " AND user_id != (SELECT id FROM users WHERE email = ?) LIMIT 1",
                (night_id, OTHER_MEMBER[0]))
    if taken is not None:
        html = fetch(client, f"/club-nights?night={night_id}")
        response = client.post(f"/club-nights/{night_id}/book", data={
            "csrf_token": csrf(html), "table_id": str(taken["t"]), "army_list_id": "", "notes": "",
        })
        assert response.status_code == 200
        assert "is already booked" in response.text


def test_cancel_own_booking(client, db_path):
    sign_in(client)
    booking = row(db_path, "SELECT b.id, b.club_night_id AS night FROM bookings b JOIN users u ON u.id = b.user_id"
                           " WHERE u.email = ?", (DEMO_ORGANISER[0],))
    html = fetch(client, f"/club-nights?night={booking['night']}")
    response = client.post(f"/bookings/{booking['id']}/cancel",
                           data={"csrf_token": csrf(html), "return_to": "/club-nights"})
    assert response.status_code == 303
    assert row(db_path, "SELECT COUNT(*) AS n FROM bookings WHERE id = ?", (booking["id"],))["n"] == 0


def test_member_cannot_cancel_someone_elses_booking(client, db_path):
    sign_in(client, OTHER_MEMBER)
    booking = row(db_path, "SELECT b.id, b.club_night_id AS night FROM bookings b JOIN users u ON u.id = b.user_id"
                           " WHERE u.email = ?", (DEMO_MEMBER[0],))
    assert booking is not None
    html = fetch(client, f"/club-nights?night={booking['night']}")
    response = client.post(f"/bookings/{booking['id']}/cancel",
                           data={"csrf_token": csrf(html), "return_to": "/club-nights"})
    assert response.status_code == 403
    assert row(db_path, "SELECT COUNT(*) AS n FROM bookings WHERE id = ?", (booking["id"],))["n"] == 1


def test_organiser_can_cancel_any_booking(client, db_path):
    sign_in(client)
    booking = row(db_path, "SELECT b.id, b.club_night_id AS night FROM bookings b JOIN users u ON u.id = b.user_id"
                           " WHERE u.email = ?", (DEMO_MEMBER[0],))
    html = fetch(client, f"/club-nights?night={booking['night']}")
    response = client.post(f"/bookings/{booking['id']}/cancel",
                           data={"csrf_token": csrf(html), "return_to": "/club-nights"})
    assert response.status_code == 303
    assert row(db_path, "SELECT COUNT(*) AS n FROM bookings WHERE id = ?", (booking["id"],))["n"] == 0


# --------------------------------------------------------------------------- #
# dashboard + hardening
# --------------------------------------------------------------------------- #

def test_new_member_dashboard_shows_empty_states(client):
    client.post("/register", data={
        "display_name": "Nadia Frost",
        "email": "nadia@club.example",
        "password": "stonewall",
        "faction": "obsidian-pact",
    })
    html = fetch(client, "/")
    assert "Create your first army list" in html
    assert "Book a table" in html


def test_dashboard_lists_points_and_territory_counts(client):
    sign_in(client)
    html = fetch(client, "/")
    assert "Vanguard" in html
    assert "650 of 2,000 pts committed" in html
    assert "of 24 territories held" in html


def test_security_headers_present(client):
    response = client.get("/login")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp


def test_session_cookie_flags(client):
    response = client.post("/login", data={"email": DEMO_ORGANISER[0], "password": DEMO_ORGANISER[1]})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie or "samesite=lax" in cookie.lower()


def test_mutation_requires_csrf(client):
    sign_in(client)
    response = client.post("/army-lists", data={
        "name": "No Token", "faction": "ironvale", "points_limit": "500",
    })
    assert response.status_code == 403


def test_static_assets_are_served(client):
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert client.get("/static/favicon.svg").status_code == 200
    font = client.get("/static/fonts/plex-mono-400.woff2")
    assert font.status_code == 200
    assert client.get("/static/app.js").status_code == 200
