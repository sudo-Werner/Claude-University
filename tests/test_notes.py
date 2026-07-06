import pytest
from backend import notes


def test_load_workspace_default_when_missing(tmp_path):
    assert notes.load_workspace(tmp_path, "c", "l1") == {"notes": "", "chat": [], "updatedAt": None}


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
