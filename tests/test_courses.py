import json


def _make_course(tmp_path):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "A demo course",
        "modules": [
            {"id": "m1", "title": "Module One", "lessons": [
                {"id": "l1", "title": "Lesson One"},
                {"id": "l2", "title": "Lesson Two"},
            ]},
        ],
    }))
    (root / "demo" / "lessons" / "l1.json").write_text(json.dumps({
        "id": "l1", "courseId": "demo", "topic": "One", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "p", "hintHtml": "h",
        "solutionAns": "a", "solutionNote": "n",
    }))
    return root


def test_load_manifest_and_lesson(tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    manifest = courses.load_manifest(root, "demo")
    assert manifest["title"] == "Demo"
    lesson = courses.load_lesson(root, "demo", "l1")
    assert lesson["topic"] == "One"
    assert courses.load_manifest(root, "nope") is None
    assert courses.load_lesson(root, "demo", "nope") is None


def test_flatten_lessons_keeps_order_and_module(tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    flat = courses.flatten_lessons(courses.load_manifest(root, "demo"))
    assert [l["id"] for l in flat] == ["l1", "l2"]
    assert flat[0]["moduleTitle"] == "Module One"


def test_progress_starts_at_zero_and_points_at_first(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    p = courses.course_progress(conn, root, "demo")
    assert p == {"done": 0, "total": 2, "pct": 0,
                 "nextLesson": {"id": "l1", "title": "Lesson One", "moduleTitle": "Module One"}}


def test_completing_a_lesson_advances_progress(conn, tmp_path):
    from backend import courses, events
    root = _make_course(tmp_path)
    events.insert_events(conn, [{
        "client_event_id": "ce-1", "session_id": "s1",
        "event_type": "lesson_completed", "occurred_at": "2026-06-22T19:00:00+00:00",
        "course_id": "demo", "topic_id": "l1",
    }])
    p = courses.course_progress(conn, root, "demo")
    assert p["done"] == 1
    assert p["pct"] == 50
    assert p["nextLesson"]["id"] == "l2"


def test_list_courses_returns_summary(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    listed = courses.list_courses(conn, root)
    assert len(listed) == 1
    summary = listed[0]
    assert summary["id"] == "demo"
    assert summary["progress"] == {"done": 0, "total": 2, "pct": 0}
    assert summary["nextLesson"]["id"] == "l1"
    assert summary["reviewsDue"] == 0


def test_list_courses_skips_malformed_course_json(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    # Add a second course with invalid JSON in course.json
    bad_dir = root / "bad-course" / "lessons"
    bad_dir.mkdir(parents=True)
    (root / "bad-course" / "course.json").write_text("{ not valid json")
    # Should not raise; only the valid course is returned
    listed = courses.list_courses(conn, root)
    assert len(listed) == 1
    assert listed[0]["id"] == "demo"
