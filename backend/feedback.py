"""Werner's in-app feedback notes.

One table, one writer. Rows are read by the autonomous build loop over SSH
(status 'new' -> triage -> 'seen'); the app itself only ever inserts. The text
is never rendered back into the app and never enters a Claude prompt here —
if a future reader does either, escape/encode at that boundary.
"""
import re
from datetime import datetime, timezone

_ID_RE = re.compile(r"^[a-z0-9-]+$")
_MAX_TEXT = 4000
_MAX_SCREEN = 40


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def _clean_id(value):
    return value if isinstance(value, str) and _ID_RE.match(value) else None


def insert_feedback(conn, *, text, screen=None, course_id=None, lesson_id=None):
    """Store one feedback note. Raises ValueError on missing/blank text; bad
    context fields are dropped to NULL — the note is the payload, never reject
    it over metadata."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("feedback text is required")
    clean_screen = screen.strip() if isinstance(screen, str) and 0 < len(screen.strip()) <= _MAX_SCREEN else None
    conn.execute(
        "INSERT INTO feedback (created_at, screen, course_id, lesson_id, text) VALUES (?, ?, ?, ?, ?)",
        (
            _utcnow_iso(),
            clean_screen,
            _clean_id(course_id),
            _clean_id(lesson_id),
            text.strip()[:_MAX_TEXT],
        ),
    )
    conn.commit()
