from backend import profile


def test_latest_is_none_when_empty(conn):
    assert profile.latest_profile(conn) is None


def test_save_then_latest(conn):
    profile.save_profile(conn, {"analogies": True})
    latest = profile.latest_profile(conn)
    assert latest["data"] == {"analogies": True}


def test_versions_are_appended_not_overwritten(conn):
    profile.save_profile(conn, {"analogies": True})
    profile.save_profile(conn, {"analogies": False})
    # Latest reflects the newest save...
    assert profile.latest_profile(conn)["data"] == {"analogies": False}
    # ...but both versions are retained.
    n = conn.execute("SELECT COUNT(*) AS n FROM profile").fetchone()["n"]
    assert n == 2
