import json
from datetime import datetime, timezone

REQUIRED_FIELDS = ("client_event_id", "session_id", "event_type", "occurred_at")


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def insert_events(conn, events):
    # Validate everything first so a bad event inserts nothing.
    for ev in events:
        if not isinstance(ev, dict):
            raise ValueError("event must be an object")
        missing = [f for f in REQUIRED_FIELDS if not ev.get(f)]
        if missing:
            raise ValueError(f"event missing required fields: {missing}")

    accepted = 0
    duplicates = 0
    received_at = _utcnow_iso()
    for ev in events:
        payload = ev.get("payload")
        cur = conn.execute(
            """INSERT OR IGNORE INTO events
               (client_event_id, session_id, device, topic_id, course_id,
                event_type, occurred_at, received_at, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["client_event_id"],
                ev["session_id"],
                ev.get("device"),
                ev.get("topic_id"),
                ev.get("course_id"),
                ev["event_type"],
                ev["occurred_at"],
                received_at,
                json.dumps(payload) if payload is not None else None,
            ),
        )
        if cur.rowcount == 1:
            accepted += 1
        else:
            duplicates += 1
    conn.commit()
    return {"accepted": accepted, "duplicates": duplicates}
