#!/usr/bin/env python3
"""End-to-end smoke walkthrough against a running server.

Registers a member, creates an army list, adds a unit, claims a territory and
books a table, then prints SMOKE OK. Uses only the standard library.

    python3 scripts/smoke_test.py [base_url]
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
CLAIM_RE = re.compile(r'action="(/campaign/territories/\d+/claim)"')
BOOK_RE = re.compile(r'action="(/club-nights/\d+/book)"')
TABLE_RE = re.compile(r'name="table_id" required>\s*<option value="(\d+)"')

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path: str) -> str:
    with opener.open(f"{BASE_URL}{path}", timeout=15) as response:
        return response.read().decode("utf-8")


def post(path: str, data: dict[str, str]) -> str:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(request, timeout=15) as response:
        return response.read().decode("utf-8")


def csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise SystemExit("no CSRF token found in page")
    return match.group(1)


def step(message: str) -> None:
    print(f"  - {message}")


def main() -> None:
    print(f"Smoke testing {BASE_URL}")
    get("/login")
    step("login page reachable")

    stamp = int(time.time())
    email = f"smoke{stamp}@club.example"
    page = post("/register", {
        "display_name": f"Smoke Tester {stamp}",
        "email": email,
        "password": "stonewall",
        "faction": "ironvale",
    })
    if "Sign in" in page and email not in page:
        raise SystemExit("registration did not sign the member in")
    step(f"registered and signed in as {email}")

    page = get("/army-lists")
    if "New army list" not in page:
        raise SystemExit("army list page did not render")
    page = post("/army-lists", {
        "csrf_token": csrf(page),
        "name": f"Smoke Vanguard {stamp}",
        "faction": "ironvale",
        "points_limit": "1000",
        "notes": "Created by scripts/smoke_test.py",
    })
    list_id = re.search(r"/army-lists/(\d+)/units", page)
    if not list_id:
        raise SystemExit("army list was not created")
    list_id_value = list_id.group(1)
    step(f"created army list #{list_id_value} for 1000 pts")

    page = post(f"/army-lists/{list_id_value}/units", {
        "csrf_token": csrf(page),
        "name": "Smoke Halberdiers",
        "kind": "Infantry",
        "points": "11",
        "qty": "10",
    })
    if "110" not in page:
        raise SystemExit("unit total not shown after adding a unit")
    step("added a unit (110 pts used)")

    page = get("/campaign")
    claim = CLAIM_RE.search(page)
    if not claim:
        raise SystemExit("no undefended territory to claim")
    page = post(claim.group(1), {"csrf_token": csrf(page)})
    if "You claimed" not in page:
        raise SystemExit("territory claim did not confirm")
    step("claimed an undefended territory")

    page = get("/club-nights")
    book = BOOK_RE.search(page)
    table = TABLE_RE.search(page)
    if not book or not table:
        raise SystemExit("no free table to book")
    page = post(book.group(1), {
        "csrf_token": csrf(page),
        "table_id": table.group(1),
        "army_list_id": list_id_value,
        "notes": "Booked by scripts/smoke_test.py",
    })
    if "booked for" not in page:
        raise SystemExit("table booking did not confirm")
    step("booked a table for the next club night")

    page = get("/")
    if "Smoke Tester" not in page:
        raise SystemExit("dashboard did not render for the smoke member")
    step("dashboard renders lists, territory and booking")

    print(json.dumps({"base_url": BASE_URL, "member": email}, indent=2))
    print("SMOKE OK")


if __name__ == "__main__":
    main()
