import json

from backend import events, exams


def _manifest():
    def obj(text, bloom):
        return {"text": text, "bloom": bloom, "knowledge": "conceptual"}
    return {
        "id": "c1", "title": "Course One", "brief": "A course.",
        "outcomes": [{"text": "Do things", "bloom": "apply"}],
        "modules": [
            {"id": "m1", "title": "Module One",
             "outcomes": ["Understand basics"],
             "lessons": [
                 {"id": "c1-l1", "title": "L1", "objectives": [obj("o1a", "remember"), obj("o1b", "apply")]},
                 {"id": "c1-l2", "title": "L2", "objectives": [obj("o2a", "understand")]},
                 {"id": "c1-l3", "title": "L3", "objectives": [obj("o3a", "analyze"), obj("o3b", "evaluate")]},
             ]},
            {"id": "m2", "title": "Module Two",
             "lessons": [
                 {"id": "c1-l4", "title": "L4", "objectives": [obj("o4a", "apply"), obj("o4b", "remember")]},
                 {"id": "c1-l5", "title": "L5", "objectives": [obj("o5a", "create")]},
             ]},
        ],
    }


def _questions_for(slots):
    out = []
    for s in slots:
        q = {"type": s["type"], "lessonId": s["lessonId"], "prompt": "<p>Q?</p>"}
        if s["type"] == "mcq":
            q["choices"] = ["a", "b", "c", "d"]
            q["answerIndex"] = 1
        else:
            q["modelAnswer"] = "ref"
            q["graderNotes"] = "notes"
        out.append(q)
    return {"questions": out}


def test_module_blueprint_covers_every_lesson_exactly_ten():
    slots = exams.module_blueprint(_manifest(), "m1")
    assert len(slots) == exams.MODULE_EXAM_QUESTIONS == 10
    assert {s["lessonId"] for s in slots} == {"c1-l1", "c1-l2", "c1-l3"}


def test_module_blueprint_formats_follow_bloom():
    slots = exams.module_blueprint(_manifest(), "m1")
    for s in slots:
        expected = "mcq" if s["bloom"] in exams.MCQ_BLOOMS else "free"
        assert s["type"] == expected


def test_module_blueprint_unknown_module_is_none():
    assert exams.module_blueprint(_manifest(), "nope") is None


def test_final_blueprint_covers_every_module_exactly_eighteen():
    slots = exams.final_blueprint(_manifest())
    assert len(slots) == exams.FINAL_EXAM_QUESTIONS == 18
    lesson_module = {"c1-l1": "m1", "c1-l2": "m1", "c1-l3": "m1", "c1-l4": "m2", "c1-l5": "m2"}
    assert {lesson_module[s["lessonId"]] for s in slots} == {"m1", "m2"}


def test_final_blueprint_prefers_higher_order():
    slots = exams.final_blueprint(_manifest())
    higher = sum(1 for s in slots if s["bloom"] in exams.HIGHER_BLOOMS)
    assert higher >= len(slots) // 2


def test_blueprint_dispatch():
    m = _manifest()
    assert exams.blueprint(m, "final") == exams.final_blueprint(m)
    assert exams.blueprint(m, "m1") == exams.module_blueprint(m, "m1")


def test_lesson_without_objectives_gets_fallback_slot():
    m = _manifest()
    m["modules"][0]["lessons"][1]["objectives"] = []
    slots = exams.module_blueprint(m, "m1")
    assert any(s["lessonId"] == "c1-l2" for s in slots)


def test_exam_prompt_mentions_slots_and_spine():
    m = _manifest()
    slots = exams.module_blueprint(m, "m1")
    spine_lessons = {"c1-l1": {"summary": "s", "concepts": [{"term": "gradient", "definition": "slope of loss"}]}}
    p = exams.exam_prompt(manifest=m, exam_key="m1", slots=slots, spine_lessons=spine_lessons)
    assert "o1a" in p and "c1-l1" in p and "gradient = slope of loss" in p
    assert "answerIndex" in p and "modelAnswer" in p


def test_exam_prompt_self_verification_and_novel_scenario_clauses():
    m = _manifest()
    slots = exams.module_blueprint(m, "m1")
    p = exams.exam_prompt(manifest=m, exam_key="m1", slots=slots, spine_lessons={})
    assert "re-answer each multiple-choice question independently" in p
    assert "Confirm the choice at answerIndex is the answer you get" in p
    assert "no distractor is also defensibly correct" in p
    assert "modelAnswer must be verifiably correct" in p
    assert "NOVEL scenario, case, or problem that does not appear in the lessons" in p
    assert "reward correct application to the scenario over recitation of definitions" in p


