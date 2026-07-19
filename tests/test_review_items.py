import json

from backend import generation, review_items


def _lesson_meta(objectives=None, title="Loops", module_title="Control Flow"):
    meta = {"id": "c1-l1", "title": title, "moduleTitle": module_title}
    if objectives is not None:
        meta["objectives"] = objectives
    return meta


OBJECTIVES = [{"text": "Write a for loop", "bloom": "apply", "knowledge": "procedural"}]
SPINE_ENTRY = {"summary": "Loops repeat a block of code.",
               "concepts": [{"term": "for loop", "definition": "repeats a block a fixed number of times"}]}


def _good_items():
    return {"items": [
        {"type": "mcq", "prompt": "Which keyword starts a for loop?", "choices": ["for", "if", "def"],
         "answer": 0, "explanation": "for introduces the loop"},
        {"type": "fill", "prompt": "How many times does `for i in range(3)` run?", "answer": "3",
         "explanation": "range(3) yields 0,1,2"},
    ]}


def test_prompt_includes_title_module_and_objectives():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert '"Loops"' in p and '"Control Flow"' in p
    assert "Write a for loop" in p and "Bloom: apply" in p


def test_prompt_includes_spine_terms_and_omits_when_absent():
    with_spine = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), SPINE_ENTRY, [])
    assert "for loop: repeats a block a fixed number of times" in with_spine
    assert "Loops repeat a block of code." in with_spine

    without_spine = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "repeats a block a fixed number of times" not in without_spine

    empty_spine = review_items.review_items_prompt(
        _lesson_meta(OBJECTIVES), {"summary": "", "concepts": []}, [])
    assert "What the lesson" not in empty_spine


def test_prompt_falls_back_to_title_derived_objective_when_absent():
    p = review_items.review_items_prompt(_lesson_meta(objectives=[], title="Recursion"), None, [])
    assert 'Explain the key ideas of "Recursion"' in p
    p2 = review_items.review_items_prompt(_lesson_meta(objectives=None, title="Recursion"), None, [])
    assert 'Explain the key ideas of "Recursion"' in p2


def test_prompt_includes_no_repeat_instruction_with_existing_prompts():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, ["What keyword starts a loop?"])
    assert "do NOT repeat or lightly reword these existing questions" in p
    assert "What keyword starts a loop?" in p

    without = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "do NOT repeat or lightly reword these existing questions" not in without


def test_prompt_demands_exactly_two_items_and_json_only():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "EXACTLY 2" in p
    assert "Reply with ONLY a JSON object, no prose, no fence" in p
    assert '{"items":' in p


def test_prompt_has_mcq_self_verification_paragraph_verbatim():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert ("Before emitting, re-answer each mcq question independently from the question "
            "text alone. Confirm the choice at answer is the answer you get, and that no "
            "distractor is also defensibly correct — if one is, rewrite it.") in p


def test_valid_review_items_accepts_one_or_two_good_items():
    assert review_items.valid_review_items(_good_items())
    one = {"items": [_good_items()["items"][0]]}
    assert review_items.valid_review_items(one)


def test_valid_review_items_rejects_zero_three_nonlist_and_bad_shapes():
    assert not review_items.valid_review_items({"items": []})
    three = _good_items()
    three["items"].append(dict(three["items"][1]))
    assert not review_items.valid_review_items(three)
    assert not review_items.valid_review_items({"items": "nope"})
    assert not review_items.valid_review_items({})
    assert not review_items.valid_review_items(None)
    bad_check = {"items": [{"type": "mcq", "prompt": "q", "choices": ["a"], "answer": 5, "explanation": "e"}]}
    assert not review_items.valid_review_items(bad_check)


def test_finalize_items_sanitizes_keeps_fill_verbatim_and_drops_unknown_keys():
    raw = _good_items()
    raw["items"][0]["prompt"] = "<p>Q <script>x()</script></p>"
    raw["items"][0]["choices"] = ["<b>for</b>", "if", "def"]
    raw["items"][1]["answer"] = "  3  "  # verbatim: whitespace preserved exactly
    raw["items"][0]["bogus"] = "should not survive"
    out = review_items.finalize_items(raw, "c1-l1", 2)
    assert out["lessonId"] == "c1-l1" and out["reviewCount"] == 2
    assert len(out["items"]) == 2
    assert "<script>" not in out["items"][0]["prompt"]
    assert "<b>" not in out["items"][0]["choices"][0]
    assert "bogus" not in out["items"][0]
    assert set(out["items"][0].keys()) == {"type", "prompt", "answer", "explanation", "choices"}
    assert set(out["items"][1].keys()) == {"type", "prompt", "answer", "explanation"}
    assert out["items"][0]["answer"] == 0        # mcq answer int kept
    assert out["items"][1]["answer"] == "  3  "  # fill answer verbatim


def test_persistence_roundtrip_corrupt_and_prune(tmp_path):
    items = review_items.finalize_items(_good_items(), "c1-l1", 1)
    review_items.save_items(tmp_path, "c1", items)
    assert review_items.load_items(tmp_path, "c1", "c1-l1")["reviewCount"] == 1
    (tmp_path / "c1" / "review-items" / "c1-l1.json").write_text("{nope")
    assert review_items.load_items(tmp_path, "c1", "c1-l1") is None
    review_items.save_items(tmp_path, "c1", items)
    review_items.save_items(tmp_path, "c1", {**items, "lessonId": "c1-l2"})
    review_items.prune(tmp_path, "c1", {"c1-l2"})
    assert review_items.load_items(tmp_path, "c1", "c1-l1") is None
    assert review_items.load_items(tmp_path, "c1", "c1-l2") is not None


