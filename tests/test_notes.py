import json

import pytest
from backend import notes


def test_load_workspace_default_when_missing(tmp_path):
    assert notes.load_workspace(tmp_path, "c", "l1") == {
        "notes": "", "chat": [], "highlights": [], "updatedAt": None}


def test_save_and_load_roundtrip(tmp_path):
    rec = notes.save_workspace(tmp_path, "c", "l1", "my notes",
                               [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    assert rec["notes"] == "my notes"
    assert rec["updatedAt"]
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["notes"] == "my notes"
    assert ws["chat"][1] == {"role": "assistant", "content": "yo"}


def test_save_workspace_rejects_bad_shape(tmp_path):
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", "n", [{"role": "bad", "content": "x"}])
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", 123, [])


def test_save_workspace_enforces_size_cap(tmp_path):
    with pytest.raises(notes.WorkspaceTooLarge):
        notes.save_workspace(tmp_path, "c", "l1", "x" * 200000, [])


def test_load_workspace_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "c" / "notes" / "l1.json"
    p.parent.mkdir(parents=True)
    p.write_text("not json{")
    assert notes.load_workspace(tmp_path, "c", "l1")["notes"] == ""


def test_save_and_load_roundtrip_with_highlights(tmp_path):
    hl = [{"id": "h1", "text": "some phrase", "occurrence": 0}]
    rec = notes.save_workspace(tmp_path, "c", "l1", "n", [], hl)
    assert rec["highlights"] == hl
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["highlights"] == hl


def test_load_workspace_defaults_highlights_when_absent_from_file(tmp_path):
    # Simulates a workspace file written before this feature existed (no "highlights" key).
    p = tmp_path / "c" / "notes" / "l1.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"notes": "n", "chat": [], "updatedAt": "t"}))
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["highlights"] == []


def test_save_workspace_defaults_highlights_when_omitted(tmp_path):
    # An old call site (or old client PUT body) that never passes highlights at all.
    rec = notes.save_workspace(tmp_path, "c", "l1", "n", [])
    assert rec["highlights"] == []


@pytest.mark.parametrize("bad_highlights", [
    "not-a-list",
    [{"id": "h1", "text": "x"}],                          # missing occurrence
    [{"id": "h1", "occurrence": 0}],                       # missing text
    [{"text": "x", "occurrence": 0}],                      # missing id
    [{"id": "", "text": "x", "occurrence": 0}],            # empty id
    [{"id": "h1", "text": "", "occurrence": 0}],           # empty text
    [{"id": "h1", "text": "x" * 2001, "occurrence": 0}],   # text over 2000 chars
    [{"id": "h" * 65, "text": "x", "occurrence": 0}],      # id over 64 chars
    [{"id": "h1", "text": "x", "occurrence": -1}],         # negative occurrence
    [{"id": "h1", "text": "x", "occurrence": 1.5}],        # non-int occurrence
    [{"id": "h1", "text": "x", "occurrence": True}],       # bool occurrence explicitly rejected
    [{"id": 1, "text": "x", "occurrence": 0}],             # non-string id
    [{"id": "h1", "text": 1, "occurrence": 0}],            # non-string text
    ["not-a-dict"],                                        # list of non-dicts
])
def test_save_workspace_rejects_bad_highlights(tmp_path, bad_highlights):
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", "n", [], bad_highlights)


def test_save_workspace_enforces_size_cap_via_highlights(tmp_path):
    big_highlights = [{"id": f"h{i}", "text": "x" * 500, "occurrence": 0} for i in range(300)]
    with pytest.raises(notes.WorkspaceTooLarge):
        notes.save_workspace(tmp_path, "c", "l1", "", [], big_highlights)