def test_valid_exam_accepts_aligned_and_rejects_misaligned():
    slots = exams.module_blueprint(_manifest(), "m1")
    good = _questions_for(slots)
    assert exams.valid_exam(good, slots)
    short = {"questions": good["questions"][:-1]}
    assert not exams.valid_exam(short, slots)
    swapped = json.loads(json.dumps(good))
    swapped["questions"][0]["type"] = "free" if slots[0]["type"] == "mcq" else "mcq"
    assert not exams.valid_exam(swapped, slots)
    wrong_lesson = json.loads(json.dumps(good))
    wrong_lesson["questions"][0]["lessonId"] = "c1-l99"
    assert not exams.valid_exam(wrong_lesson, slots)


def test_valid_exam_rejects_bad_mcq_and_free_shapes():
    slots = exams.module_blueprint(_manifest(), "m1")
    mcq_i = next(i for i, s in enumerate(slots) if s["type"] == "mcq")
    free_i = next(i for i, s in enumerate(slots) if s["type"] == "free")
    base = _questions_for(slots)
    for mutate in (
        lambda q: q[mcq_i].update(choices=["a", "b"]),
        lambda q: q[mcq_i].update(answerIndex=9),
        lambda q: q[free_i].update(modelAnswer=""),
        lambda q: q[free_i].update(graderNotes=None),
        lambda q: q[free_i].update(prompt=" "),
    ):
        bad = json.loads(json.dumps(base))
        mutate(bad["questions"])
        assert not exams.valid_exam(bad, slots)


def test_finalize_sanitizes_and_stamps_slot_metadata():
    slots = exams.module_blueprint(_manifest(), "m1")
    raw = _questions_for(slots)
    raw["questions"][0]["prompt"] = '<p onclick="x">Q<script>bad()</script></p>'
    exam = exams.finalize_exam(raw, slots, "m1", "c1")
    assert exam["examKey"] == "m1" and exam["courseId"] == "c1"
    q0 = exam["questions"][0]
    assert "<p onclick" not in q0["prompt"] and "<script>" not in q0["prompt"]
    assert q0["objectiveText"] == slots[0]["objectiveText"]
    assert q0["bloom"] == slots[0]["bloom"]


def test_client_view_strips_all_keys():
    slots = exams.module_blueprint(_manifest(), "m1")
    exam = exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")
    view = exams.client_view(exam)
    blob = json.dumps(view)
    assert "answerIndex" not in blob and "modelAnswer" not in blob and "graderNotes" not in blob
    assert len(view["questions"]) == 10 and view["examKey"] == "m1"


def test_pending_roundtrip_and_prune(tmp_path):
    slots = exams.module_blueprint(_manifest(), "m1")
    exam = exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")
    exams.save_pending(tmp_path, "c1", exam)
    assert exams.load_pending(tmp_path, "c1", "m1")["examKey"] == "m1"
    assert exams.load_pending(tmp_path, "c1", "final") is None
    (tmp_path / "c1" / "exams" / "m9.json").write_text("{}")
    (tmp_path / "c1" / "exams" / "final.json").write_text(json.dumps(exam))
    exams.prune_pending(tmp_path, "c1", {"m1", "final"})
    assert not (tmp_path / "c1" / "exams" / "m9.json").exists()
    assert (tmp_path / "c1" / "exams" / "m1.json").exists()
    assert (tmp_path / "c1" / "exams" / "final.json").exists()
    exams.delete_pending(tmp_path, "c1", "m1")
    assert exams.load_pending(tmp_path, "c1", "m1") is None
    exams.delete_pending(tmp_path, "c1", "m1")  # idempotent


def test_load_pending_corrupt_is_none(tmp_path):
    p = tmp_path / "c1" / "exams"
    p.mkdir(parents=True)
    (p / "m1.json").write_text("{not json")
    assert exams.load_pending(tmp_path, "c1", "m1") is None


