import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "learning.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path=DEFAULT_DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA_PATH.read_text())
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "course_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN course_id TEXT")
