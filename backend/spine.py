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
