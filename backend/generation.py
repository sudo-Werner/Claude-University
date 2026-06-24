import html as _html
import json
from pathlib import Path

from backend import claude_client, courses

# Default-deny HTML sanitizer: escape everything, then restore a tiny safe allowlist.
# Lessons carry inline formatting (<code>, <em>, <strong>, <br>, <span class="mono">)
# plus structural block tags the generator emits to lay out a lesson (headings,
# paragraphs, lists, preformatted code). Only the exact attribute-less tag strings
# below are restored; anything else — script, img, on* handlers, <a href>, or any
# tag carrying attributes (e.g. "<p onclick=...>") — stays escaped and inert.
_INLINE_TAGS = ["code", "em", "strong"]
_BLOCK_TAGS = ["h1", "h2", "h3", "p", "pre", "ul", "ol", "li"]
_ALLOWED_HTML = {
    "&lt;br&gt;": "<br>", "&lt;br/&gt;": "<br>", "&lt;br /&gt;": "<br>",
    "&lt;hr&gt;": "<hr>", "&lt;hr/&gt;": "<hr>", "&lt;hr /&gt;": "<hr>",
    '&lt;span class=&quot;mono&quot;&gt;': '<span class="mono">',
    "&lt;/span&gt;": "</span>",
}
for _t in _INLINE_TAGS + _BLOCK_TAGS:
    _ALLOWED_HTML["&lt;%s&gt;" % _t] = "<%s>" % _t
    _ALLOWED_HTML["&lt;/%s&gt;" % _t] = "</%s>" % _t

# The generator emits HTML, so it escapes its own special characters (a `<` in
# code becomes the entity `&lt;`). _html.escape would re-escape the leading `&`
# into `&amp;lt;`, which renders as the literal text "&lt;". Undo that one level
# of over-escaping for the standard character entities. Safe: the result is still
# an inert entity (e.g. `&lt;` renders as the character "<", never a live tag),
# so default-deny is preserved.
_ENTITY_RESTORE = {
    "&amp;lt;": "&lt;", "&amp;gt;": "&gt;", "&amp;amp;": "&amp;",
    "&amp;quot;": "&quot;", "&amp;#39;": "&#39;", "&amp;#x27;": "&#x27;",
}


def sanitize_html(value):
    out = _html.escape(str(value), quote=True)
    for escaped, allowed in _ALLOWED_HTML.items():
        out = out.replace(escaped, allowed)
    for double, single in _ENTITY_RESTORE.items():
        out = out.replace(double, single)
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


def valid_check(item):
    if not isinstance(item, dict) or not isinstance(item.get("prompt"), str) \
            or not isinstance(item.get("explanation"), str):
        return False
    if not item["prompt"].strip() or not item["explanation"].strip():
        return False
    if item.get("type") == "mcq":
        choices = item.get("choices")
        answer = item.get("answer")
        return (isinstance(choices, list) and len(choices) >= 2
                and all(isinstance(c, str) and c.strip() for c in choices)
                and isinstance(answer, int) and 0 <= answer < len(choices))
    if item.get("type") == "fill":
        return isinstance(item.get("answer"), str) and bool(item["answer"].strip())
    return False


def valid_lesson(obj):
    if not (isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)):
        return False
    for field in ("promptHtml", "hintHtml", "solutionAns", "solutionNote"):
        if not (isinstance(obj.get(field), str) and obj[field].strip()):
            return False
    checks = obj.get("checks")
    if not (isinstance(checks, list) and 1 <= len(checks) <= 3):
        return False
    return all(valid_check(c) for c in checks)


def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
                  performance="", directive=""):
    perf_line = f"Learner performance so far: {performance}\n" if performance else ""
    directive_line = f"\n{directive}\n" if directive else ""
    return (
        "You are writing one self-contained lesson for a personalized course.\n"
        f"Course context: {brief}\n"
        f"Learner preferences (JSON): {json.dumps(profile or {})}\n"
        f"{perf_line}"
        f"This is lesson {position} of {total}. Module: {module_title}. "
        f"Lesson title: {lesson_title}.\n\n"
        "Write a single exercise-style lesson. Reply with ONLY a JSON object (no prose, no fence) "
        "with exactly these keys:\n"
        f'  id: "{lesson_id}"\n'
        "  courseId, topic (short), step (integer 1), totalSteps (integer 1), "
        'eyebrow ("EXERCISE"), promptHtml (the question as HTML, may use <code>), '
        "hintHtml (a hint as HTML), solutionAns (the answer), "
        "solutionNote (a brief worked example: show the reasoning/steps, not just restate the answer),\n"
        "  checks: a list of 1-3 concept-check items. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,'
        '"explanation":"<specific, encouraging one-sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact expected answer>",'
        '"explanation":"<specific, encouraging one-sentence why>"}.\n'
        "Shape every learner-facing field to the learner preferences above.\n\n"
        # Slice A: evidence-backed readability/engagement guidance (conversational tone,
        # chunking/scannability, worked examples, warm feedback) applied to every lesson.
        "Write so it is genuinely easy and engaging to read:\n"
        "- Speak directly to the learner as 'you', like a friendly tutor. Plain language, "
        "short sentences, no jargon dumps.\n"
        "- Chunk the promptHtml into short paragraphs; wrap the single most important term in "
        "<strong>; use a <ul> for any list of points instead of cramming them into one sentence.\n"
        "- Make the solutionNote a short worked example — walk through the key step of the "
        "reasoning so the learner sees HOW, not just the final answer.\n"
        "- Keep every check explanation specific and encouraging: name what is right and the one "
        "thing to watch, never a bare 'wrong'."
        + directive_line
    )


