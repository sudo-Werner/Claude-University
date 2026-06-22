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
