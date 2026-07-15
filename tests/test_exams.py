import json

from backend import exams


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
    assert "<script>" not in q0["prompt"] and "onclick" not in q0["prompt"]
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
