-- Hollow Gate Wargames Club — campaign schema.
-- Applied idempotently at every boot by app.db.init_db().

CREATE TABLE IF NOT EXISTS factions (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    slug    TEXT NOT NULL UNIQUE,
    colour  TEXT NOT NULL,
    motto   TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    faction_id    INTEGER REFERENCES factions(id),
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('organiser', 'member')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS army_lists (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    faction_id   INTEGER NOT NULL REFERENCES factions(id),
    name         TEXT NOT NULL,
    points_limit INTEGER NOT NULL DEFAULT 1000 CHECK (points_limit > 0),
    notes        TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS units (
    id           INTEGER PRIMARY KEY,
    army_list_id INTEGER NOT NULL REFERENCES army_lists(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    points       INTEGER NOT NULL CHECK (points >= 0),
    qty          INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 1)
);

CREATE TABLE IF NOT EXISTS territories (
    id                      INTEGER PRIMARY KEY,
    name                    TEXT NOT NULL,
    x                       INTEGER NOT NULL,
    y                       INTEGER NOT NULL,
    controlling_faction_id  INTEGER REFERENCES factions(id),
    claimed_by_user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    claimed_at              TEXT,
    UNIQUE (x, y)
);

CREATE TABLE IF NOT EXISTS club_nights (
    id       INTEGER PRIMARY KEY,
    date     TEXT NOT NULL,
    title    TEXT NOT NULL,
    location TEXT NOT NULL,
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS "tables" (
    id       INTEGER PRIMARY KEY,
    label    TEXT NOT NULL UNIQUE,
    capacity INTEGER NOT NULL DEFAULT 4
);

CREATE TABLE IF NOT EXISTS bookings (
    id            INTEGER PRIMARY KEY,
    club_night_id INTEGER NOT NULL REFERENCES club_nights(id) ON DELETE CASCADE,
    table_id      INTEGER NOT NULL REFERENCES "tables"(id),
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    army_list_id  INTEGER REFERENCES army_lists(id) ON DELETE SET NULL,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (club_night_id, table_id),
    UNIQUE (club_night_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    flash      TEXT,
    flash_kind TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_users_faction    ON users(faction_id);
CREATE INDEX IF NOT EXISTS ix_lists_owner      ON army_lists(owner_id);
CREATE INDEX IF NOT EXISTS ix_lists_faction    ON army_lists(faction_id);
CREATE INDEX IF NOT EXISTS ix_units_list       ON units(army_list_id);
CREATE INDEX IF NOT EXISTS ix_territories_held ON territories(controlling_faction_id);
CREATE INDEX IF NOT EXISTS ix_nights_date      ON club_nights(date);
CREATE INDEX IF NOT EXISTS ix_bookings_night   ON bookings(club_night_id);
CREATE INDEX IF NOT EXISTS ix_bookings_user    ON bookings(user_id);
CREATE INDEX IF NOT EXISTS ix_sessions_user    ON sessions(user_id);
