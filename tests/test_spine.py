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
