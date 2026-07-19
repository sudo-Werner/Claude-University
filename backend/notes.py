import json
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil

_MAX_BYTES = 100_000  # ~100 KB cap on the serialized notes + chat + highlights
_MAX_HIGHLIGHT_TEXT = 2000  # per-highlight text cap (design doc Decision 3)
_MAX_HIGHLIGHT_ID = 64  # generous cap on the client-generated id (ids.newId()), not a real limit
_EMPTY = {"notes": "", "chat": [], "highlights": [], "updatedAt": None}


class WorkspaceTooLarge(ValueError):
    pass


def _path(content_dir, course_id, lesson_id):
    return Path(content_dir) / course_id / "notes" / f"{lesson_id}.json"


def load_workspace(content_dir, course_id, lesson_id):
    path = _path(content_dir, course_id, lesson_id)
    if not path.exists():
        return dict(_EMPTY)
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    return {
        "notes": data["notes"] if isinstance(data.get("notes"), str) else "",
        "chat": data["chat"] if isinstance(data.get("chat"), list) else [],
        "highlights": data["highlights"] if isinstance(data.get("highlights"), list) else [],
        "updatedAt": data.get("updatedAt"),
    }


def _valid_chat(chat):
    if not isinstance(chat, list):
        return False
    for m in chat:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return False
        if not isinstance(m.get("content"), str):
            return False
    return True


def _valid_highlights(highlights):
    if not isinstance(highlights, list):
        return False
    for h in highlights:
        if not isinstance(h, dict):
            return False
        hid = h.get("id")
        if not isinstance(hid, str) or not hid or len(hid) > _MAX_HIGHLIGHT_ID:
            return False
        text = h.get("text")
        if not isinstance(text, str) or not text or len(text) > _MAX_HIGHLIGHT_TEXT:
            return False
        occurrence = h.get("occurrence")
        # bool is a subclass of int in Python -- must be excluded explicitly, checked
        # BEFORE the int check, or True/False would silently pass as 1/0.
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0:
            return False
    return True


def save_workspace(content_dir, course_id, lesson_id, notes, chat, highlights=None):
    if highlights is None:
        highlights = []
    if not isinstance(notes, str) or not _valid_chat(chat) or not _valid_highlights(highlights):
        raise ValueError("invalid workspace shape")
    record = {
        "notes": notes,
        "chat": [{"role": m["role"], "content": m["content"]} for m in chat],
        "highlights": [
            {"id": h["id"], "text": h["text"], "occurrence": h["occurrence"]} for h in highlights
        ],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    blob = json.dumps(record, ensure_ascii=False)
    if len(blob.encode("utf-8")) > _MAX_BYTES:
        raise WorkspaceTooLarge("workspace too large")
    path = _path(content_dir, course_id, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, blob)
    return record


def course_notes_summary(content_dir, course_id, manifest):
    """Read-only per-lesson aggregate of notes + highlights across a whole
    course, in curriculum order, for the 'My notes' view (charter Tier 3 #20 —
    display only, no AI processing). Skips lessons with neither: most lessons
    are never annotated, and this view exists to surface the ones that were."""
    out = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            lesson_id = lesson.get("id")
            ws = load_workspace(content_dir, course_id, lesson_id)
            notes_text = (ws.get("notes") or "").strip()
            highlights = [h.get("text", "") for h in (ws.get("highlights") or [])
                         if isinstance(h, dict)]
            if not notes_text and not highlights:
                continue
            out.append({
                "lessonId": lesson_id,
                "lessonTitle": lesson.get("title", ""),
                "moduleTitle": module.get("title", ""),
                "notes": notes_text,
                "highlights": highlights,
                "updatedAt": ws.get("updatedAt"),
            })
    return out
