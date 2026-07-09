import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "courses"


def load_manifest(content_dir, course_id):
    path = Path(content_dir) / course_id / "course.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_lesson(content_dir, course_id, lesson_id):
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def flatten_lessons(manifest):
    out = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            out.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "moduleTitle": module["title"],
                "objectives": lesson.get("objectives", []),
            })
    return out


def completed_lesson_ids(conn, course_id):
    rows = conn.execute(
        "SELECT DISTINCT topic_id FROM events "
        "WHERE event_type IN ('lesson_completed', 'lesson_reviewed') AND course_id = ?",
        (course_id,),
    ).fetchall()
    return {r["topic_id"] for r in rows if r["topic_id"]}


def course_progress(conn, content_dir, course_id):
    manifest = load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    lessons = flatten_lessons(manifest)
    done_ids = completed_lesson_ids(conn, course_id)
    done = sum(1 for lesson in lessons if lesson["id"] in done_ids)
    total = len(lessons)
    pct = round(done / total * 100) if total else 0
    next_lesson = next((lesson for lesson in lessons if lesson["id"] not in done_ids), None)
    return {"done": done, "total": total, "pct": pct, "nextLesson": next_lesson}


def list_courses(conn, content_dir):
    # Deferred here to avoid a courses↔srs circular import (srs imports courses at module level).
    from backend import srs
    content_dir = Path(content_dir)
    summaries = []
    if not content_dir.exists():
        return summaries
    for child in sorted(content_dir.iterdir()):
        if not (child / "course.json").exists():
            continue
        try:  # skip malformed course
            manifest = load_manifest(content_dir, child.name)
            progress = course_progress(conn, content_dir, child.name)
            summaries.append({
                "id": manifest["id"],
                "title": manifest["title"],
                "subtitle": manifest.get("subtitle", ""),
                "progress": {k: progress[k] for k in ("done", "total", "pct")},
                "nextLesson": progress["nextLesson"],
                "reviewsDue": srs.reviews_due_count(conn, content_dir, child.name),
            })
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # skip malformed course
    return summaries


def slug_for(title, existing_ids):
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if not base:
        base = "course"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


def write_course(content_dir, proposal):
    content_dir = Path(content_dir)
    existing = {p.name for p in content_dir.iterdir()} if content_dir.exists() else set()
    course_id = slug_for(proposal["title"], existing)

    # Map each lesson's provisional id (compiler's l1..lN, or positional for legacy) to its slugged
    # id first, so prereq edges can be remapped to the same slugged ids.
    id_map, counter = {}, 1
    for module in proposal.get("modules", []):
        for lesson in module.get("lessons", []):
            id_map[lesson.get("id") or f"l{counter}"] = f"{course_id}-l{counter}"
            counter += 1

    modules, counter = [], 1
    for m_idx, module in enumerate(proposal.get("modules", []), start=1):
        lessons = []
        for lesson in module.get("lessons", []):
            new_lesson = {"id": f"{course_id}-l{counter}", "title": lesson["title"]}
            if "objectives" in lesson:
                new_lesson["objectives"] = lesson["objectives"]
            if "estMinutes" in lesson:
                new_lesson["estMinutes"] = lesson["estMinutes"]
            if "prereqs" in lesson:
                new_lesson["prereqs"] = [id_map.get(p, p) for p in lesson.get("prereqs", [])]
            lessons.append(new_lesson)
            counter += 1
        new_module = {"id": f"m{m_idx}", "title": module["title"], "lessons": lessons}
        if "outcomes" in module:
            new_module["outcomes"] = module["outcomes"]
        modules.append(new_module)

    manifest = {
        "id": course_id,
        "title": proposal["title"],
        "subtitle": proposal.get("subtitle", ""),
        "brief": proposal.get("brief", ""),
        "modules": modules,
    }
    # Carry the compiled (schemaVersion 2) course-level fields through when present; legacy
    # proposals omit them and write exactly as before.
    for field in ("schemaVersion", "learnerBrief", "level", "targetHours", "skills",
                  "outcomes", "groundingSources"):
        if field in proposal:
            manifest[field] = proposal[field]

    course_dir = content_dir / course_id
    (course_dir / "lessons").mkdir(parents=True, exist_ok=True)
    (course_dir / "course.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def _lesson_id_list(manifest):
    """Return a flat list of lesson ids from a manifest dict."""
    return [l.get("id") for m in manifest.get("modules", []) for l in m.get("lessons", [])]


def apply_revision(content_dir, course_id, revised, *, now=None):
    """Validate, back up, and atomically write a revised course manifest in-place.

    Returns the revised dict on success, or None if validation fails or the course
    directory does not exist. Never touches the lessons/ directory.
    """
    content_dir = Path(content_dir)
    course_dir = content_dir / course_id
    manifest_path = course_dir / "course.json"
    if not manifest_path.exists():
        return None
    if not isinstance(revised, dict) or revised.get("id") != course_id:
        return None
    from backend import generation
    if not generation.valid_compiled_course(revised):
        return None
    current = json.loads(manifest_path.read_text())
    existing_ids = {l.get("id") for m in current.get("modules", []) for l in m.get("lessons", [])}
    pattern = re.compile(rf"^{re.escape(course_id)}-l\d+$")
    seen = set()
    for m in revised.get("modules", []):
        for l in m.get("lessons", []):
            lid = l.get("id")
            if lid in seen:
                return None
            seen.add(lid)
            if lid not in existing_ids and not pattern.match(lid or ""):
                return None
    if now is None:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (course_dir / f"course.json.pre-revise-{now}").write_text(manifest_path.read_text())
    tmp = course_dir / "course.json.tmp"
    tmp.write_text(json.dumps(revised, indent=2, ensure_ascii=False))
    os.replace(tmp, manifest_path)
    return revised