def test_module_blueprint_grows_to_cover_oversized_module():
    def obj(text, bloom):
        return {"text": text, "bloom": bloom}
    manifest = {
        "id": "c1", "title": "Course", "brief": "A course.",
        "modules": [
            {
                "id": "m1", "title": "Oversized Module",
                "lessons": [
                    {"id": f"c1-l{i}", "title": f"L{i}", "objectives": [obj(f"o{i}a", "remember")]}
                    for i in range(1, 13)  # 12 lessons
                ]
            }
        ]
    }
    slots = exams.module_blueprint(manifest, "m1")
    assert len(slots) == 12
    lesson_ids = {s["lessonId"] for s in slots}
    assert lesson_ids == {f"c1-l{i}" for i in range(1, 13)}


def test_final_blueprint_grows_to_cover_oversized_course():
    def obj(text, bloom):
        return {"text": text, "bloom": bloom}
    manifest = {
        "id": "c1", "title": "Oversized Course", "brief": "A course.",
        "modules": [
            {
                "id": f"m{i}", "title": f"Module {i}",
                "lessons": [
                    {"id": f"c1-m{i}-l1", "title": "L1", "objectives": [obj(f"o{i}a", "remember")]}
                ]
            }
            for i in range(1, 21)  # 20 modules
        ]
    }
    slots = exams.final_blueprint(manifest)
    assert len(slots) == 20
    lesson_ids = {s["lessonId"] for s in slots}
    assert lesson_ids == {f"c1-m{i}-l1" for i in range(1, 21)}


def test_valid_exam_rejects_boolean_answer_index():
    slots = exams.module_blueprint(_manifest(), "m1")
    mcq_i = next(i for i, s in enumerate(slots) if s["type"] == "mcq")
    bad = _questions_for(slots)
    bad["questions"][mcq_i]["answerIndex"] = True
    assert not exams.valid_exam(bad, slots)


def _exam(slots=None):
    slots = slots or exams.module_blueprint(_manifest(), "m1")
    return exams.finalize_exam(_questions_for(slots), slots, "m1", "c1")


def _answers(exam, *, mcq=1, free="my answer"):
    return [mcq if q["type"] == "mcq" else free for q in exam["questions"]]


def _grader(verdict="correct", note="Good.", evidence="my answer"):
    def generate(prompt, validate):
        import re
        idxs = [int(m) for m in re.findall(r'"index": (\d+)', prompt)]
        result = {"grades": [{"index": i, "verdict": verdict, "note": note, "evidence": evidence}
                             for i in idxs]}
        assert validate(result)
        return result
    return generate


def test_validate_answers_shapes():
    exam = _exam()
    assert exams.validate_answers(exam, _answers(exam)) is None
    assert exams.validate_answers(exam, "nope") is not None
    assert exams.validate_answers(exam, _answers(exam)[:-1]) is not None
    bad_mcq = _answers(exam)
    bad_mcq[[i for i, q in enumerate(exam["questions"]) if q["type"] == "mcq"][0]] = 99
    assert exams.validate_answers(exam, bad_mcq) is not None
    long_free = _answers(exam, free="x" * (exams.MAX_FREE_ANSWER_CHARS + 1))
    assert exams.validate_answers(exam, long_free) is not None
    empty_free_ok = _answers(exam, free="")
    assert exams.validate_answers(exam, empty_free_ok) is None


def test_exam_grade_prompt_lists_only_free_questions():
    exam = _exam()
    p = exams.exam_grade_prompt(exam, _answers(exam))
    free_count = sum(1 for q in exam["questions"] if q["type"] == "free")
    assert p.count('"learnerAnswer"') == free_count
    assert "my answer" in p and "graderNotes" not in p  # notes embedded under a different key


def test_exam_grade_prompt_demands_evidence():
    exam = _exam()
    p = exams.exam_grade_prompt(exam, _answers(exam))
    assert "include evidence" in p
    assert "short verbatim" in p and "quote from the learner's answer" in p
    assert "empty string only if the answer is empty" in p
    assert '"evidence"' in p


def test_valid_exam_grades_requires_exact_indices():
    check = exams.valid_exam_grades([1, 3])
    ok = {"grades": [{"index": 1, "verdict": "close", "note": "n", "evidence": "q"},
                     {"index": 3, "verdict": "correct", "note": "n", "evidence": ""}]}
    assert check(ok)
    assert not check({"grades": ok["grades"][:1]})
    assert not check({"grades": ok["grades"] + [{"index": 9, "verdict": "correct", "note": "n", "evidence": "q"}]})
    assert not check({"grades": [{"index": 1, "verdict": "meh", "note": "n", "evidence": "q"},
                                 {"index": 3, "verdict": "correct", "note": "n", "evidence": "q"}]})
    assert not check({"grades": [{"index": 1, "verdict": "close", "note": " ", "evidence": "q"},
                                 {"index": 3, "verdict": "correct", "note": "n", "evidence": "q"}]})


