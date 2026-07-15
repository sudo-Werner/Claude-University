import json


def _valid_compiled(cid):
    """Build a minimal valid schemaVersion-2 course with lesson ids <cid>-l1 and <cid>-l2."""
    OBJ = {"text": "Calculate the result", "bloom": "apply", "knowledge": "procedural"}
    return {
        "schemaVersion": 2,
        "id": cid,
        "title": "Test Course",
        "subtitle": "A test",
        "brief": "For testing",
        "learnerBrief": {"goal": "g"},
        "level": {"code": "bachelor-y1", "label": "Bachelor Y1"},
        "targetHours": 10,
        "skills": ["skill one"],
        "outcomes": [OBJ],
        "groundingSources": [],
        "modules": [{
            "id": "m1",
            "title": "Module One",
            "outcomes": [OBJ],
            "lessons": [
                {"id": f"{cid}-l1", "title": "Lesson One", "estMinutes": 30,
                 "objectives": [OBJ], "prereqs": []},
                {"id": f"{cid}-l2", "title": "Lesson Two", "estMinutes": 45,
                 "objectives": [OBJ], "prereqs": [f"{cid}-l1"]},
            ],
        }],
    }


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


def test_load_manifest_returns_none_on_corrupt_json(tmp_path):
    from backend import courses
    course_dir = tmp_path / "c1"
    course_dir.mkdir()
    (course_dir / "course.json").write_text('{"id": "c1", "title": ')  # truncated write
    assert courses.load_manifest(tmp_path, "c1") is None


def test_load_lesson_returns_none_on_corrupt_json(tmp_path):
    from backend import courses
    lessons = tmp_path / "c1" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "c1-l1.json").write_text('{"id": "c1-l1"')  # truncated write
    assert courses.load_lesson(tmp_path, "c1", "c1-l1") is None


def test_progress_starts_at_zero_and_points_at_first(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    p = courses.course_progress(conn, root, "demo")
    assert p == {"done": 0, "total": 2, "pct": 0,
                 "nextLesson": {"id": "l1", "title": "Lesson One", "moduleTitle": "Module One",
                                "objectives": []}}


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


def test_slug_for_is_url_safe_and_deduped():
    from backend import courses
    assert courses.slug_for("Linear Algebra for ML!", set()) == "linear-algebra-for-ml"
    assert courses.slug_for("Go", {"go"}) == "go-2"
    assert courses.slug_for("Go", {"go", "go-2"}) == "go-3"
    assert courses.slug_for("***", set()) == "course"


def test_write_course_creates_manifest_with_brief_and_ids(tmp_path):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    proposal = {
        "title": "Intro Stats",
        "subtitle": "From scratch",
        "brief": "Beginner, 2h/week, wants intuition first.",
        "modules": [
            {"title": "Basics", "lessons": [{"title": "Mean & median"}, {"title": "Variance"}]},
        ],
    }
    manifest = courses.write_course(root, proposal)
    assert manifest["id"] == "intro-stats"
    assert manifest["brief"] == "Beginner, 2h/week, wants intuition first."
    assert manifest["modules"][0]["id"] == "m1"
    ids = [l["id"] for l in manifest["modules"][0]["lessons"]]
    assert ids == ["intro-stats-l1", "intro-stats-l2"]
    # persisted + lessons dir created
    on_disk = courses.load_manifest(root, "intro-stats")
    assert on_disk["title"] == "Intro Stats"
    assert (root / "intro-stats" / "lessons").is_dir()


def test_write_course_legacy_shape_unchanged(tmp_path):
    from backend import courses
    m = courses.write_course(tmp_path, {"title": "Old Way", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L1"}, {"title": "L2"}]}]})
    assert m["id"] == "old-way"
    assert [l["id"] for l in m["modules"][0]["lessons"]] == ["old-way-l1", "old-way-l2"]
    assert "schemaVersion" not in m


def test_write_course_compiled_shape_slugs_ids_and_remaps_prereqs(tmp_path):
    from backend import courses
    OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
    compiled = {"schemaVersion": 2, "title": "Deep ML", "subtitle": "s", "brief": "b",
        "learnerBrief": {"goal": "g"}, "level": {"code": "master", "label": "Master-equivalent"},
        "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ], "groundingSources": [],
        "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
            {"id": "l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []},
            {"id": "l2", "title": "B", "estMinutes": 60, "objectives": [OBJ], "prereqs": ["l1"]}]}]}
    m = courses.write_course(tmp_path, compiled)
    assert m["schemaVersion"] == 2 and m["level"]["code"] == "master" and m["targetHours"] == 130
    lessons = m["modules"][0]["lessons"]
    assert [l["id"] for l in lessons] == ["deep-ml-l1", "deep-ml-l2"]
    assert lessons[1]["prereqs"] == ["deep-ml-l1"]                 # prereq remapped to slugged id
    assert lessons[0]["objectives"] == [OBJ] and lessons[0]["estMinutes"] == 90
    # persisted file matches the returned manifest
    import json
    on_disk = json.loads((tmp_path / "deep-ml" / "course.json").read_text())
    assert on_disk == m


def test_flatten_lessons_includes_objectives():
    from backend import courses
    OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
    manifest = {"modules": [{"id": "m1", "title": "M", "lessons": [
        {"id": "c-l1", "title": "A", "objectives": [OBJ]}, {"id": "c-l2", "title": "B"}]}]}
    flat = courses.flatten_lessons(manifest)
    assert flat[0]["objectives"] == [OBJ] and flat[1]["objectives"] == []


def test_completed_counts_reviewed_events(conn, tmp_path):
    from backend import courses, events
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(__import__("json").dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    events.insert_events(conn, [{
        "client_event_id": "r1", "session_id": "s1", "event_type": "lesson_reviewed",
        "occurred_at": "2026-01-01T09:00:00+00:00", "course_id": "demo",
        "topic_id": "demo-l1", "payload": {"quality": "good"},
    }])
    assert "demo-l1" in courses.completed_lesson_ids(conn, "demo")


def test_apply_revision_writes_in_place_backs_up_and_preserves_bodies(tmp_path):
    from backend import courses
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "c-l1", "title": "One"}]}]}))
    (course / "lessons" / "c-l1.json").write_text('{"id": "c-l1"}')  # retained body
    revised = _valid_compiled("c")  # schemaVersion-2 course with ids c-l1 + new c-l2
    out = courses.apply_revision(cdir, "c", revised, now="20260709T120000Z")
    assert out is not None
    on_disk = json.loads((course / "course.json").read_text())
    ids = [l.get("id") for m in on_disk.get("modules", []) for l in m.get("lessons", [])]
    assert on_disk["schemaVersion"] == 2 and ids  # written in place
    assert (course / "course.json.pre-revise-20260709T120000Z").exists()        # backup made
    assert (course / "lessons" / "c-l1.json").exists()                           # body preserved


