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
