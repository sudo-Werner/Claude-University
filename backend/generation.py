import html as _html
import json
from pathlib import Path

from backend import claude_client, courses

# Default-deny HTML sanitizer: escape everything, then restore a tiny safe allowlist.
# The lesson fields are meant to carry only <code>, <em>, <strong>, <br>, and
# <span class="mono"> formatting; anything else (script, img, on* handlers, other
# tags/attributes) stays escaped and inert.
_ALLOWED_HTML = {
    "&lt;code&gt;": "<code>", "&lt;/code&gt;": "</code>",
    "&lt;em&gt;": "<em>", "&lt;/em&gt;": "</em>",
    "&lt;strong&gt;": "<strong>", "&lt;/strong&gt;": "</strong>",
    "&lt;br&gt;": "<br>", "&lt;br/&gt;": "<br>", "&lt;br /&gt;": "<br>",
    '&lt;span class=&quot;mono&quot;&gt;': '<span class="mono">',
    "&lt;/span&gt;": "</span>",
}


def sanitize_html(value):
    out = _html.escape(str(value), quote=True)
    for escaped, allowed in _ALLOWED_HTML.items():
        out = out.replace(escaped, allowed)
    return out


COURSE_SYSTEM_PROMPT = (
    "You are a curriculum designer building a personalized course for a single learner "
    "on their personal learning platform. Have a short, friendly conversation to understand "
    "their goal, prior knowledge, desired depth, and how intensively they want to study. "
    "Ask one or two focused questions per turn. When you have enough to propose a curriculum, "
    "reply with a brief sentence and then a fenced code block labelled `course` containing ONLY "
    "JSON of this shape:\n"
    "```course\n"
    '{"title": "...", "subtitle": "...", "brief": "<one paragraph capturing audience level, '
    'depth, pace, and goals for later lesson generation>", '
    '"modules": [{"title": "...", "lessons": [{"title": "..."}]}]}\n'
    "```\n"
    "Keep the course focused: 3-6 modules, 3-6 lessons each. Do not emit the course block until "
    "you have enough information."
)

LESSON_KEYS = (
    "id", "courseId", "topic", "step", "totalSteps",
    "eyebrow", "promptHtml", "hintHtml", "solutionAns", "solutionNote",
)


def detect_proposal(text):
    return claude_client.extract_fenced_json(text, "course")


def valid_lesson(obj):
    return isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)


def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total):
    return (
        "You are writing one self-contained lesson for a personalized course.\n"
        f"Course context: {brief}\n"
        f"Learner preferences (JSON): {json.dumps(profile or {})}\n"
        f"This is lesson {position} of {total}. Module: {module_title}. "
        f"Lesson title: {lesson_title}.\n\n"
        "Write a single exercise-style lesson. Reply with ONLY a JSON object (no prose, no fence) "
        "with exactly these keys:\n"
        f'  id: "{lesson_id}"\n'
        "  courseId, topic (short), step (integer 1), totalSteps (integer 1), "
        'eyebrow ("EXERCISE"), promptHtml (the question as HTML, may use <code>), '
        "hintHtml (a hint as HTML), solutionAns (the answer), solutionNote (one-sentence why).\n"
        "Shape every learner-facing field to the learner preferences above."
    )


def build_chat_prompt(messages, profile):
    lines = [COURSE_SYSTEM_PROMPT, "", f"Learner preferences (JSON): {json.dumps(profile or {})}", ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)


def _sse(event, data):
    payload = "\n".join(f"data: {line}" for line in data.split("\n"))
    return f"event: {event}\n{payload}\n\n"


def chat_sse(messages, profile, *, stream_fn):
    prompt = build_chat_prompt(messages, profile)
    full = []
    try:
        for chunk in stream_fn(prompt):
            full.append(chunk)
            yield _sse("delta", chunk)
    except claude_client.ClaudeError:
        yield _sse("error", json.dumps({"message": "Claude is unavailable right now."}))
        return
    proposal = detect_proposal("".join(full))
    if proposal is not None:
        yield _sse("proposal", json.dumps(proposal))
    yield _sse("done", "{}")


def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    flat = courses.flatten_lessons(manifest)
    meta = next((l for l in flat if l["id"] == lesson_id), None)
    if meta is None:
        return None
    position = [l["id"] for l in flat].index(lesson_id) + 1
    prompt = lesson_prompt(
        brief=manifest.get("brief", ""),
        profile=profile,
        lesson_id=lesson_id,
        lesson_title=meta["title"],
        module_title=meta["moduleTitle"],
        position=position,
        total=len(flat),
    )
    lesson = generate(prompt)
    if isinstance(lesson, dict):
        lesson["id"] = lesson_id
        lesson["courseId"] = course_id
        lesson["step"] = position
        lesson["totalSteps"] = len(flat)
    for field in ("promptHtml", "hintHtml", "solutionAns", "solutionNote"):
        if isinstance(lesson, dict) and isinstance(lesson.get(field), str):
            lesson[field] = sanitize_html(lesson[field])
    for field in ("topic", "eyebrow"):
        if isinstance(lesson, dict) and isinstance(lesson.get(field), str):
            lesson[field] = _html.escape(lesson[field], quote=True)
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    path.write_text(json.dumps(lesson, indent=2, ensure_ascii=False))
    return lesson
