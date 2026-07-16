import json

from backend import capstone, db, events


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _manifest():
    return {"id": "c1", "title": "Course", "brief": "b",
            "outcomes": [{"text": "Do the course thing", "bloom": "apply", "knowledge": "procedural"}],
            "modules": [{"id": "m1", "title": "Mod One",
                         "outcomes": [{"text": "Do X well", "bloom": "apply", "knowledge": "procedural"}],
                         "lessons": [{"id": "c1-l1", "title": "L1"}]}]}


def _capstone(scope="m1", title="Mod One"):
    return {"scope": scope, "title": title, "intro": "Real world.",
            "items": [{"title": "AlphaFold", "detail": "d", "source": "s"},
                      {"title": "GPS", "detail": "d", "source": "s"}]}


RUBRIC4 = [{"criterion": f"Criterion {i}"} for i in range(4)]


def _grade(mets, summary="Overall solid."):
    return {"perCriterion": [
        {"index": i, "met": m, "note": "Shows it.", "evidence": "a quote"}
        for i, m in enumerate(mets)], "summary": summary}


def _fake_generate(rubric_obj, grade_obj):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = grade_obj if '"perCriterion"' in prompt else rubric_obj
        assert validate(obj)
        return obj

    gen.calls = calls
    return gen


def _write_capstone(tmp_path, cap, scope="m1"):
    p = tmp_path / "c1" / "capstones" / f"{scope}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap))
    return p


def test_valid_rubric_bounds_and_shapes():
    assert capstone.valid_rubric(RUBRIC4)
    assert capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(6)])
    assert not capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(3)])   # too few
    assert not capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(7)])   # too many
    assert not capstone.valid_rubric([{"criterion": ""}] * 4)                       # empty text
    assert not capstone.valid_rubric([{"criterion": "ok"}] * 3 + ["not a dict"])
    assert not capstone.valid_rubric("nope")
    assert not capstone.valid_rubric(None)                                          # legacy: no rubric


def test_load_capstone_missing_and_corrupt(tmp_path):
    assert capstone.load_capstone(tmp_path, "c1", "m1") is None
    p = _write_capstone(tmp_path, _capstone())
    assert capstone.load_capstone(tmp_path, "c1", "m1")["title"] == "Mod One"
    p.write_text("{nope")
    assert capstone.load_capstone(tmp_path, "c1", "m1") is None


def test_ensure_rubric_upgrades_legacy_file_and_escapes(tmp_path):
    _write_capstone(tmp_path, _capstone())          # legacy Pi cache: no rubric field
    gen = _fake_generate({"rubric": [{"criterion": "Uses <b>real</b> data"}] + RUBRIC4[:3]}, None)
    cap = capstone.load_capstone(tmp_path, "c1", "m1")
    out = capstone.ensure_rubric(tmp_path, "c1", "m1", cap, _manifest(), generate=gen)
    assert len(out["rubric"]) == 4
    assert out["rubric"][0]["criterion"] == "Uses &lt;b&gt;real&lt;/b&gt; data"     # plain-text escaped
    assert "AlphaFold" in gen.calls[0] and "Do X well" in gen.calls[0]              # items + module objectives
    saved = json.loads((tmp_path / "c1" / "capstones" / "m1.json").read_text())
    assert saved["rubric"] == out["rubric"]                                          # persisted upgrade
    assert saved["items"] == cap["items"]                                            # extended, not regenerated


def test_ensure_rubric_course_scope_uses_course_outcomes(tmp_path):
    _write_capstone(tmp_path, _capstone(scope="course", title="Course"), scope="course")
    gen = _fake_generate({"rubric": RUBRIC4}, None)
    cap = capstone.load_capstone(tmp_path, "c1", "course")
    capstone.ensure_rubric(tmp_path, "c1", "course", cap, _manifest(), generate=gen)
    assert "Do the course thing" in gen.calls[0]


def test_ensure_rubric_skips_generation_when_valid_rubric_present(tmp_path):
    cap = {**_capstone(), "rubric": RUBRIC4}
    _write_capstone(tmp_path, cap)
    gen = _fake_generate(None, None)
    out = capstone.ensure_rubric(tmp_path, "c1", "m1", cap, _manifest(), generate=gen)
    assert out["rubric"] == RUBRIC4 and gen.calls == []