def test_valid_exam_grades_rejects_missing_or_non_string_evidence():
    check = exams.valid_exam_grades([1, 3])
    missing = {"grades": [{"index": 1, "verdict": "close", "note": "n"},
                          {"index": 3, "verdict": "correct", "note": "n", "evidence": "q"}]}
    assert not check(missing)
    non_string = {"grades": [{"index": 1, "verdict": "close", "note": "n", "evidence": 5},
                             {"index": 3, "verdict": "correct", "note": "n", "evidence": "q"}]}
    assert not check(non_string)


def test_valid_exam_grades_accepts_empty_evidence_string():
    check = exams.valid_exam_grades([1])
    ok = {"grades": [{"index": 1, "verdict": "incorrect", "note": "n", "evidence": ""}]}
    assert check(ok)


def test_valid_exam_grades_rejects_duplicate_index():
    check = exams.valid_exam_grades([1, 3])
    dup = {"grades": [
        {"index": 1, "verdict": "close", "note": "n", "evidence": "q"},
        {"index": 1, "verdict": "correct", "note": "n2", "evidence": "q2"},
    ]}
    assert not check(dup)


def test_valid_exam_grades_rejects_wrong_count():
    check = exams.valid_exam_grades([1, 3])
    too_many = {"grades": [
        {"index": 1, "verdict": "close", "note": "n", "evidence": "q"},
        {"index": 3, "verdict": "correct", "note": "n", "evidence": "q"},
        {"index": 5, "verdict": "correct", "note": "n", "evidence": "q"},
    ]}
    assert not check(too_many)


def test_grade_exam_all_correct_passes():
    exam = _exam()
    result = exams.grade_exam(exam, _answers(exam), _manifest(), generate=_grader())
    assert result["score"] == 1.0 and result["passed"] is True
    assert len(result["perQuestion"]) == 10 and result["weakSpots"] == []


def test_grade_exam_exactly_eighty_percent_passes():
    exam = _exam()
    mcq_idx = [i for i, q in enumerate(exam["questions"]) if q["type"] == "mcq"]
    free_count = 10 - len(mcq_idx)
    # Make wrong MCQs + close frees add up to exactly 2.0 lost points when possible;
    # fall back to asserting the boundary rule directly.
    assert exams.PASS_SCORE == 0.8
    answers = _answers(exam)
    wrong = 0
    for i in mcq_idx:
        if wrong == 2:
            break
        answers[i] = (exam["questions"][i]["answerIndex"] + 1) % len(exam["questions"][i]["choices"])
        wrong += 1
    if wrong == 2:
        result = exams.grade_exam(exam, answers, _manifest(), generate=_grader())
        assert result["score"] == 0.8 and result["passed"] is True


def test_grade_exam_failure_builds_weak_spots():
    exam = _exam()
    answers = _answers(exam)
    for i, q in enumerate(exam["questions"]):
        if q["type"] == "mcq":
            answers[i] = (q["answerIndex"] + 1) % len(q["choices"])
    result = exams.grade_exam(exam, answers, _manifest(), generate=_grader(verdict="incorrect", note="No."))
    assert result["score"] == 0.0 and result["passed"] is False
    assert {w["lessonId"] for w in result["weakSpots"]} == {"c1-l1", "c1-l2", "c1-l3"}
    spot = next(w for w in result["weakSpots"] if w["lessonId"] == "c1-l1")
    assert spot["lessonTitle"] == "L1" and spot["objectives"]


def test_grade_exam_sanitizes_grader_notes_and_reveals_mcq_key():
    exam = _exam()
    result = exams.grade_exam(exam, _answers(exam), _manifest(),
                              generate=_grader(note='<em>ok</em><script>x()</script>'))
    free_q = next(q for q in result["perQuestion"] if q["type"] == "free")
    assert "<script>" not in free_q["note"] and "<em>ok</em>" in free_q["note"]
    mcq_q = next(q for q in result["perQuestion"] if q["type"] == "mcq")
    assert isinstance(mcq_q["correctIndex"], int) and "answerIndex" not in mcq_q


