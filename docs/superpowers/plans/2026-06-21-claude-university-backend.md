# Claude University — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Pi-hosted service that ingests, stores, and serves Werner's learning event log — the single source of truth every other part of the platform reads and writes.

**Architecture:** A small Flask app over a single SQLite file. Stateless HTTP endpoints open a fresh SQLite connection per request (SQLite connections aren't thread-safe to share). Event ingestion is idempotent via a unique `client_event_id`, so the browser's offline-first buffer can re-sync after a dropped connection without double-counting. The learner profile is stored append-only (versioned). Developed and unit-tested on the Mac; deployed to and verified on the Pi (`192.168.2.69`).

**Tech Stack:** Python 3.11, Flask (HTTP), stdlib `sqlite3` (storage — no ORM), waitress (production WSGI server, pure-Python, runs on the Pi's aarch64), pytest (tests).

## Global Constraints

- Storage is a single SQLite `.db` file — the source of truth. No other datastore.
- Every event carries a `client_event_id`; ingestion MUST be idempotent on it (offline-first re-sync safety).
- No ORM — use stdlib `sqlite3` directly (simplest solution that works).
- Single user (Werner). No auth, multi-tenancy, or sharing.
- Append-only event log: events are inserted, never updated or deleted by the app.
- Python module/package name: `backend`. Project root: `/Users/wernervanellewee/Projects/Claude_Education` (Mac); mirror to `~/claude_university` on the Pi.
- Commit messages end with the trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## Plan sequence

This is **Plan 1 of 4**. It produces a complete, runnable, tested backend service with no dependency on the others. Plans 2–4 (frontend engine, learning mechanics + content, in-app tutor) build on the API this plan exposes.

## Prerequisites

The project directory is currently empty and **not** a git repository. Before Task 1, from the project root:

```bash
cd /Users/wernervanellewee/Projects/Claude_Education
git init
python3 -m venv .venv
source .venv/bin/activate
```

> Confirm with Werner before `git init` (his rule: no git actions without explicit ask). The plan's commit steps assume an initialized repo.

## File Structure

```
Claude_Education/
  backend/
    __init__.py        # marks the package (empty)
    schema.sql         # SQLite DDL: events + profile tables
    db.py              # connection + schema init
    events.py          # idempotent event ingestion
    queries.py         # event read/query helpers (dashboard + Claude analysis)
    profile.py         # versioned learner-profile store
    app.py             # Flask app factory + HTTP routes
  tests/
    conftest.py        # pytest fixtures: temp db conn + Flask test client
    test_db.py
    test_events.py
    test_queries.py
    test_profile.py
    test_api.py
  deploy/
    claude-university.service   # systemd unit for the Pi
  requirements.txt
  pytest.ini
```

Each backend module has one responsibility: `db` owns the connection/schema, `events` owns writes, `queries` owns reads, `profile` owns the profile, `app` owns HTTP wiring only (no business logic).

---

### Task 1: Project scaffold + database layer

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `backend/__init__.py`
- Create: `backend/schema.sql`
- Create: `backend/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `backend.db.DEFAULT_DB_PATH: pathlib.Path`
  - `backend.db.get_connection(db_path=DEFAULT_DB_PATH) -> sqlite3.Connection` (row_factory = `sqlite3.Row`, parent dir created)
  - `backend.db.init_db(conn: sqlite3.Connection) -> None` (idempotent; runs `schema.sql`)
  - pytest fixture `conn` (temp-file SQLite connection, schema initialised)

- [ ] **Step 1: Write the dependency and config files**

`requirements.txt`:
```
Flask==3.0.3
waitress==3.0.0
```

`pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

`backend/__init__.py`:
```python
```
(empty file — just marks the package)

- [ ] **Step 2: Write the schema**

`backend/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS events (
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

CREATE INDEX IF NOT EXISTS idx_events_session  ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type     ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);

CREATE TABLE IF NOT EXISTS profile (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    data       TEXT NOT NULL
);
```

- [ ] **Step 3: Write the failing test**

`tests/conftest.py`:
```python
import pytest

from backend import db


@pytest.fixture
def conn(tmp_path):
    c = db.get_connection(tmp_path / "test.db")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def client(tmp_path):
    from backend.app import create_app

    app = create_app(db_path=tmp_path / "test_api.db")
    app.config.update(TESTING=True)
    return app.test_client()
```

`tests/test_db.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.db'` (db.py not written yet).

- [ ] **Step 5: Write minimal implementation**

`backend/db.py`:
```python
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
    conn.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini backend/__init__.py backend/schema.sql backend/db.py tests/conftest.py tests/test_db.py
git commit -m "feat(backend): SQLite schema and connection layer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Idempotent event ingestion

**Files:**
- Create: `backend/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: `backend.db.get_connection`, the `conn` fixture.
- Produces:
  - `backend.events.REQUIRED_FIELDS: tuple[str, ...]` = `("client_event_id", "session_id", "event_type", "occurred_at")`
  - `backend.events.insert_events(conn, events: list[dict]) -> dict` returning `{"accepted": int, "duplicates": int}`. Raises `ValueError` if any event is missing a required field (nothing is inserted in that case). Idempotent on `client_event_id`. `payload` (a dict or None) is JSON-serialised into the `payload` column.

- [ ] **Step 1: Write the failing test**

`tests/test_events.py`:
```python
import json

import pytest

from backend import events


def _ev(cid, **over):
    base = {
        "client_event_id": cid,
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
        "device": "mac",
        "topic_id": "p1t1",
        "payload": {"section": "intro"},
    }
    base.update(over)
    return base


def test_insert_new_events_accepted(conn):
    result = events.insert_events(conn, [_ev("a"), _ev("b")])
    assert result == {"accepted": 2, "duplicates": 0}
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 2


def test_duplicate_client_event_id_ignored(conn):
    events.insert_events(conn, [_ev("a")])
    result = events.insert_events(conn, [_ev("a"), _ev("c")])
    assert result == {"accepted": 1, "duplicates": 1}
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 2


def test_payload_stored_as_json(conn):
    events.insert_events(conn, [_ev("a", payload={"k": 1})])
    row = conn.execute("SELECT payload FROM events WHERE client_event_id='a'").fetchone()
    assert json.loads(row["payload"]) == {"k": 1}


def test_missing_required_field_raises(conn):
    bad = _ev("a")
    del bad["event_type"]
    with pytest.raises(ValueError):
        events.insert_events(conn, [bad])
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.events'`.

- [ ] **Step 3: Write minimal implementation**

`backend/events.py`:
```python
import json
from datetime import datetime, timezone

REQUIRED_FIELDS = ("client_event_id", "session_id", "event_type", "occurred_at")


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def insert_events(conn, events):
    # Validate everything first so a bad event inserts nothing.
    for ev in events:
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
               (client_event_id, session_id, device, topic_id,
                event_type, occurred_at, received_at, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["client_event_id"],
                ev["session_id"],
                ev.get("device"),
                ev.get("topic_id"),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_events.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/events.py tests/test_events.py
git commit -m "feat(backend): idempotent event ingestion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Event querying

**Files:**
- Create: `backend/queries.py`
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: `backend.events.insert_events`, the `conn` fixture.
- Produces:
  - `backend.queries.query_events(conn, since=None, session_id=None, event_type=None, limit=1000) -> list[dict]`. Returns events ordered by `occurred_at ASC, id ASC`. Each dict has the row columns; `payload` is JSON-decoded back to a dict (or `None`). Filters: `since` → `occurred_at >= since`; `session_id` exact; `event_type` exact.

- [ ] **Step 1: Write the failing test**

`tests/test_queries.py`:
```python
from backend import events, queries


def _ev(cid, **over):
    base = {
        "client_event_id": cid,
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
        "payload": {"section": "intro"},
    }
    base.update(over)
    return base


def test_query_all(conn):
    events.insert_events(conn, [_ev("a"), _ev("b")])
    rows = queries.query_events(conn)
    assert len(rows) == 2
    assert rows[0]["payload"] == {"section": "intro"}


def test_query_filters_by_session(conn):
    events.insert_events(conn, [_ev("a", session_id="s1"), _ev("b", session_id="s2")])
    rows = queries.query_events(conn, session_id="s2")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_filters_by_type(conn):
    events.insert_events(
        conn, [_ev("a", event_type="lesson_view"), _ev("b", event_type="quiz_answer")]
    )
    rows = queries.query_events(conn, event_type="quiz_answer")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_filters_since(conn):
    events.insert_events(
        conn,
        [
            _ev("a", occurred_at="2026-06-20T10:00:00+00:00"),
            _ev("b", occurred_at="2026-06-22T10:00:00+00:00"),
        ],
    )
    rows = queries.query_events(conn, since="2026-06-21T00:00:00+00:00")
    assert [r["client_event_id"] for r in rows] == ["b"]


def test_query_ordered_by_occurred_at(conn):
    events.insert_events(
        conn,
        [
            _ev("late", occurred_at="2026-06-22T10:00:00+00:00"),
            _ev("early", occurred_at="2026-06-20T10:00:00+00:00"),
        ],
    )
    rows = queries.query_events(conn)
    assert [r["client_event_id"] for r in rows] == ["early", "late"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.queries'`.

- [ ] **Step 3: Write minimal implementation**

`backend/queries.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_queries.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/queries.py tests/test_queries.py
git commit -m "feat(backend): event query helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Versioned learner profile

**Files:**
- Create: `backend/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: the `conn` fixture.
- Produces:
  - `backend.profile.save_profile(conn, data: dict) -> dict` — inserts a new row, returns `{"id": int, "created_at": str}`. Never updates; each save is a new version.
  - `backend.profile.latest_profile(conn) -> dict | None` — the most recent row as `{"id", "created_at", "data": dict}`, or `None` if no profile saved yet.

- [ ] **Step 1: Write the failing test**

`tests/test_profile.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.profile'`.

- [ ] **Step 3: Write minimal implementation**

`backend/profile.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/profile.py tests/test_profile.py
git commit -m "feat(backend): versioned learner profile store

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Flask HTTP API

**Files:**
- Create: `backend/app.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `backend.db`, `backend.events`, `backend.queries`, `backend.profile`; the `client` fixture.
- Produces:
  - `backend.app.create_app(db_path=None) -> flask.Flask`. Opens a fresh connection per request. Routes:
    - `GET  /api/health` → `{"status": "ok"}`
    - `POST /api/events` body `{"events": [...]}` → `insert_events` result; `400 {"error": ...}` on a missing required field
    - `GET  /api/events?since=&session_id=&type=&limit=` → `{"events": [...]}`
    - `POST /api/profile` body = profile dict → `save_profile` result
    - `GET  /api/profile` → latest profile dict, or `{}` if none

- [ ] **Step 1: Write the failing test**

`tests/test_api.py`:
```python
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_post_and_get_events(client):
    payload = {
        "events": [
            {
                "client_event_id": "a",
                "session_id": "s1",
                "event_type": "lesson_view",
                "occurred_at": "2026-06-21T10:00:00+00:00",
                "payload": {"section": "intro"},
            }
        ]
    }
    post = client.post("/api/events", json=payload)
    assert post.status_code == 200
    assert post.get_json() == {"accepted": 1, "duplicates": 0}

    got = client.get("/api/events")
    assert got.status_code == 200
    events = got.get_json()["events"]
    assert len(events) == 1
    assert events[0]["payload"] == {"section": "intro"}


def test_post_events_idempotent_over_http(client):
    ev = {
        "client_event_id": "dup",
        "session_id": "s1",
        "event_type": "lesson_view",
        "occurred_at": "2026-06-21T10:00:00+00:00",
    }
    client.post("/api/events", json={"events": [ev]})
    second = client.post("/api/events", json={"events": [ev]})
    assert second.get_json() == {"accepted": 0, "duplicates": 1}


def test_post_events_missing_field_returns_400(client):
    bad = {"events": [{"client_event_id": "x", "session_id": "s1"}]}
    resp = client.post("/api/events", json=bad)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_profile_roundtrip(client):
    assert client.get("/api/profile").get_json() == {}
    client.post("/api/profile", json={"analogies": True})
    latest = client.get("/api/profile").get_json()
    assert latest["data"] == {"analogies": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app'` (raised inside the `client` fixture).

- [ ] **Step 3: Write minimal implementation**

`backend/app.py`:
```python
from flask import Flask, jsonify, request

from backend import db, events, profile, queries


def create_app(db_path=None):
    app = Flask(__name__)
    path = db_path or db.DEFAULT_DB_PATH

    # Ensure the schema exists at startup.
    init_conn = db.get_connection(path)
    db.init_db(init_conn)
    init_conn.close()

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/events")
    def post_events():
        body = request.get_json(silent=True) or {}
        conn = db.get_connection(path)
        try:
            result = events.insert_events(conn, body.get("events", []))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()
        return jsonify(result)

    @app.get("/api/events")
    def get_events():
        conn = db.get_connection(path)
        try:
            result = queries.query_events(
                conn,
                since=request.args.get("since"),
                session_id=request.args.get("session_id"),
                event_type=request.args.get("type"),
                limit=int(request.args.get("limit", 1000)),
            )
        finally:
            conn.close()
        return jsonify({"events": result})

    @app.post("/api/profile")
    def post_profile():
        body = request.get_json(silent=True) or {}
        conn = db.get_connection(path)
        try:
            result = profile.save_profile(conn, body)
        finally:
            conn.close()
        return jsonify(result)

    @app.get("/api/profile")
    def get_profile():
        conn = db.get_connection(path)
        try:
            result = profile.latest_profile(conn)
        finally:
            conn.close()
        return jsonify(result or {})

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tasks' tests — 20 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_api.py
git commit -m "feat(backend): Flask HTTP API for events and profile

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Deploy to the Pi and verify

**Files:**
- Create: `deploy/claude-university.service`

This task has no unit test — its deliverable is a running, reachable service on the Pi, verified by an HTTP round-trip from the Mac. Pi access: `ssh werner@192.168.2.69` (or the `mcp__pi-ssh__exec` tool). Pi app dir: `~/claude_university`.

**Interfaces:**
- Consumes: the full `backend/` package and `requirements.txt`.
- Produces: a systemd service `claude-university` listening on `0.0.0.0:8000`, serving the same API verified locally.

- [ ] **Step 1: Write the systemd unit**

`deploy/claude-university.service`:
```ini
[Unit]
Description=Claude University learning service
After=network.target

[Service]
WorkingDirectory=/home/werner/claude_university
ExecStart=/home/werner/claude_university/.venv/bin/waitress-serve --host=0.0.0.0 --port=8000 --call backend.app:create_app
Restart=always
User=werner

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Copy the project to the Pi**

From the Mac project root (excludes the local venv and test/db artifacts):
```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='backend/data' \
  /Users/wernervanellewee/Projects/Claude_Education/ \
  werner@192.168.2.69:~/claude_university/
```

- [ ] **Step 3: Create the venv and install deps on the Pi**

```bash
ssh werner@192.168.2.69 'cd ~/claude_university && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'
```
Expected: waitress and Flask install without error (pure-Python wheels, fine on aarch64).

- [ ] **Step 4: Install and start the service**

```bash
ssh werner@192.168.2.69 'sudo cp ~/claude_university/deploy/claude-university.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now claude-university'
```

- [ ] **Step 5: Verify the service is active**

```bash
ssh werner@192.168.2.69 'systemctl is-active claude-university'
```
Expected: `active`

- [ ] **Step 6: Verify the API end-to-end from the Mac**

```bash
curl -s http://192.168.2.69:8000/api/health
```
Expected: `{"status":"ok"}`

Round-trip an event and read it back:
```bash
curl -s -X POST http://192.168.2.69:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"client_event_id":"deploy-smoke-1","session_id":"s0","event_type":"deploy_check","occurred_at":"2026-06-21T12:00:00+00:00"}]}'
curl -s 'http://192.168.2.69:8000/api/events?type=deploy_check'
```
Expected: first call returns `{"accepted":1,"duplicates":0}`; second returns the event in `{"events":[...]}`.

- [ ] **Step 7: Confirm Claude can read the log over SSH**

```bash
ssh werner@192.168.2.69 'sqlite3 ~/claude_university/backend/data/learning.db "SELECT event_type, occurred_at FROM events;"'
```
Expected: lists the `deploy_check` row — confirming the on-Pi SQLite file is the readable source of truth.

- [ ] **Step 8: Commit**

```bash
git add deploy/claude-university.service
git commit -m "feat(deploy): systemd unit and Pi deployment for the learning service

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage (backend slice of the spec):**
- Data home = Pi service, SQLite source of truth → Tasks 1, 6. ✓
- Idempotent offline-first re-sync via `client_event_id` → Task 2. ✓
- Append-only event log with the captured fields (session, device, topic, type, time, payload) → Tasks 1–2. ✓
- Readable by Claude over SSH → Task 6 Step 7. ✓
- Versioned learner profile (diagnostic captured/stored/versioned) → Task 4. ✓
- Event querying for dashboard + Claude analysis → Task 3. ✓
- Reachable multi-device (LAN/Tailscale) → Task 6 binds `0.0.0.0`. ✓
- *Deferred to Plan 2 (correctly out of scope here):* serving the static frontend, the offline-first browser buffer, the diagnostic UI. The backend exposes the endpoints they will call.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to" — every step has complete code or an exact command. ✓

**3. Type consistency:** `get_connection`/`init_db` (Task 1) used unchanged in Tasks 2–5; `insert_events` return shape `{"accepted","duplicates"}` consistent across Tasks 2 and 5; `query_events` signature consistent across Tasks 3 and 5; `save_profile`/`latest_profile` consistent across Tasks 4 and 5. The `client`/`conn` fixtures defined in Task 1's `conftest.py` are used by all later tests. ✓
