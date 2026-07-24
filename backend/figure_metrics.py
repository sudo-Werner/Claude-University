"""Population-level figure distribution-health metrics (spec §5D). Reads the
figure-telemetry JSONL, joins each lesson to its objective stratum via the
objective registry, and reports the signals the regression gate checks. Never a
per-lesson ground-truth label — only aggregate health."""

from collections import defaultdict

from backend import courses, figure_telemetry, objectives


def _lesson_strata(content_dir, course_id):
    """{lesson_id: True if any objective is identification-stratum} — factual
    knowledge at a low Bloom level (remember/understand)."""
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return {}
    strata = {}
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            objs = objectives.for_lesson(manifest, lesson)
            strata[lesson["id"]] = any(
                o.get("knowledge") == "factual" and o.get("bloom") in ("remember", "understand")
                for o in objs if isinstance(o, dict))
    return strata


def compute(content_dir, course_id):
    rows = [r for r in figure_telemetry.read(content_dir) if r.get("course_id") == course_id]
    strata = _lesson_strata(content_dir, course_id)
    # The telemetry JSONL is append-only and accumulates rows for all time,
    # including lessons since renamed or removed from the manifest. Bound
    # aggregation to the current manifest's lessons so stale/orphaned rows
    # can't inflate fig_lessons past total_lessons or drift the per-lesson mean.
    rows = [r for r in rows if r.get("lesson_id") in strata]
    by_lesson = defaultdict(list)
    for r in rows:
        by_lesson[r.get("lesson_id")].append(r)

    drawn = [r for r in rows if r.get("requested_type") in ("mermaid", "svg", "svg-animated")]
    photos = [r for r in rows if r.get("requested_type") == "web-image"]
    drawn_and_photo = len(drawn) + len(photos)

    id_lessons = [lid for lid, fig in by_lesson.items() if strata.get(lid)]
    id_with_photo = sum(
        1 for lid in id_lessons
        if any(r.get("requested_type") == "web-image" for r in by_lesson[lid]))

    total_lessons = len(strata) or 1
    fig_lessons = [lid for lid, fig in by_lesson.items() if fig]

    def rate(num, den):
        return round(num / den, 4) if den else 0.0

    return {
        "id_alignment_rate": rate(id_with_photo, len(id_lessons)),
        "mermaid_share": rate(sum(1 for r in drawn if r["requested_type"] == "mermaid"),
                              drawn_and_photo),
        "web_image_realization_rate": rate(
            sum(1 for r in photos if r.get("outcome") == "rendered"), len(photos)),
        "figures_per_lesson": rate(len(rows), total_lessons),
        "zero_figure_rate": rate(total_lessons - len(fig_lessons), total_lessons),
    }


def regression_ok(current, baseline):
    """Gate: alignment not lower AND figures/lesson within +/-10% of baseline AND
    zero-figure rate not falling (spec §5D)."""
    if current["id_alignment_rate"] < baseline["id_alignment_rate"]:
        return False
    base_fpl = baseline["figures_per_lesson"] or 1e-9
    if abs(current["figures_per_lesson"] - baseline["figures_per_lesson"]) / base_fpl > 0.10:
        return False
    if current["zero_figure_rate"] < baseline["zero_figure_rate"]:
        return False
    return True
