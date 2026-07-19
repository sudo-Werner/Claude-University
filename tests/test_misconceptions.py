import json

from backend import misconceptions


def test_load_profile_empty_when_missing(tmp_path):
    assert misconceptions.load_profile(tmp_path, "c1") == []


def test_add_and_load_roundtrip(tmp_path):
    misconceptions.add_entries(
        tmp_path, "c1", "c1-l1", "Lesson One", "explain",
        [("thinks gradient descent always finds the global minimum", "it always finds the best answer")],
    )
    profile = misconceptions.load_profile(tmp_path, "c1")
    assert len(profile) == 1
    entry = profile[0]
    assert entry["text"] == "thinks gradient descent always finds the global minimum"
    assert entry["excerpt"] == "it always finds the best answer"
    assert entry["lessonId"] == "c1-l1"
    assert entry["lessonTitle"] == "Lesson One"
    assert entry["source"] == "explain"
    assert entry["id"].startswith("mc-")
    assert entry["occurredAt"]


def test_load_profile_newest_first(tmp_path):
    misconceptions.add_entries(tmp_path, "c1", "c1-l1", "L1", "explain", [("first one", "ex1")])
    misconceptions.add_entries(tmp_path, "c1", "c1-l2", "L2", "teach", [("second one", "ex2")])
    profile = misconceptions.load_profile(tmp_path, "c1")
    assert [e["text"] for e in profile] == ["second one", "first one"]


def test_add_entries_dedupes_normalized_text(tmp_path):
    misconceptions.add_entries(tmp_path, "c1", "c1-l1", "L1", "explain",
                               [("Thinks X Is Always True", "ex1")])
    misconceptions.add_entries(tmp_path, "c1", "c1-l2", "L2", "teach",
                               [("thinks x is always true", "ex2")])  # same, different case/lesson
    profile = misconceptions.load_profile(tmp_path, "c1")
    assert len(profile) == 1  # second one skipped as a duplicate
    assert profile[0]["text"] == "Thinks X Is Always True"  # first one kept, not overwritten


def test_add_entries_multiple_texts_in_one_call(tmp_path):
    misconceptions.add_entries(tmp_path, "c1", "c1-l1", "L1", "explain",
                               [("misconception A", "exA"), ("misconception B", "exB")])
    profile = misconceptions.load_profile(tmp_path, "c1")
    assert len(profile) == 2


def test_delete_entry_removes_by_id(tmp_path):
    misconceptions.add_entries(tmp_path, "c1", "c1-l1", "L1", "explain", [("to delete", "ex")])
    entry_id = misconceptions.load_profile(tmp_path, "c1")[0]["id"]
    assert misconceptions.delete_entry(tmp_path, "c1", entry_id) is True
    assert misconceptions.load_profile(tmp_path, "c1") == []


def test_delete_entry_returns_false_for_unknown_id(tmp_path):
    assert misconceptions.delete_entry(tmp_path, "c1", "mc-doesnotexist") is False


def test_load_profile_tolerates_corrupt_file(tmp_path):
    course_dir = tmp_path / "c1"
    course_dir.mkdir()
    (course_dir / "misconceptions.json").write_text("{not valid json")
    assert misconceptions.load_profile(tmp_path, "c1") == []


def test_load_profile_tolerates_malformed_shape(tmp_path):
    course_dir = tmp_path / "c1"
    course_dir.mkdir()
    (course_dir / "misconceptions.json").write_text(json.dumps({"entries": "not-a-list"}))
    assert misconceptions.load_profile(tmp_path, "c1") == []


def test_add_entries_skips_blank_text(tmp_path):
    misconceptions.add_entries(tmp_path, "c1", "c1-l1", "L1", "explain", [("  ", "ex"), ("", "ex2")])
    assert misconceptions.load_profile(tmp_path, "c1") == []
