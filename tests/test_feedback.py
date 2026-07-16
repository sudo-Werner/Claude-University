import pytest

from backend import app as app_module, db, feedback


@pytest.fixture()
def dbconn(tmp_path):
    conn = db.get_connection(tmp_path / "t.db")
    db.init_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def client(tmp_path):
    app = app_module.create_app(db_path=str(tmp_path / "t.db"))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, tmp_path / "t.db"


def _rows(db_path):
    conn = db.get_connection(db_path)
    try:
        return conn.execute(
            "SELECT created_at, screen, course_id, lesson_id, text, status FROM feedback"
        ).fetchall()
    finally:
        conn.close()


# ---- insert_feedback ----

def test_insert_feedback_stores_note_with_defaults(dbconn):
    feedback.insert_feedback(dbconn, text="  add dark mode  ", screen="lesson",
                             course_id="ml-course", lesson_id="l1")
    row = dbconn.execute("SELECT * FROM feedback").fetchone()
    assert row["text"] == "add dark mode"
    assert row["screen"] == "lesson"
    assert row["course_id"] == "ml-course"
    assert row["lesson_id"] == "l1"
    assert row["status"] == "new"
    assert row["created_at"]  # server-stamped, non-empty


@pytest.mark.parametrize("bad", [None, "", "   ", 42, ["x"], {"t": "x"}])
def test_insert_feedback_rejects_missing_or_blank_text(dbconn, bad):
    with pytest.raises(ValueError):
        feedback.insert_feedback(dbconn, text=bad)
    assert dbconn.execute("SELECT COUNT(*) c FROM feedback").fetchone()["c"] == 0


def test_insert_feedback_truncates_long_text(dbconn):
    feedback.insert_feedback(dbconn, text="x" * 5000)
    row = dbconn.execute("SELECT text FROM feedback").fetchone()
    assert len(row["text"]) == 4000


@pytest.mark.parametrize("bad_id", [42, "Bad_Id", "a b", "UPPER", "", "x" * 5 + "!"])
def test_insert_feedback_drops_bad_context_ids_to_null(dbconn, bad_id):
    feedback.insert_feedback(dbconn, text="note", course_id=bad_id, lesson_id=bad_id)
    row = dbconn.execute("SELECT course_id, lesson_id FROM feedback").fetchone()
    assert row["course_id"] is None
    assert row["lesson_id"] is None


def test_insert_feedback_drops_bad_screen_to_null(dbconn):
    feedback.insert_feedback(dbconn, text="a", screen="s" * 41)
    feedback.insert_feedback(dbconn, text="b", screen=7)
    feedback.insert_feedback(dbconn, text="c", screen="   ")
    rows = dbconn.execute("SELECT screen FROM feedback").fetchall()
    assert all(r["screen"] is None for r in rows)


def test_init_db_twice_is_idempotent(tmp_path):
    conn = db.get_connection(tmp_path / "t.db")
    db.init_db(conn)
    db.init_db(conn)  # CREATE TABLE IF NOT EXISTS — must not raise
    feedback.insert_feedback(conn, text="still works")
    assert conn.execute("SELECT COUNT(*) c FROM feedback").fetchone()["c"] == 1
    conn.close()


# ---- POST /api/feedback ----

def test_post_feedback_happy_path_writes_row(client):
    c, db_path = client
    resp = c.post("/api/feedback", json={
        "text": "the review screen needs a back button",
        "screen": "review", "courseId": "ml-course", "lessonId": "l2",
    })
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    rows = _rows(db_path)
    assert len(rows) == 1
    assert rows[0]["text"] == "the review screen needs a back button"
    assert rows[0]["screen"] == "review"
    assert rows[0]["course_id"] == "ml-course"
    assert rows[0]["lesson_id"] == "l2"
    assert rows[0]["status"] == "new"


@pytest.mark.parametrize("body", [
    {},
    {"text": ""},
    {"text": "   "},
    {"text": 42},
    {"text": ["note"]},
])
def test_post_feedback_400_without_text(client, body):
    c, db_path = client
    resp = c.post("/api/feedback", json=body)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "feedback text is required"}
    assert _rows(db_path) == []


@pytest.mark.parametrize("body", ["just a string", [1, 2], 42, None])
def test_post_feedback_never_500s_on_non_dict_bodies(client, body):
    c, _ = client
    resp = c.post("/api/feedback", json=body)
    assert resp.status_code == 400


def test_post_feedback_keeps_note_when_context_is_forged(client):
    c, db_path = client
    resp = c.post("/api/feedback", json={
        "text": "note survives bad metadata",
        "screen": {"x": 1}, "courseId": "../etc", "lessonId": 99,
    })
    assert resp.status_code == 200
    rows = _rows(db_path)
    assert rows[0]["text"] == "note survives bad metadata"
    assert rows[0]["screen"] is None
    assert rows[0]["course_id"] is None
    assert rows[0]["lesson_id"] is None


def test_post_feedback_without_json_body_is_400(client):
    c, _ = client
    resp = c.post("/api/feedback", data="not json", content_type="text/plain")
    assert resp.status_code == 400
