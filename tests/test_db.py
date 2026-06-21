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
