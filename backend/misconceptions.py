"""Per-course misconception profile (charter Tier 2 item 7): non-empty
`misconceptions` strings from the teach-it-to-Claude and explain-it-back
graders' structured rubric accumulate here — learner state, not a
lesson-content cache (contrast spine.json, review-items: apply_revision
prunes those, this file is deliberately never pruned; see courses.py).

Lives in content/courses/<course_id>/misconceptions.json, plain text only
(no sanitize_html at store time — entries get json.dumps'd into a future
lesson prompt as data; HTML entities baked in at store time would corrupt
that). Escaping for display is the frontend's job (esc()), same as
mynotes.js.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil, generation

_MAX_EXCERPT = 280


def _path(content_dir, course_id):
    return Path(content_dir) / course_id / "misconceptions.json"


def _normalize(text):
    return re.sub(r"\s+", " ", text.strip().casefold())


def load_profile(content_dir, course_id):
    """Newest-first. A missing, corrupt, or malformed file reads as []."""
    path = _path(content_dir, course_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return []
    entries = [e for e in data["entries"] if isinstance(e, dict)]
    return sorted(entries, key=lambda e: e.get("occurredAt", ""), reverse=True)


def _save(content_dir, course_id, entries):
    path = _path(content_dir, course_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(
        path,
        json.dumps({"courseId": course_id, "entries": entries}, indent=2, ensure_ascii=False),
    )


def add_entries(content_dir, course_id, lesson_id, lesson_title, source, texts_and_excerpts):
    """texts_and_excerpts: list of (misconception_text, excerpt) string pairs.
    Blank text is skipped. A new entry whose normalized text already matches
    an existing entry (anywhere in the course, not just this lesson) is
    skipped — the same misunderstanding re-detected later doesn't re-append.
    Locked per-course so a concurrent teach+explain grading pair can't race
    each other's read-modify-write.
    """
    with generation._gen_lock(("misconceptions", course_id)):
        existing = load_profile(content_dir, course_id)
        seen = {_normalize(e["text"]) for e in existing if isinstance(e.get("text"), str)}
        now = datetime.now(timezone.utc).isoformat()
        added = False
        for text, excerpt in texts_and_excerpts:
            if not isinstance(text, str) or not text.strip():
                continue
            norm = _normalize(text)
            if norm in seen:
                continue
            seen.add(norm)
            existing.append({
                "id": f"mc-{uuid.uuid4().hex[:12]}",
                "text": text.strip(),
                "excerpt": (excerpt or "").strip()[:_MAX_EXCERPT],
                "lessonId": lesson_id,
                "lessonTitle": lesson_title,
                "source": source,
                "occurredAt": now,
            })
            added = True
        if added:
            _save(content_dir, course_id, existing)


def delete_entry(content_dir, course_id, entry_id):
    with generation._gen_lock(("misconceptions", course_id)):
        existing = load_profile(content_dir, course_id)
        kept = [e for e in existing if e.get("id") != entry_id]
        if len(kept) == len(existing):
            return False
        _save(content_dir, course_id, kept)
        return True
