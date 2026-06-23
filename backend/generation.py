import json

from backend import claude_client

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
    return f"event: {event}\ndata: {data}\n\n"


def chat_sse(messages, profile, *, stream_fn):
    prompt = build_chat_prompt(messages, profile)
    full = []
    for chunk in stream_fn(prompt):
        full.append(chunk)
        yield _sse("delta", chunk)
    proposal = detect_proposal("".join(full))
    if proposal is not None:
        yield _sse("proposal", json.dumps(proposal))
    yield _sse("done", "{}")
