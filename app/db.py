"""SQLite access layer: one short-lived connection per request, WAL mode.

Every statement in the app is parameterized; nothing user-supplied is ever
interpolated into SQL.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
SCHEMA_PATH = APP_DIR / "schema.sql"

logger = logging.getLogger("campaign.db")

DEFAULT_DB_NAME = "campaign.db"


def now_iso() -> str:
    """UTC timestamp as ISO-8601 with a fixed offset (lexicographically sortable)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def database_path() -> Path:
    """The SQLite file. Relative paths resolve against the project root."""
    raw = os.environ.get("CAMPAIGN_DB", DEFAULT_DB_NAME).strip() or DEFAULT_DB_NAME
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def connect() -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced."""
    db_file = database_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Transactional connection: commit on success, roll back on failure."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()


def query_scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    row = query_one(conn, sql, params)
    return row[0] if row is not None else None


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    return conn.execute(sql, tuple(params))


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def init_db() -> None:
    """Create the database, its schema and (on an empty club) the demo data."""
    from app import seed  # local import: seed imports this module

    db_file = database_path()
    first_boot = not db_file.exists()
    with connection() as conn:
        apply_schema(conn)
    if first_boot:
        logger.info("created database at %s", db_file)
    seeded = seed.seed_if_empty()
    logger.info("startup complete (db=%s, seeded=%s)", db_file, seeded)
