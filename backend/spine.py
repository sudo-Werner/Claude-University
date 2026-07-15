"""Per-course knowledge spine: what each lesson actually taught.

The spine lives in content/courses/<course_id>/spine.json and is used ONLY on the
generation side — entries are harvested from generated lessons and injected into
later lessons' prompts so they build on prior material with consistent terms.
It is never sent to the browser, so its fields carry plain text, not sanitized HTML.
"""

import json
from pathlib import Path

from backend import fsutil

MAX_CONCEPTS = 4


def _spine_path(content_dir, course_id):
    return Path(content_dir) / course_id / "spine.json"


def load_spine(content_dir, course_id):
    """Return the spine dict; a missing, corrupt, or malformed file reads as empty."""
    path = _spine_path(content_dir, course_id)
    if not path.exists():
        return {"lessons": {}}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {"lessons": {}}
    if not isinstance(data, dict) or not isinstance(data.get("lessons"), dict):
        return {"lessons": {}}
    return data


def save_spine(content_dir, course_id, spine_data):
    fsutil.write_text_atomic(
        _spine_path(content_dir, course_id),
        json.dumps(spine_data, indent=2, ensure_ascii=False),
    )


def upsert_entry(content_dir, course_id, lesson_id, entry):
    spine_data = load_spine(content_dir, course_id)
    spine_data["lessons"][lesson_id] = entry
    save_spine(content_dir, course_id, spine_data)


def prune(content_dir, course_id, keep_ids):
    """Drop entries for lessons no longer in the syllabus. No-op when nothing changes."""
    spine_data = load_spine(content_dir, course_id)
    kept = {lid: e for lid, e in spine_data["lessons"].items() if lid in keep_ids}
    if kept != spine_data["lessons"]:
        spine_data["lessons"] = kept
        save_spine(content_dir, course_id, spine_data)


def valid_spine_entry(obj):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("summary"), str) and obj["summary"].strip()):
        return False
    concepts = obj.get("concepts")
    if not (isinstance(concepts, list) and 1 <= len(concepts) <= MAX_CONCEPTS):
        return False
    for c in concepts:
        if not isinstance(c, dict):
            return False
        for field in ("term", "definition"):
            if not (isinstance(c.get(field), str) and c[field].strip()):
                return False
    return True


# ---- One-off backfill: index lessons cached before the spine existed ----


def backfill_prompt(batch):
    """batch: list of (lesson_id, cached_lesson_dict)."""
    lessons_txt = "\n\n".join(
        f"LESSON id={lid}\nTopic: {lesson.get('topic', '')}\n"
        f"Body: {lesson.get('promptHtml', '')}\n"
        f"Worked example: {lesson.get('solutionNote', '')}"
        for lid, lesson in batch
    )
    return (
        "You are indexing existing lessons of a course for a knowledge spine that "
        "future lessons will build on.\n"
        "For EACH lesson below, state what it taught. Reply with ONLY a JSON object "
        "(no prose, no fence) mapping each lesson id to "
        '{"summary":"<one plain-text sentence>","concepts":[{"term":"<exact term as '
        'used in the lesson>","definition":"<one plain-text sentence>"}]} with 1-4 '
        "concepts per lesson. No HTML in any field. Include every id exactly once.\n\n"
        + lessons_txt
    )


def valid_backfill(expected_ids):
    """Validator factory for one backfill batch: exact id set, every entry valid."""
    expected = set(expected_ids)

    def check(obj):
        return (isinstance(obj, dict)
                and set(obj.keys()) == expected
                and all(valid_spine_entry(v) for v in obj.values()))

    return check


def backfill_course(content_dir, course_id, *, generate, batch_size=10):
    """Extract spine entries for cached lessons missing from the spine.

    generate(prompt, validate) -> validated dict (the run_structured convention).
    Idempotent: lessons already in the spine are skipped, so re-running is safe.
    Returns the number of entries added.
    """
    lessons_dir = Path(content_dir) / course_id / "lessons"
    if not lessons_dir.is_dir():
        return 0
    present = load_spine(content_dir, course_id)["lessons"]
    pending = []
    for path in sorted(lessons_dir.glob("*.json")):
        lesson_id = path.stem
        if lesson_id in present:
            continue
        try:
            lesson = json.loads(path.read_text())
        except ValueError:
            continue  # corrupt cache file; ensure_lesson will regenerate it anyway
        if isinstance(lesson, dict):
            pending.append((lesson_id, lesson))
    added = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        ids = [lid for lid, _ in batch]
        result = generate(backfill_prompt(batch), valid_backfill(ids))
        spine_data = load_spine(content_dir, course_id)
        for lid in ids:
            spine_data["lessons"][lid] = result[lid]
        save_spine(content_dir, course_id, spine_data)
        added += len(ids)
    return added


if __name__ == "__main__":
    from backend import claude_client

    content_dir = Path(__file__).resolve().parent.parent / "content" / "courses"
    run = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
    for course_dir in sorted(p for p in content_dir.iterdir() if p.is_dir()):
        count = backfill_course(content_dir, course_dir.name, generate=run)
        print(f"{course_dir.name}: {count} spine entries added")