def test_grade_exam_does_not_leak_evidence_into_result_payload():
    exam = _exam()
    result = exams.grade_exam(exam, _answers(exam), _manifest(), generate=_grader(evidence="a telling quote"))
    blob = json.dumps(result)
    assert "evidence" not in blob and "a telling quote" not in blob


def test_record_result_and_status(conn):
    manifest = _manifest()
    r1 = {"score": 0.6, "passed": False, "perQuestion": [], "weakSpots": []}
    r2 = {"score": 0.9, "passed": True, "perQuestion": [], "weakSpots": []}
    assert exams.record_result(conn, "c1", "m1", r1) == 1
    assert exams.record_result(conn, "c1", "m1", r2) == 2
    assert exams.record_result(conn, "c1", "final", r2) == 1
    status = exams.exam_status(conn, "c1", manifest)
    assert status["m1"] == {"attempts": 2, "bestScore": 0.9, "passed": True}
    assert status["final"]["passed"] is True and "m2" not in status
    assert exams.course_passed(status, manifest) is False  # m2 never taken
    exams.record_result(conn, "c1", "m2", r2)
    status = exams.exam_status(conn, "c1", manifest)
    assert exams.course_passed(status, manifest) is True


def test_status_ignores_dropped_module_keys(conn):
    manifest = _manifest()
    exams.record_result(conn, "c1", "m99", {"score": 1.0, "passed": True, "perQuestion": [], "weakSpots": []})
    status = exams.exam_status(conn, "c1", manifest)
    assert "m99" not in status


def test_status_tolerates_non_dict_payload_and_non_numeric_score(conn):
    manifest = _manifest()
    events.insert_events(conn, [
        {  # forged non-dict payload — event skipped entirely
            "client_event_id": "bad1", "session_id": "s1", "event_type": "exam_result",
            "occurred_at": "2026-07-15T09:00:00+00:00", "course_id": "c1", "topic_id": "m1",
            "payload": ["not", "a", "dict"],
        },
        {  # dict payload but non-numeric score — attempt counts, score ignored
            "client_event_id": "bad2", "session_id": "s1", "event_type": "exam_result",
            "occurred_at": "2026-07-15T09:05:00+00:00", "course_id": "c1", "topic_id": "m1",
            "payload": {"score": "high", "passed": True},
        },
    ])
    status = exams.exam_status(conn, "c1", manifest)  # must not raise
    assert status["m1"]["attempts"] == 1  # only the dict-payload row counted
    assert status["m1"]["bestScore"] == 0.0  # non-numeric score ignored
    assert status["m1"]["passed"] is True


def test_submit_exam_full_cycle(tmp_path, conn):
    manifest = _manifest()
    exam = _exam()
    exams.save_pending(tmp_path, "c1", exam)
    result = exams.submit_exam(tmp_path, conn, "c1", "m1", _answers(exam),
                               manifest=manifest, generate=_grader())
    assert result["passed"] is True and result["attempt"] == 1
    assert exams.load_pending(tmp_path, "c1", "m1") is None  # consumed
    rows = conn.execute("SELECT event_type, topic_id, course_id FROM events").fetchall()
    assert ("exam_result", "m1", "c1") in [(r["event_type"], r["topic_id"], r["course_id"]) for r in rows]


def test_submit_exam_no_pending_is_none(tmp_path, conn):
    assert exams.submit_exam(tmp_path, conn, "c1", "m1", [], manifest=_manifest(), generate=_grader()) is None


def test_submit_exam_grading_failure_keeps_pending(tmp_path, conn):
    from backend import claude_client
    exam = _exam()
    exams.save_pending(tmp_path, "c1", exam)

    def boom(prompt, validate):
        raise claude_client.ClaudeError("nope")

    try:
        exams.submit_exam(tmp_path, conn, "c1", "m1", _answers(exam), manifest=_manifest(), generate=boom)
        assert False, "expected ClaudeError"
    except claude_client.ClaudeError:
        pass
    assert exams.load_pending(tmp_path, "c1", "m1") is not None  # NOT consumed
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0


def test_final_unlocked_requires_every_module_passed():
    manifest = _manifest()
    locked = {"m1": {"passed": True}}
    assert not exams.final_unlocked(locked, manifest)
    assert not exams.final_unlocked({}, manifest)
    both = {"m1": {"passed": True}, "m2": {"passed": True}}
    assert exams.final_unlocked(both, manifest)
    assert not exams.final_unlocked(both, {"modules": []})
