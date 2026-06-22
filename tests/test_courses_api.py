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