# ---- #4 answer grading: Claude judges the learner's typed free-text answer ----

_GRADE_VERDICTS = ("correct", "close", "incorrect")


def valid_grade(obj):
    if not isinstance(obj, dict) or obj.get("verdict") not in _GRADE_VERDICTS:
        return False
    note = obj.get("note")
    return isinstance(note, str) and bool(note.strip())


def grade_prompt(*, prompt_html, solution_ans, solution_note, answer):
    return (
        "You are a warm, honest tutor grading a learner's free-text answer to one "
        "exercise on their personal learning platform. Judge understanding, not wording.\n\n"
        f"Exercise (HTML): {prompt_html}\n"
        f"Reference answer: {solution_ans}\n"
        f"Why it is right: {solution_note}\n"
        f"Learner's answer: {answer}\n\n"
        "Decide whether the learner's answer is correct, close (right idea, a gap or "
        "error), or incorrect. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"verdict":"correct"|"close"|"incorrect","note":"<one or two encouraging '
        "sentences addressed to 'you': what you got right, then the single most "
        'important thing to fix or add>"}'
    )


def grade_answer(content_dir, course_id, lesson_id, answer, *, generate):
    lesson = courses.load_lesson(content_dir, course_id, lesson_id)
    if lesson is None:
        return None
    prompt = grade_prompt(
        prompt_html=lesson.get("promptHtml", ""),
        solution_ans=lesson.get("solutionAns", ""),
        solution_note=lesson.get("solutionNote", ""),
        answer=answer,
    )
    result = generate(prompt)
    if not isinstance(result, dict):
        raise claude_client.ClaudeError("grader returned a non-dict result")
    return {"verdict": result["verdict"], "note": sanitize_html(result["note"])}


# ---- #1 real-world evidence capstone: how the concepts show up in the real world ----
# The model supplies real-world example names + descriptions + a SOURCE NAME (not a URL);
# the frontend turns each into a live web-search link. This avoids hallucinated/dead links
# while still giving the learner a one-click path to real evidence.

def valid_capstone(obj):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("intro"), str) and obj["intro"].strip()):
        return False
    items = obj.get("items")
    if not (isinstance(items, list) and 2 <= len(items) <= 6):
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        if not (isinstance(it.get("title"), str) and it["title"].strip()):
            return False
        if not (isinstance(it.get("detail"), str) and it["detail"].strip()):
            return False
        # source is required — the frontend's "Explore" search link is built from it
        if not (isinstance(it.get("source"), str) and it["source"].strip()):
            return False
    return True


def capstone_prompt(*, scope_label, scope_title, concept_titles, brief, profile):
    concepts = "; ".join(t for t in concept_titles if t)
    return (
        f"You are writing a short 'real-world connections' capstone for a learner who just "
        f'finished {scope_label} titled "{scope_title}" in a personal course.\n'
        f"Course context: {brief}\n"
        f"Learner preferences (JSON): {json.dumps(profile or {})}\n"
        f"What they covered: {concepts}\n\n"
        "Show how these ideas show up in the real world — concrete systems, products, research, "
        "or events the learner would recognize — to solidify what they learned. Reply with ONLY a "
        "JSON object, no prose, no fence:\n"
        '{"intro":"<one or two sentences connecting their study to the real world>",'
        '"items":[{"title":"<a real, recognizable example: a named system, product, paper, or '
        'event>","detail":"<1-2 sentences, addressed to \'you\', on how the concept applies '
        'there>","source":"<a short well-known SOURCE NAME to look it up, e.g. \'PyTorch docs\', '
        "'Wikipedia', 'DeepMind' — a name, NOT a URL>\"}]}"
        " Provide 3 to 5 items grounded in real, recognizable things — never invent products or "
        "papers. Use a source NAME, never a URL (the app builds the link)."
    )


