CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_event_id TEXT    NOT NULL UNIQUE,
    session_id      TEXT    NOT NULL,
    device          TEXT,
    topic_id        TEXT,
    course_id       TEXT,
    event_type      TEXT    NOT NULL,
    occurred_at     TEXT    NOT NULL,
    received_at     TEXT    NOT NULL,
    payload         TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_session  ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type     ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);
-- idx_events_course is created in db._migrate, AFTER the course_id column is
-- ensured: on a pre-existing DB the column is added by ALTER at migrate time,
-- so indexing it here (before migrate) would fail with "no such column".

CREATE TABLE IF NOT EXISTS profile (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    data       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    screen     TEXT,
    course_id  TEXT,
    lesson_id  TEXT,
    text       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'new'
);
