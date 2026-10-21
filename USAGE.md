# Using the club campaign

Sign in at `/login`. The demo panel on the login card lists the three seeded
accounts and offers one-click sign-in.

- `cenius@cenius.ai` / `cenius` — organiser
- `rowan@ironvale.club` / `wargames` — member (Ironvale Compact)
- `marek@ashenchoir.club` / `wargames` — member (Ashen Choir)

## Dashboard (`/`)

The home screen answers "where do I stand?" in one view:

- a greeting showing your display name, role and faction motto;
- four KPI tiles: army lists and points committed, territories held by your
  faction (of 24), territories still claimable, and upcoming tables;
- **My army lists** with owner-visible points progress bars;
- **Campaign standing** for your faction with a held/24 meter and a claim link;
- **Upcoming bookings** with a cancel button on each row;
- **Next club night** with the free-table count and a link to that night;
- for organisers only, **club totals**: members, army lists, undefended
  territories and bookings ahead.

A brand-new member gets invitations instead of blank panels ("Create your first
army list", "Book a table").

## Army lists (`/army-lists`)

1. Pick a faction, a name and a points limit in the **New army list** form.
2. The left pane lists every club list grouped by faction with owner, unit count
   and `total / limit` points. Your own lists are highlighted.
3. Open a list to see its running total, remaining points, a progress bar that
   turns amber near the limit, and the units table.

On your own list:

- **Add a unit** — name, kind, points per model and models. The subtotal is
  `points × models`, and the server rejects anything that would take the list
  over its limit, telling you the total it would have reached (e.g. "That would
  take the list to 1,120 of 1,000 pts").
- **Remove** a unit — the total recalculates immediately.
- **Delete list** — behind a confirmation disclosure; it removes the list and its
  units.

Other members' lists are read-only. Organisers can manage any list.

## Campaign map (`/campaign`)

- 24 territories in an 8-wide grid, coloured by the faction that controls them.
- The legend strip shows each faction's live territory count plus the undefended
  total.
- **Claim** appears on every undefended tile. Claiming records you as the
  claimant and stamps the time; the tile turns your faction colour.
- A territory already held by another faction cannot be claimed — you get a clear
  message naming the holder.
- Organisers get an **Arbitration** table listing all 24 territories with a
  faction selector: set any territory to another faction, or clear it back to
  "Undefended". Non-organisers who post to that route directly get a 403 page.

## Club nights (`/club-nights`)

- The left pane lists the five upcoming nights with date, title, location and
  how many tables are free; the selected night is highlighted.
- The right pane shows that night's six tables: **Free** or **Booked** with the
  member's name, the army list they are bringing and their note.
- **Reserve a table** — choose a free table, optionally attach one of your army
  lists and add a note. The confirmation flash appears on the page you land on
  and the booking also shows on your dashboard.
- **Cancel** — on your own bookings (organisers can cancel anyone's); the table
  returns to Free immediately.
- The rules are enforced server-side: a table already taken, a second table on
  the same night, or a full night are all refused with a message and no change.

## Validation and errors

- Every form validates on the server and re-renders at HTTP 200 with the message
  at the field and everything you typed retained.
- Unknown ids render a friendly not-found page inside the normal app shell; a
  permission failure renders a 403 page; unhandled faults render a generic error
  page and log the traceback to the server console only.
- All mutations are POST-only, guarded by a session-bound CSRF token, and scoped
  to the signed-in member on the server — never trusting a client-supplied id.
