def test_list_courses_includes_machine_learning(client):
    resp = client.get("/api/courses")
    assert resp.status_code == 200
    courses = resp.get_json()["courses"]
    ml = next(c for c in courses if c["id"] == "machine-learning")
    assert ml["title"] == "Machine Learning"
    assert ml["progress"]["total"] >= 1
    assert ml["nextLesson"]["id"] == "ml-m3-l2"


def test_get_course_manifest(client):
    resp = client.get("/api/courses/machine-learning")
    assert resp.status_code == 200
    assert resp.get_json()["modules"][0]["title"] == "Neural Networks"


def test_get_lesson_and_404s(client):
    ok = client.get("/api/courses/machine-learning/lessons/ml-m3-l2")
    assert ok.status_code == 200
    assert ok.get_json()["topic"] == "Backpropagation"
    assert client.get("/api/courses/machine-learning/lessons/nope").status_code == 404
    assert client.get("/api/courses/nope").status_code == 404


def test_post_course_creates_and_lists(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.post("/api/courses", json={
        "title": "Test Course",
        "subtitle": "sub",
        "brief": "ctx",
        "modules": [{"title": "M1", "lessons": [{"title": "L1"}]}],
    })
    assert resp.status_code == 201
    created = resp.get_json()["course"]
    assert created["id"] == "test-course"

    listed = client.get("/api/courses").get_json()["courses"]
    assert any(c["id"] == "test-course" for c in listed)


def test_post_course_rejects_missing_fields(client, tmp_path, monkeypatch):
    from backend import courses
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path / "courses")
    assert client.post("/api/courses", json={"title": "x"}).status_code == 400
    assert client.post("/api/courses", json={"modules": []}).status_code == 400


def test_routes_reject_illegal_ids(client):
    assert client.get("/api/courses/Bad_Id").status_code == 404
    assert client.get("/api/courses/machine-learning/lessons/..%2fsecret").status_code == 404
