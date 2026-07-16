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


MAX_PRIOR_KNOWLEDGE_CHARS = 2000


def latest_prior_knowledge(conn, course_id, lesson_id):
    """The newest non-empty prior-knowledge answer for this course+lesson, or ""
    if none exists or every stored row is malformed. Events are client-forgeable —
    same trust level as the profile, which already reaches prompts as arbitrary
    client JSON — so every field is read defensively and a bad row is skipped
    rather than raising."""
    rows = conn.execute(
        "SELECT payload FROM events WHERE event_type = 'prior_knowledge' "
        "AND course_id = ? AND topic_id = ? ORDER BY occurred_at DESC, id DESC",
        (course_id, lesson_id),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        text = payload.get("text")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        return text[:MAX_PRIOR_KNOWLEDGE_CHARS]
    return ""