def ensure_capstone(content_dir, course_id, scope, profile, *, generate):
    path = Path(content_dir) / course_id / "capstones" / f"{scope}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass  # regenerate a corrupt cache
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    modules = manifest.get("modules", [])
    if scope == "course":
        scope_label = "this course"
        scope_title = manifest.get("title", "")
        concept_titles = [m.get("title", "") for m in modules]
    else:
        module = next((m for m in modules if m.get("id") == scope), None)
        if module is None:
            return None
        scope_label = "the module"
        scope_title = module.get("title", "")
        concept_titles = [l.get("title", "") for l in module.get("lessons", [])]
    prompt = capstone_prompt(
        scope_label=scope_label, scope_title=scope_title, concept_titles=concept_titles,
        brief=manifest.get("brief", ""), profile=profile,
    )
    capstone = generate(prompt)
    if not isinstance(capstone, dict):
        raise claude_client.ClaudeError("capstone generator returned a non-dict result")
    if not valid_capstone(capstone):
        raise claude_client.ClaudeError("generated capstone failed validation")
    capstone["scope"] = scope
    capstone["title"] = scope_title
    capstone["intro"] = sanitize_html(capstone.get("intro", ""))
    for it in capstone.get("items", []):
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("detail"), str):
            it["detail"] = sanitize_html(it["detail"])
        if isinstance(it.get("title"), str):
            it["title"] = _html.escape(it["title"], quote=True)
        if isinstance(it.get("source"), str):
            it["source"] = _html.escape(it["source"], quote=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capstone, indent=2, ensure_ascii=False))
    return capstone


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
    except claude_client.ClaudeAuthError:
        yield _sse("error", json.dumps({"message": "Claude needs re-authentication on the Pi — run `claude` there to log in again."}))
        return
    except claude_client.ClaudeError:
        yield _sse("error", json.dumps({"message": "Claude is unavailable right now."}))
        return
    proposal = detect_proposal("".join(full))
    if proposal is not None:
        yield _sse("proposal", json.dumps(proposal))
    yield _sse("done", "{}")


def _generate_and_store_lesson(content_dir, course_id, lesson_id, profile, *, generate,
                               performance="", directive=""):
    """Generate one lesson, reconcile authoritative fields, sanitize, validate, and
    cache it (overwriting any existing file). Shared by ensure_lesson (cache-miss
    generation) and deepen_lesson (forced regeneration with a depth directive).
    Returns None if the manifest or the lesson's manifest entry is missing."""
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    flat = courses.flatten_lessons(manifest)
    meta = None
    position = None
    for i, l in enumerate(flat):
        if l["id"] == lesson_id:
            meta = l
            position = i + 1
            break
    if meta is None:
        return None
    prompt = lesson_prompt(
        brief=manifest.get("brief", ""),
        profile=profile,
        lesson_id=lesson_id,
        lesson_title=meta["title"],
        module_title=meta["moduleTitle"],
        position=position,
        total=len(flat),
        performance=performance,
        directive=directive,
    )
    lesson = generate(prompt)
    if not isinstance(lesson, dict):
        raise claude_client.ClaudeError("generator returned a non-dict result")
    lesson["id"] = lesson_id
    lesson["courseId"] = course_id
    lesson["step"] = position
    lesson["totalSteps"] = len(flat)
    for field in ("promptHtml", "hintHtml", "solutionAns", "solutionNote"):
        if isinstance(lesson.get(field), str):
            lesson[field] = sanitize_html(lesson[field])
    for field in ("topic", "eyebrow"):
        if isinstance(lesson.get(field), str):
            lesson[field] = _html.escape(lesson[field], quote=True)
    if isinstance(lesson.get("checks"), list):
        for chk in lesson["checks"]:
            if not isinstance(chk, dict):
                continue
            for f in ("prompt", "explanation"):
                if isinstance(chk.get(f), str):
                    chk[f] = sanitize_html(chk[f])
            if isinstance(chk.get("choices"), list):
                chk["choices"] = [sanitize_html(c) if isinstance(c, str) else c for c in chk["choices"]]
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    path.write_text(json.dumps(lesson, indent=2, ensure_ascii=False))
    return lesson


def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance=""):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    return _generate_and_store_lesson(
        content_dir, course_id, lesson_id, profile, generate=generate, performance=performance,
    )


# #5 — the learner says they are rusty; regenerate this one lesson deeper, assuming
# less prior knowledge, and overwrite the cache so the deeper version sticks.
_DEEPEN_DIRECTIVE = (
    "IMPORTANT: the learner has said they are rusty on this and want more depth. "
    "Assume less prior knowledge: briefly re-establish the fundamentals and any "
    "prerequisite ideas this lesson builds on, define the key terms, and walk through "
    "the reasoning in smaller, explicit steps with a concrete worked example before "
    "asking them to apply it. Keep the same single-exercise shape and JSON keys."
)


def deepen_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance=""):
    return _generate_and_store_lesson(
        content_dir, course_id, lesson_id, profile, generate=generate,
        performance=performance, directive=_DEEPEN_DIRECTIVE,
    )
