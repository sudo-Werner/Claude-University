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
        "apply": {"prompt": "<p>A novel scenario.</p>", "modelAnswer": "Covers X and Y."},
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


def test_prompt_has_mcq_self_verification_and_apply_clause():
    p = remediation.remediation_prompt(manifest=_manifest(), exam_key="m1",
                                       weak_spots=WEAK, spine_lessons={})
    assert "re-answer each mcq question independently" in p
    assert "Confirm the choice at answer is the answer you get" in p
    assert "no distractor is also defensibly correct" in p
    assert "APPLY the objective" in p and "apply or higher" in p


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


def test_prompt_demands_apply_item_with_novel_scenario():
    p = remediation.remediation_prompt(manifest=_manifest(), exam_key="m1",
                                       weak_spots=WEAK, spine_lessons={})
    assert '"apply"' in p and '"modelAnswer"' in p
    assert "NOVEL scenario, case, or problem that does not appear in the lessons" in p


def test_valid_remediation_requires_apply_on_new_generations():
    good = _gaps(WEAK)
    assert remediation.valid_remediation(good, WEAK)
    missing = json.loads(json.dumps(good)); del missing["gaps"][0]["apply"]
    assert not remediation.valid_remediation(missing, WEAK)
    empty = json.loads(json.dumps(good)); empty["gaps"][0]["apply"]["prompt"] = " "
    assert not remediation.valid_remediation(empty, WEAK)
    no_model = json.loads(json.dumps(good)); no_model["gaps"][0]["apply"]["modelAnswer"] = ""
    assert not remediation.valid_remediation(no_model, WEAK)


def test_finalize_sanitizes_apply_fields():
    raw = _gaps(WEAK)
    raw["gaps"][0]["apply"] = {"prompt": "<p>Scenario <script>x()</script></p>",
                               "modelAnswer": "Covers <script>y()</script> Z"}
    s = remediation.finalize_session(raw, WEAK, "m1", "c1", 2)
    assert "<script>" not in s["gaps"][0]["apply"]["prompt"]
    assert "<script>" not in s["gaps"][0]["apply"]["modelAnswer"]
    assert s["gaps"][1]["apply"]["modelAnswer"] == "Covers X and Y."


def _mark(conn, i, event_type, payload, topic_id="c1-l1"):
    events.insert_events(conn, [{
        "client_event_id": f"mk-{event_type}-{i}", "session_id": "s1",
        "event_type": event_type, "occurred_at": f"2026-07-16T10:{i:02d}:00+00:00",
        "course_id": "c1", "topic_id": topic_id, "payload": payload,
    }])


def _check_payload(index, attempt=1, **overrides):
    p = {"index": index, "type": "mcq", "correct": True, "source": "remediation",
         "examKey": "m1", "attempt": attempt}
    p.update(overrides)
    return p


def test_session_completed_requires_all_practice_and_apply(tmp_path):
    conn = _conn()
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    # 2 gaps x 2 practice = flat indices 0..3, plus one apply per gap (indices 0 and 1)
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # applies missing
    _mark(conn, 10, "lesson_explained", {"verdict": "correct", "source": "remediation",
                                         "examKey": "m1", "attempt": 1, "index": 0})
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    _mark(conn, 11, "lesson_explained", {"verdict": "close", "source": "remediation",
                                         "examKey": "m1", "attempt": 1, "index": 1})
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)


def test_session_completed_false_without_session_or_on_stale_attempt(tmp_path):
    conn = _conn()
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # nothing on disk
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    for gi in range(2):
        _mark(conn, 10 + gi, "lesson_explained",
              {"verdict": "correct", "source": "remediation", "examKey": "m1",
               "attempt": 1, "index": gi})
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    # a newer failed attempt makes the stored session stale -> not completed
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 2)


def test_session_completed_ignores_unmarked_and_malformed_events(tmp_path):
    conn = _conn()
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    # legacy remediation answers: no examKey/attempt markers -> must not count
    for i in range(4):
        _mark(conn, i, "lesson_check",
              {"index": i, "type": "mcq", "correct": True, "source": "remediation"})
    # forged garbage must be skipped, never raised on
    _mark(conn, 20, "lesson_check", "not-a-dict")
    _mark(conn, 21, "lesson_check", _check_payload("zero"))          # non-int index
    _mark(conn, 22, "lesson_check", _check_payload(99))              # out of range
    _mark(conn, 23, "lesson_check", _check_payload(0, examKey="final"))
    _mark(conn, 24, "lesson_check", _check_payload(0, attempt=7))
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)


def test_session_completed_legacy_session_without_apply(tmp_path):
    conn = _conn()
    legacy = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    for g in legacy["gaps"]:
        del g["apply"]                                               # session from before this ships
    remediation.save_session(tmp_path, "c1", legacy)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # practice alone suffices


def test_session_completed_ignores_gap_with_unusable_apply(tmp_path):
    # A gap whose apply dict is present but blank (e.g. a stripped/whitespace
    # prompt) must not be treated as "has an apply task": the grade route
    # (backend/app.py grade_remediation_apply) would refuse to grade it, so
    # counting it as expected would permanently lock the retake.
    conn = _conn()
    raw = _gaps(WEAK[:1])
    raw["gaps"][0]["apply"] = {"prompt": " ", "modelAnswer": "x"}
    s = remediation.finalize_session(raw, WEAK[:1], "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    for i in range(2):                                             # 1 gap x 2 practice items
        _mark(conn, i, "lesson_check", _check_payload(i))
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # unusable apply not expected
