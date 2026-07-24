import json
from backend import figure_metrics, figure_telemetry


def _seed(content_dir, course_id, lessons, events):
    cdir = content_dir / course_id
    (cdir / "lessons").mkdir(parents=True)
    manifest = {"schemaVersion": 3, "objectives": [], "modules": [{"title": "M",
                "lessons": []}]}
    for lid, objs in lessons.items():
        for i, o in enumerate(objs):
            o["id"] = f"{lid}-o{i}"
        manifest["objectives"].extend(objs)
        manifest["modules"][0]["lessons"].append(
            {"id": lid, "title": lid, "objectiveIds": [o["id"] for o in objs]})
    (cdir / "course.json").write_text(json.dumps(manifest))
    for ev in events:
        figure_telemetry.record(content_dir, ev)


def test_id_alignment_and_realization(tmp_path):
    content_dir = tmp_path / "courses"
    _seed(content_dir, "demo",
          lessons={"demo-l1": [{"text": "identify the bone", "bloom": "remember",
                                "knowledge": "factual"}],
                   "demo-l2": [{"text": "explain flow", "bloom": "analyze",
                                "knowledge": "conceptual"}]},
          events=[
            {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
             "requested_type": "web-image", "outcome": "rendered", "drop_reason": None},
            {"course_id": "demo", "lesson_id": "demo-l2", "n": 1,
             "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
          ])
    m = figure_metrics.compute(content_dir, "demo")
    assert m["id_alignment_rate"] == 1.0            # the one ID lesson asked for a photo
    assert m["web_image_realization_rate"] == 1.0   # its photo resolved
    assert m["mermaid_share"] == 0.5                 # 1 of 2 drawn/photo slots is mermaid


def test_orphaned_telemetry_lesson_does_not_break_metrics(tmp_path):
    """The telemetry JSONL is append-only and accumulates rows for ALL time,
    including lessons later renamed/removed from the manifest. compute() must
    bound its aggregation to the current manifest's lessons so a renamed/
    removed lesson's stale rows can't push fig_lessons past total_lessons
    (which would make zero_figure_rate go negative) or drift figures_per_lesson."""
    lessons = {"demo-l1": [{"text": "a", "bloom": "analyze", "knowledge": "conceptual"}],
               "demo-l2": [{"text": "b", "bloom": "analyze", "knowledge": "conceptual"}]}
    manifest_events = [
        {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
         "requested_type": "web-image", "outcome": "rendered", "drop_reason": None},
        {"course_id": "demo", "lesson_id": "demo-l2", "n": 1,
         "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
    ]
    # Stale telemetry for a lesson that has since been renamed/removed from the
    # manifest -- the append-only JSONL still has these rows from before the rename.
    orphan_events = [
        {"course_id": "demo", "lesson_id": "demo-l-renamed-away", "n": 1,
         "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
        {"course_id": "demo", "lesson_id": "demo-l-renamed-away", "n": 1,
         "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
    ]

    dirty_dir = tmp_path / "dirty"
    _seed(dirty_dir, "demo", lessons=lessons, events=manifest_events + orphan_events)
    m = figure_metrics.compute(dirty_dir, "demo")

    # Reference: the same manifest, but the telemetry JSONL only ever saw the
    # current lessons (no orphaned rows) -- this is what the metrics SHOULD be.
    clean_dir = tmp_path / "clean"
    _seed(clean_dir, "demo", lessons=lessons, events=manifest_events)
    expected = figure_metrics.compute(clean_dir, "demo")

    assert m["zero_figure_rate"] >= 0.0
    assert m == expected


def test_figures_per_lesson_denominator_is_total_lessons(tmp_path):
    """figures_per_lesson promises figures-per-lesson-in-the-course, so it must
    divide by total_lessons -- not by the count of lessons that already have a
    figure (which would silently mask a lesson with zero figures)."""
    content_dir = tmp_path / "courses"
    _seed(content_dir, "demo",
          lessons={"demo-l1": [{"text": "a", "bloom": "analyze", "knowledge": "conceptual"}],
                   "demo-l2": [{"text": "b", "bloom": "analyze", "knowledge": "conceptual"}]},
          events=[
            {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
             "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
          ])
    m = figure_metrics.compute(content_dir, "demo")
    assert m["figures_per_lesson"] == 0.5   # 1 row / 2 total lessons, not 1 / 1 fig lesson


def test_regression_ok_gate(tmp_path):
    base = {"id_alignment_rate": 0.6, "figures_per_lesson": 1.0, "zero_figure_rate": 0.3}
    good = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.05, "zero_figure_rate": 0.3}
    bad_freq = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.3, "zero_figure_rate": 0.3}
    bad_zero = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.0, "zero_figure_rate": 0.1}
    assert figure_metrics.regression_ok(good, base) is True
    assert figure_metrics.regression_ok(bad_freq, base) is False
    assert figure_metrics.regression_ok(bad_zero, base) is False
