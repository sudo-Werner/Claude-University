import json
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
            })
    return out


def completed_lesson_ids(conn, course_id):
    rows = conn.execute(
        "SELECT DISTINCT topic_id FROM events "
        "WHERE event_type = 'lesson_completed' AND course_id = ?",
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
                "reviewsDue": 0,
            })
        except Exception:
            continue  # skip malformed course
    return summaries
