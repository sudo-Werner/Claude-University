from backend import db


def test_init_db_creates_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"events", "profile"} <= tables


def test_init_db_is_idempotent(conn):
    # Running init a second time must not raise.
    db.init_db(conn)
    db.init_db(conn)


def test_get_connection_creates_parent_dir(tmp_path):
    nested = tmp_path / "a" / "b" / "learning.db"
    c = db.get_connection(nested)
    assert nested.parent.exists()
    c.close()


def test_init_db_migrates_preexisting_db_without_course_id(tmp_path):
    # Reproduces the production upgrade path: a database created under the OLD
    # schema (events table has no course_id column and no course index). init_db
    # must add the column AND its index without touching existing rows.
    import sqlite3

    dbfile = tmp_path / "old.db"
    raw = sqlite3.connect(dbfile)
    raw.executescript(
        """
        CREATE TABLE events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_event_id TEXT    NOT NULL UNIQUE,
            session_id      TEXT    NOT NULL,
            device          TEXT,
            topic_id        TEXT,
            event_type      TEXT    NOT NULL,
            occurred_at     TEXT    NOT NULL,
            received_at     TEXT    NOT NULL,
            payload         TEXT
        );
        CREATE INDEX idx_events_session ON events(session_id);
        """
    )
    raw.execute(
        "INSERT INTO events (client_event_id, session_id, event_type, occurred_at, received_at) "
        "VALUES ('old-1', 's1', 'session_start', '2026-06-20T10:00:00+00:00', '2026-06-20T10:00:00+00:00')"
    )
    raw.commit()
    raw.close()

    conn = db.get_connection(dbfile)
    db.init_db(conn)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    assert "course_id" in cols  # migration added the column

    indexes = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_events_course" in indexes  # index created after the column

    # the pre-existing row survived the migration
    assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 1

    # running the upgrade again must not raise
    db.init_db(conn)
    conn.close()