def test_valid_capstone_grade_matrix():
    ok = _grade(["met", "partial", "unmet", "met"])
    assert capstone.valid_capstone_grade(ok, RUBRIC4)
    empty_evidence = _grade(["met", "met", "met", "met"])
    empty_evidence["perCriterion"][2]["evidence"] = ""
    assert capstone.valid_capstone_grade(empty_evidence, RUBRIC4)   # empty evidence allowed
    assert not capstone.valid_capstone_grade({"perCriterion": ok["perCriterion"][:3],
                                              "summary": "s"}, RUBRIC4)             # wrong count
    dup = json.loads(json.dumps(ok)); dup["perCriterion"][1]["index"] = 0
    assert not capstone.valid_capstone_grade(dup, RUBRIC4)                            # duplicate index
    out_of_range = json.loads(json.dumps(ok)); out_of_range["perCriterion"][3]["index"] = 9
    assert not capstone.valid_capstone_grade(out_of_range, RUBRIC4)
    bad_met = json.loads(json.dumps(ok)); bad_met["perCriterion"][0]["met"] = "kinda"
    assert not capstone.valid_capstone_grade(bad_met, RUBRIC4)
    no_note = json.loads(json.dumps(ok)); no_note["perCriterion"][0]["note"] = " "
    assert not capstone.valid_capstone_grade(no_note, RUBRIC4)
    no_evidence = json.loads(json.dumps(ok)); del no_evidence["perCriterion"][0]["evidence"]
    assert not capstone.valid_capstone_grade(no_evidence, RUBRIC4)                    # evidence mandatory
    no_summary = json.loads(json.dumps(ok)); no_summary["summary"] = ""
    assert not capstone.valid_capstone_grade(no_summary, RUBRIC4)
    assert not capstone.valid_capstone_grade("nope", RUBRIC4)


def test_score_grade_and_threshold():
    assert capstone.CAPSTONE_PASS == 0.7
    per = _grade(["met", "met", "partial", "unmet"])["perCriterion"]
    assert capstone.score_grade(per) == 0.625                                        # (1+1+.5+0)/4
    exact = _grade(["met", "met", "met", "partial", "unmet"])["perCriterion"]
    assert capstone.score_grade(exact) == 0.7                                        # 3.5/5, passes at >=
    assert capstone.score_grade(_grade(["met"] * 4)["perCriterion"]) == 1.0


def test_record_result_stamps_attempts_and_drops_evidence():
    conn = _conn()
    result = {"scope": "m1", "score": 1.0, "passed": True, "summary": "s",
              "perCriterion": [{"index": 0, "met": "met", "note": "n", "evidence": "quote"}]}
    assert capstone.record_result(conn, "c1", "m1", result) == 1
    assert capstone.record_result(conn, "c1", "m1", result) == 2
    assert capstone.record_result(conn, "c1", "course", result) == 1                 # per-scope counter
    rows = conn.execute(
        "SELECT payload FROM events WHERE event_type = 'capstone_result' "
        "AND course_id = 'c1' AND topic_id = 'm1' ORDER BY id ASC").fetchall()
    payloads = [json.loads(r["payload"]) for r in rows]
    assert [p["attempt"] for p in payloads] == [1, 2]
    assert payloads[0]["perCriterion"][0] == {"index": 0, "met": "met", "note": "n"}  # no evidence stored


def test_submit_capstone_none_without_file(tmp_path):
    conn = _conn()
    gen = _fake_generate({"rubric": RUBRIC4}, _grade(["met"] * 4))
    assert capstone.submit_capstone(tmp_path, conn, "c1", "m1", "work",
                                    manifest=_manifest(), generate=gen) is None
    assert gen.calls == []


def test_submit_capstone_happy_path_sanitizes_and_records(tmp_path):
    conn = _conn()
    _write_capstone(tmp_path, _capstone())
    grade = _grade(["met", "met", "met", "partial"], summary="Good <script>x</script> work")
    grade["perCriterion"][0]["note"] = "Nice <script>alert(1)</script> start"
    gen = _fake_generate({"rubric": RUBRIC4}, grade)
    out = capstone.submit_capstone(tmp_path, conn, "c1", "m1", "my work",
                                   manifest=_manifest(), generate=gen)
    assert out["score"] == 0.875 and out["passed"] is True and out["attempt"] == 1
    assert out["scope"] == "m1" and len(out["rubric"]) == 4
    assert out["perCriterion"][0]["evidence"] == "a quote"                            # API keeps evidence
    assert "<script>" not in out["perCriterion"][0]["note"]                           # sanitized
    assert "<script>" not in out["summary"]
    assert len(gen.calls) == 2                                                        # rubric, then grade
    row = conn.execute("SELECT payload FROM events WHERE event_type = 'capstone_result'").fetchone()
    assert json.loads(row["payload"])["attempt"] == 1