def test_apply_revision_rejects_tampered_course(tmp_path):
    from backend import courses
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "c-l1", "title": "One"}]}]}))
    foreign = _valid_compiled("c")
    foreign["modules"][0]["lessons"].append({"id": "other-l9", "title": "X",
        "objectives": [{"text": "Calculate y", "bloom": "apply", "knowledge": "procedural"}],
        "estMinutes": 30, "prereqs": [f"c-l1", f"c-l2"]})  # bad id pattern
    assert courses.apply_revision(cdir, "c", foreign, now="t") is None
    assert courses.apply_revision(cdir, "c", {**foreign, "id": "d"}, now="t") is None  # id mismatch


def test_apply_revision_prunes_spine_entries_for_removed_lessons(tmp_path):
    from backend import courses, spine
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [{"id": "m1", "title": "M", "lessons": [
            {"id": "c-l1", "title": "One"}, {"id": "c-l2", "title": "Two"}]}]}))
    entry = {"summary": "s", "concepts": [{"term": "t", "definition": "d"}]}
    spine.upsert_entry(cdir, "c", "c-l1", entry)
    spine.upsert_entry(cdir, "c", "c-l2", entry)
    revised = _valid_compiled("c")
    revised["modules"][0]["lessons"] = revised["modules"][0]["lessons"][:1]  # keep only c-l1
    out = courses.apply_revision(cdir, "c", revised, now="20260715T120000Z")
    assert out is not None
    assert set(spine.load_spine(cdir, "c")["lessons"]) == {"c-l1"}


def test_apply_revision_prunes_dropped_module_exams(tmp_path):
    from backend import courses
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [
            {"id": "m1", "title": "M1", "lessons": [{"id": "c-l1", "title": "One"}]},
            {"id": "m2", "title": "M2", "lessons": [{"id": "c-l3", "title": "Three"}]},
        ]}))
    exams_dir = course / "exams"
    exams_dir.mkdir()
    for key in ("m1", "m2", "final"):
        (exams_dir / f"{key}.json").write_text(json.dumps({"questions": []}))
    revised = _valid_compiled("c")  # keeps only module m1 → m2 is dropped
    out = courses.apply_revision(cdir, "c", revised, now="20260715T120001Z")
    assert out is not None
    assert (exams_dir / "m1.json").exists()
    assert (exams_dir / "final.json").exists()
    assert not (exams_dir / "m2.json").exists()


def test_list_courses_includes_passed_flag(conn, tmp_path):
    from backend import courses
    root = _make_course(tmp_path)
    summaries = courses.list_courses(conn, root)
    assert summaries and summaries[0]["passed"] is False
