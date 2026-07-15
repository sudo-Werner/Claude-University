import json

from backend import db, events, remediation


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _manifest():
    return {"id": "c1", "title": "Course", "brief": "b", "modules": [
        {"id": "m1", "title": "Mod One", "lessons": [
            {"id": "c1-l1", "title": "L1"}, {"id": "c1-l2", "title": "L2"}]}]}


WEAK = [{"lessonId": "c1-l1", "lessonTitle": "L1", "objectives": ["obj a"]},
        {"lessonId": "c1-l2", "lessonTitle": "L2", "objectives": ["obj b", "obj c"]}]


def _result(conn, exam_key, payload, occurred, i=0):
    events.insert_events(conn, [{
        "client_event_id": f"e-{exam_key}-{occurred}-{i}", "session_id": "s",
        "event_type": "exam_result", "occurred_at": occurred,
        "course_id": "c1", "topic_id": exam_key, "payload": payload,
    }])


def _gaps(weak):
    return {"gaps": [{
        "lessonId": w["lessonId"],
        "explanationHtml": "<p>An analogy.</p>",
        "practice": [
            {"type": "mcq", "prompt": "<p>Q</p>", "choices": ["a", "b", "c"],
             "answer": 1, "explanation": "because"},
            {"type": "fill", "prompt": "Blank?", "answer": "word", "explanation": "why"},
        ],
    } for w in weak]}


def test_latest_failed_result_returns_newest_fail():
    conn = _conn()
    _result(conn, "m1", {"passed": False, "attempt": 1, "weakSpots": WEAK},
            "2026-07-10T10:00:00+00:00")
    _result(conn, "m1", {"passed": False, "attempt": 2, "weakSpots": WEAK[:1]},
            "2026-07-12T10:00:00+00:00")
    got = remediation.latest_failed_result(conn, "c1", "m1")
    assert got["attempt"] == 2 and len(got["weakSpots"]) == 1


def test_latest_failed_result_none_when_latest_passed_or_absent():
    conn = _conn()
    assert remediation.latest_failed_result(conn, "c1", "m1") is None
    _result(conn, "m1", {"passed": False, "attempt": 1, "weakSpots": WEAK},
            "2026-07-10T10:00:00+00:00")
    _result(conn, "m1", {"passed": True, "attempt": 2, "weakSpots": []},
            "2026-07-12T10:00:00+00:00")
    assert remediation.latest_failed_result(conn, "c1", "m1") is None


def test_prompt_names_gaps_and_demands_new_angle():
    p = remediation.remediation_prompt(manifest=_manifest(), exam_key="m1",
                                       weak_spots=WEAK, spine_lessons={})
    assert "lessonId=c1-l1" in p and "obj b; obj c" in p
    assert "DIFFERENT angle" in p and '"gaps"' in p
    assert p.count("lessonId=") == 2


def test_valid_remediation_accepts_good_and_rejects_misaligned():
    good = _gaps(WEAK)
    assert remediation.valid_remediation(good, WEAK)
    swapped = {"gaps": list(reversed(good["gaps"]))}
    assert not remediation.valid_remediation(swapped, WEAK)
    assert not remediation.valid_remediation({"gaps": good["gaps"][:1]}, WEAK)
    one = json.loads(json.dumps(good)); one["gaps"][0]["practice"] = one["gaps"][0]["practice"][:1]
    assert not remediation.valid_remediation(one, WEAK)          # < PRACTICE_MIN
    bad = json.loads(json.dumps(good)); bad["gaps"][0]["practice"][0]["answer"] = 9
    assert not remediation.valid_remediation(bad, WEAK)          # invalid check


def test_finalize_sanitizes_and_stamps_metadata():
    raw = _gaps(WEAK)
    raw["gaps"][0]["explanationHtml"] = '<p onclick="x()">hi</p><script>bad()</script>'
    raw["gaps"][0]["practice"][0]["prompt"] = "<p>Q <script>x</script></p>"
    s = remediation.finalize_session(raw, WEAK, "m1", "c1", 2)
    assert s["attempt"] == 2 and s["examKey"] == "m1"
    assert s["gaps"][0]["lessonTitle"] == "L1" and s["gaps"][0]["objectives"] == ["obj a"]
    assert "<script>" not in s["gaps"][0]["explanationHtml"]
    assert "<p onclick" not in s["gaps"][0]["explanationHtml"]
    assert "<script>" not in s["gaps"][0]["practice"][0]["prompt"]
    assert s["gaps"][0]["practice"][1]["answer"] == "word"       # fill answer untouched


def test_persistence_roundtrip_corrupt_and_prune(tmp_path):
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    assert remediation.load_session(tmp_path, "c1", "m1")["attempt"] == 1
    (tmp_path / "c1" / "remediation" / "m1.json").write_text("{nope")
    assert remediation.load_session(tmp_path, "c1", "m1") is None
    remediation.save_session(tmp_path, "c1", s)
    remediation.save_session(tmp_path, "c1", {**s, "examKey": "final"})
    remediation.prune(tmp_path, "c1", {"final"})
    assert remediation.load_session(tmp_path, "c1", "m1") is None
    assert remediation.load_session(tmp_path, "c1", "final") is not None


def test_ensure_session_reuses_fresh_and_regenerates_stale(tmp_path):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = _gaps(WEAK)
        assert validate(obj)
        return obj

    payload = {"passed": False, "attempt": 1, "weakSpots": WEAK}
    s1 = remediation.ensure_session(tmp_path, "c1", "m1", payload,
                                    manifest=_manifest(), spine_lessons={}, generate=gen)
    assert s1["attempt"] == 1 and len(calls) == 1
    s2 = remediation.ensure_session(tmp_path, "c1", "m1", payload,
                                    manifest=_manifest(), spine_lessons={}, generate=gen)
    assert s2["attempt"] == 1 and len(calls) == 1                 # served from disk
    payload2 = {"passed": False, "attempt": 2, "weakSpots": WEAK[:1]}
    s3 = remediation.ensure_session(tmp_path, "c1", "m1", payload2,
                                    manifest=_manifest(), spine_lessons={},
                                    generate=lambda p, v: _gaps(WEAK[:1]))
    assert s3["attempt"] == 2 and len(s3["gaps"]) == 1            # regenerated
