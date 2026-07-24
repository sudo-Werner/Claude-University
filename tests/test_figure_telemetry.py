from backend import figure_telemetry


def test_record_appends_jsonl_with_timestamp(tmp_path):
    ev = {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
          "requested_type": "web-image", "outcome": "rendered",
          "drop_reason": None, "query": "q"}
    figure_telemetry.record(tmp_path, ev)
    figure_telemetry.record(tmp_path, {**ev, "n": 2, "outcome": "dropped",
                                       "drop_reason": "vision-rejected"})
    rows = figure_telemetry.read(tmp_path)
    assert len(rows) == 2
    assert rows[0]["n"] == 1 and "ts" in rows[0]
    assert rows[1]["drop_reason"] == "vision-rejected"


def test_read_missing_file_is_empty(tmp_path):
    assert figure_telemetry.read(tmp_path) == []


def test_record_never_raises_on_bad_dir():
    figure_telemetry.record("/nonexistent/deeply/nested", {"n": 1})  # no exception


def test_read_skips_malformed_lines(tmp_path):
    path = tmp_path / figure_telemetry.TELEMETRY_FILENAME
    path.write_text(
        '{"n": 1}\n'
        "not json\n"
        '{"n": 2}\n',
        encoding="utf-8",
    )
    rows = figure_telemetry.read(tmp_path)
    assert len(rows) == 2
    assert rows[0]["n"] == 1 and rows[1]["n"] == 2
