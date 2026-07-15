import json
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil

_MAX_BYTES = 100_000  # ~100 KB cap on the serialized notes + chat
_EMPTY = {"notes": "", "chat": [], "updatedAt": None}


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


def save_workspace(content_dir, course_id, lesson_id, notes, chat):
    if not isinstance(notes, str) or not _valid_chat(chat):
        raise ValueError("invalid workspace shape")
    record = {
        "notes": notes,
        "chat": [{"role": m["role"], "content": m["content"]} for m in chat],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    blob = json.dumps(record, ensure_ascii=False)
    if len(blob.encode("utf-8")) > _MAX_BYTES:
        raise WorkspaceTooLarge("workspace too large")
    path = _path(content_dir, course_id, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, blob)
    return record
