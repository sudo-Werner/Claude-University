import json
import re
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil, objectives, spine

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "courses"


def load_manifest(content_dir, course_id):
    path = Path(content_dir) / course_id / "course.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None  # corrupt manifest reads as missing (404), never a 500


def load_lesson(content_dir, course_id, lesson_id):
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None  # corrupt cache reads as missing so ensure_lesson regenerates it


def flatten_lessons(manifest):
    out = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            out.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "moduleTitle": module["title"],
                "objectives": objectives.for_lesson(manifest, lesson),
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
    from backend import exams, srs
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
                "passed": exams.course_passed(
                    exams.exam_status(conn, child.name, manifest), manifest),
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
    fsutil.write_text_atomic(course_dir / "course.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def apply_revision(content_dir, course_id, revised, *, now=None):
    """Validate, back up, and atomically write a revised course manifest in-place.

    Returns the revised dict on success, or None if validation fails or the course
    directory does not exist. Never touches the lessons/ directory. Prunes spine.json
    entries for lessons removed from the syllabus.
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
    fsutil.write_text_atomic(manifest_path, json.dumps(revised, indent=2, ensure_ascii=False))
    # Same per-course lock generation holds for its spine upsert: an unlocked prune
    # racing a concurrent lesson generation could clobber the just-written entry.
    with generation._gen_lock(("spine", course_id)):
        spine.prune(content_dir, course_id, seen)
    # Pending exams and gap reviews for modules dropped by the revision are dead.
    # (Not locked: a concurrent start for a just-dropped module can at worst leave
    # one stale file, which status/freshness checks ignore and the next revision removes.)
    from backend import exams, remediation, review_items
    module_ids = {m.get("id") for m in revised.get("modules", [])}
    exams.prune_pending(content_dir, course_id, module_ids | {"final"})
    remediation.prune(content_dir, course_id, module_ids | {"final"})
    # review-items are keyed by lesson id (like spine.json), not exam key -> reuse `seen`,
    # the lesson-id set already validated above and used for spine.prune.
    review_items.prune(content_dir, course_id, seen)
    # misconceptions.json is deliberately NEVER pruned here, unlike the caches above:
    # spine/review-items/exams are lesson-CONTENT caches (stale entries are dead weight
    # once the syllabus changes), but a misconception profile is learner STATE — the
    # learner's misunderstanding of a concept doesn't evaporate because the course was
    # reorganized, and silently deleting profile entries without the learner's own
    # action would violate the "nothing in your profile is unaccountable" trust model
    # the feature is built on. Its lessonTitle field is a write-time snapshot for
    # exactly this reason — never re-resolved against the current manifest.
    return revised
