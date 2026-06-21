import json


def query_events(conn, since=None, session_id=None, event_type=None, limit=1000):
    clauses = []
    params = []
    if since:
        clauses.append("occurred_at >= ?")
        params.append(since)
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM events {where} ORDER BY occurred_at ASC, id ASC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def _row_to_event(row):
    d = dict(row)
    d["payload"] = json.loads(d["payload"]) if d.get("payload") else None
    return d
