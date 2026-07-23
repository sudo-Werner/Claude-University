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


def test_regression_ok_gate(tmp_path):
    base = {"id_alignment_rate": 0.6, "figures_per_lesson": 1.0, "zero_figure_rate": 0.3}
    good = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.05, "zero_figure_rate": 0.3}
    bad_freq = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.3, "zero_figure_rate": 0.3}
    bad_zero = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.0, "zero_figure_rate": 0.1}
    assert figure_metrics.regression_ok(good, base) is True
    assert figure_metrics.regression_ok(bad_freq, base) is False
    assert figure_metrics.regression_ok(bad_zero, base) is False
