import json

from backend import spine


def _entry(summary="Teaches recursion.", term="recursion",
           definition="A function calling itself on a smaller input."):
    return {"summary": summary, "concepts": [{"term": term, "definition": definition}]}


def test_load_spine_missing_file_returns_empty(tmp_path):
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_load_spine_corrupt_json_returns_empty(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "spine.json").write_text("{nope")
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_load_spine_wrong_shape_returns_empty(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "spine.json").write_text(json.dumps({"lessons": [1, 2]}))
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_upsert_entry_roundtrips_and_overwrites(tmp_path):
    (tmp_path / "c").mkdir()
    first = _entry()
    spine.upsert_entry(tmp_path, "c", "c-l1", first)
    assert spine.load_spine(tmp_path, "c")["lessons"]["c-l1"] == first
    second = _entry(summary="Teaches base cases.", term="base case",
                    definition="The input a recursive function answers directly.")
    spine.upsert_entry(tmp_path, "c", "c-l1", second)
    data = spine.load_spine(tmp_path, "c")
    assert data["lessons"] == {"c-l1": second}


def test_prune_keeps_only_named_ids(tmp_path):
    (tmp_path / "c").mkdir()
    spine.upsert_entry(tmp_path, "c", "c-l1", _entry())
    spine.upsert_entry(tmp_path, "c", "c-l2", _entry(term="stack", definition="Call bookkeeping."))
    spine.prune(tmp_path, "c", {"c-l1"})
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1"}


def test_prune_without_spine_file_is_a_noop(tmp_path):
    spine.prune(tmp_path, "c", {"c-l1"})  # must not raise or create anything
    assert not (tmp_path / "c" / "spine.json").exists()


def test_valid_spine_entry_accepts_good_entry():
    assert spine.valid_spine_entry(_entry())
    four = {"summary": "s", "concepts": [
        {"term": f"t{i}", "definition": f"d{i}"} for i in range(4)]}
    assert spine.valid_spine_entry(four)


def test_valid_spine_entry_rejects_malformed():
    assert not spine.valid_spine_entry(None)
    assert not spine.valid_spine_entry("recursion")
    assert not spine.valid_spine_entry({"summary": "s", "concepts": []})
    assert not spine.valid_spine_entry({"summary": "", "concepts": [{"term": "t", "definition": "d"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": [{"term": " ", "definition": "d"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": [{"term": "t"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": ["t"]})
    five = {"summary": "s", "concepts": [
        {"term": f"t{i}", "definition": f"d{i}"} for i in range(5)]}
    assert not spine.valid_spine_entry(five)


def _cached_lesson(topic="Recursion"):
    return {"id": "x", "topic": topic, "promptHtml": "<p>body</p>",
            "solutionNote": "worked example"}


def _write_lessons(tmp_path, course_id, lesson_ids):
    ldir = tmp_path / course_id / "lessons"
    ldir.mkdir(parents=True)
    for lid in lesson_ids:
        (ldir / f"{lid}.json").write_text(json.dumps(_cached_lesson()))
    return ldir


def test_backfill_prompt_lists_each_lesson_id():
    batch = [("c-l1", _cached_lesson()), ("c-l2", _cached_lesson("Base cases"))]
    prompt = spine.backfill_prompt(batch)
    assert "c-l1" in prompt and "c-l2" in prompt
    assert "ONLY a JSON object" in prompt
    assert "No HTML" in prompt


def test_valid_backfill_requires_exact_ids_and_valid_entries():
    good = {"c-l1": _entry(), "c-l2": _entry(term="base case", definition="d")}
    check = spine.valid_backfill(["c-l1", "c-l2"])
    assert check(good)
    assert not check({"c-l1": _entry()})                       # missing id
    assert not check({**good, "c-l3": _entry()})               # extra id
    assert not check({"c-l1": _entry(), "c-l2": {"summary": "s", "concepts": []}})
    assert not check([])


def test_backfill_course_batches_merges_and_reports_count(tmp_path):
    _write_lessons(tmp_path, "c", ["c-l1", "c-l2", "c-l3"])
    calls = []

    def fake_generate(prompt, validate):
        ids = [lid for lid in ("c-l1", "c-l2", "c-l3") if f"id={lid}" in prompt]
        calls.append(ids)
        result = {lid: _entry(summary=f"about {lid}") for lid in ids}
        assert validate(result)
        return result

    added = spine.backfill_course(tmp_path, "c", generate=fake_generate, batch_size=2)
    assert added == 3
    assert len(calls) == 2 and calls[0] == ["c-l1", "c-l2"] and calls[1] == ["c-l3"]
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1", "c-l2", "c-l3"}


def test_backfill_course_skips_ids_already_in_spine(tmp_path):
    _write_lessons(tmp_path, "c", ["c-l1", "c-l2"])
    spine.upsert_entry(tmp_path, "c", "c-l1", _entry())

    def fake_generate(prompt, validate):
        assert "id=c-l1" not in prompt
        return {"c-l2": _entry(term="t2", definition="d2")}

    added = spine.backfill_course(tmp_path, "c", generate=fake_generate)
    assert added == 1
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1", "c-l2"}


def test_backfill_course_missing_lessons_dir_returns_zero(tmp_path):
    assert spine.backfill_course(tmp_path, "c", generate=None) == 0


def test_backfill_course_skips_corrupt_lesson_files(tmp_path):
    ldir = _write_lessons(tmp_path, "c", ["c-l1"])
    (ldir / "c-l2.json").write_text("{nope")
    added = spine.backfill_course(
        tmp_path, "c",
        generate=lambda p, validate: {"c-l1": _entry()})
    assert added == 1
