import json
from datetime import datetime, timezone


def save_profile(conn, data):
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO profile (created_at, data) VALUES (?, ?)",
        (created_at, json.dumps(data)),
    )
    conn.commit()
    return {"id": cur.lastrowid, "created_at": created_at}


def latest_profile(conn):
    row = conn.execute("SELECT * FROM profile ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    d = dict(row)
    d["data"] = json.loads(d["data"])
    return d