def test_ensure_review_items_reuses_fresh_and_regenerates_on_stamp_change(tmp_path):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = _good_items()
        assert validate(obj)
        return obj

    meta = _lesson_meta(OBJECTIVES)
    s1 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s1["reviewCount"] == 1 and len(calls) == 1
    s2 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s2["reviewCount"] == 1 and len(calls) == 1   # served from disk
    s3 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 2, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s3["reviewCount"] == 2 and len(calls) == 2   # stamp changed -> regenerated


def test_ensure_review_items_corrupt_cache_regenerates(tmp_path):
    path = tmp_path / "c1" / "review-items" / "c1-l1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{corrupt")
    meta = _lesson_meta(OBJECTIVES)
    result = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=lambda p, v: _good_items())
    assert result["reviewCount"] == 1 and len(result["items"]) == 2


# ---- highlight -> review item ----

def _good_highlight_item():
    return {"item": {"type": "fill", "prompt": "What does a for loop do?",
                      "answer": "repeats a block of code", "explanation": "that's its job"}}


def test_highlight_item_prompt_includes_highlighted_text_and_lesson_context():
    p = review_items.highlight_item_prompt("for loops repeat code", _lesson_meta(OBJECTIVES), None)
    assert "for loops repeat code" in p
    assert '"Loops"' in p and '"Control Flow"' in p
    assert 'Reply with ONLY JSON, no prose, no fence: {"item":' in p


def test_highlight_item_prompt_includes_spine_when_present():
    p = review_items.highlight_item_prompt("for loops repeat code", _lesson_meta(OBJECTIVES), SPINE_ENTRY)
    assert "Loops repeat a block of code." in p


def test_valid_highlight_item_accepts_wrapped_check_rejects_bad_shapes():
    assert review_items.valid_highlight_item(_good_highlight_item())
    assert not review_items.valid_highlight_item({"item": {"type": "mcq"}})
    assert not review_items.valid_highlight_item({})
    assert not review_items.valid_highlight_item({"items": [_good_highlight_item()["item"]]})
    assert not review_items.valid_highlight_item(None)


def test_make_highlight_item_generates_finalizes_ids_and_persists(tmp_path):
    meta = _lesson_meta(OBJECTIVES)
    item = review_items.make_highlight_item(
        tmp_path, "c1", "c1-l1", "for loops repeat code",
        lesson_meta=meta, spine_entry=None, generate=lambda p, v: _good_highlight_item())
    assert item["prompt"] == "What does a for loop do?"
    assert item["source"] == "highlight"
    assert item["id"].startswith("hi-")
    stored = review_items.load_items(tmp_path, "c1", "c1-l1")
    assert stored["userItems"] == [item]
    assert stored["items"] == []          # no AI-generated fresh items exist yet
    assert stored["reviewCount"] == -1    # sentinel: never matches a real review count


def test_make_highlight_item_preserves_existing_ai_items_and_review_count(tmp_path):
    meta = _lesson_meta(OBJECTIVES)
    review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 3, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=lambda p, v: _good_items())
    item = review_items.make_highlight_item(
        tmp_path, "c1", "c1-l1", "for loops repeat code",
        lesson_meta=meta, spine_entry=None, generate=lambda p, v: _good_highlight_item())
    stored = review_items.load_items(tmp_path, "c1", "c1-l1")
    assert stored["reviewCount"] == 3
    assert len(stored["items"]) == 2      # untouched
    assert stored["userItems"] == [item]


def test_make_highlight_item_appends_to_existing_user_items(tmp_path):
    meta = _lesson_meta(OBJECTIVES)
    first = review_items.make_highlight_item(
        tmp_path, "c1", "c1-l1", "first passage",
        lesson_meta=meta, spine_entry=None, generate=lambda p, v: _good_highlight_item())
    second = review_items.make_highlight_item(
        tmp_path, "c1", "c1-l1", "second passage",
        lesson_meta=meta, spine_entry=None, generate=lambda p, v: _good_highlight_item())
    stored = review_items.load_items(tmp_path, "c1", "c1-l1")
    assert stored["userItems"] == [first, second]
    assert first["id"] != second["id"]


def test_ensure_review_items_preserves_user_items_across_regeneration(tmp_path):
    meta = _lesson_meta(OBJECTIVES)
    user_item = review_items.make_highlight_item(
        tmp_path, "c1", "c1-l1", "for loops repeat code",
        lesson_meta=meta, spine_entry=None, generate=lambda p, v: _good_highlight_item())
    regenerated = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=lambda p, v: _good_items())
    assert regenerated["reviewCount"] == 1
    assert len(regenerated["items"]) == 2
    assert regenerated["userItems"] == [user_item]


def test_load_items_defaults_user_items_for_back_compat_files(tmp_path):
    path = tmp_path / "c1" / "review-items" / "c1-l1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"lessonId": "c1-l1", "reviewCount": 1, "items": []}))
    loaded = review_items.load_items(tmp_path, "c1", "c1-l1")
    assert loaded["userItems"] == []
