import html as _html
import json
import re as _re
import threading
from pathlib import Path

from backend import claude_client, courses, fsutil, spine

# Single-flight: expensive generations (a lesson is ~110s of Max-plan web search) must
# never run twice concurrently for the same artifact. The second caller blocks on the
# per-key lock, then finds the cache the first caller just wrote.
_GEN_LOCKS = {}
_GEN_LOCKS_GUARD = threading.Lock()


def _gen_lock(key):
    with _GEN_LOCKS_GUARD:
        lock = _GEN_LOCKS.get(key)
        if lock is None:
            lock = _GEN_LOCKS[key] = threading.Lock()
    return lock


# Default-deny HTML sanitizer: escape everything, then restore a tiny safe allowlist.
# Lessons carry inline formatting (<code>, <em>, <strong>, <br>, <span class="mono">)
# plus structural block tags the generator emits to lay out a lesson (headings,
# paragraphs, lists, preformatted code). Only the exact attribute-less tag strings
# below are restored; anything else — script, img, on* handlers, <a href>, or any
# tag carrying attributes (e.g. "<p onclick=...>") — stays escaped and inert.
_INLINE_TAGS = ["code", "em", "strong"]
# Block tags include the comparison-table family (#visual-aids); all attribute-less,
# so a cell carrying an attribute (e.g. "<td onclick=...>") stays escaped and inert.
_BLOCK_TAGS = ["h1", "h2", "h3", "p", "pre", "ul", "ol", "li",
               "table", "thead", "tbody", "tr", "th", "td"]
_ALLOWED_HTML = {
    "&lt;br&gt;": "<br>", "&lt;br/&gt;": "<br>", "&lt;br /&gt;": "<br>",
    "&lt;hr&gt;": "<hr>", "&lt;hr/&gt;": "<hr>", "&lt;hr /&gt;": "<hr>",
    '&lt;span class=&quot;mono&quot;&gt;': '<span class="mono">',
    "&lt;/span&gt;": "</span>",
    # Visual-aid containers: only these EXACT class strings are restored. An unlisted
    # class ("<div class=evil>") or any attribute-bearing div stays escaped/inert.
    '&lt;div class=&quot;callout&quot;&gt;': '<div class="callout">',
    '&lt;div class=&quot;box&quot;&gt;': '<div class="box">',
    "&lt;/div&gt;": "</div>",
}
for _t in _INLINE_TAGS + _BLOCK_TAGS:
    _ALLOWED_HTML["&lt;%s&gt;" % _t] = "<%s>" % _t
    _ALLOWED_HTML["&lt;/%s&gt;" % _t] = "</%s>" % _t

# The generator emits HTML, so it escapes its own special characters: a `<` in code
# becomes `&lt;`, a smart quote becomes `&ldquo;`, an em dash `&mdash;`, etc. _html.escape
# then re-escapes the leading `&` into `&amp;`, so `&ldquo;` becomes `&amp;ldquo;` — which
# renders as the literal text "&ldquo;". Un-double ANY character entity (named like
# &ldquo;/&mdash;, decimal &#8220;, or hex &#x201C;) back to its single-escaped form.
# Safe: a restored entity still renders as a CHARACTER, never a live tag (e.g. `&lt;`
# shows "<", it cannot start markup), so default-deny is preserved. Only `&amp;NAME;` is
# touched — a standalone literal `&amp;` (a real ampersand) and a single-escaped `&lt;`
# from genuinely raw markup are left escaped.
_DOUBLE_ENTITY = _re.compile(r"&amp;(#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")


def sanitize_html(value):
    out = _html.escape(str(value), quote=True)
    for escaped, allowed in _ALLOWED_HTML.items():
        out = out.replace(escaped, allowed)
    out = _DOUBLE_ENTITY.sub(r"&\1;", out)
    return out


COURSE_SYSTEM_PROMPT = (
    "You are an academic advisor conducting an INTAKE INTERVIEW to design a rigorous, personalized "
    "university-level course for a single learner. Understand, in the learner's own words:\n"
    "- their GOAL: what they want to be able to DO afterwards (the real-world transfer), not just "
    "'learn about X';\n"
    "- their BACKGROUND: relevant experience or study;\n"
    "- their PRIOR KNOWLEDGE: probe conversationally which parts of the subject they already know, so "
    "the course starts at the right depth and marks familiar material (this replaces a placement quiz);\n"
    "- their MOTIVATION: why this, why now;\n"
    "- their DESIRED DEPTH: how deep and rigorous they want to go.\n"
    "Ask ONE or TWO focused questions per turn and follow up to probe prior knowledge. Do NOT ask how "
    "much time they have per day or week — the course is self-paced. When you have enough to design a "
    "real program, reply with a brief sentence and then a fenced code block labelled `learnerBrief` "
    "containing ONLY JSON of this shape:\n"
    "```learnerBrief\n"
    '{"goal": "<what they want to be able to DO>", "background": "<their experience, in their words>", '
    '"priorKnowledge": ["<a topic they already know>"], "motivation": "<why>", '
    '"desiredDepth": "<their stated depth preference>"}\n'
    "```\n"
    "Do not emit the learnerBrief block until you have enough. After emitting it the platform builds "
    "the full syllabus — do not list modules or lessons yourself."
)

LESSON_KEYS = (
    "id", "courseId", "topic", "step", "totalSteps",
    "eyebrow", "promptHtml", "hintHtml", "solutionAns", "solutionNote",
)


# ---- Sub-project A: program-backbone schema (Bloom objectives, levels, prereq graph) ----

BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
KNOWLEDGE_DIMS = ("factual", "conceptual", "procedural", "metacognitive")
LEVEL_CODES = ("foundation", "bachelor-y1", "bachelor-y2", "bachelor-y3", "master")
# Non-observable verbs: an objective built on these cannot be measured, so backward design
# forbids them in objective text. Kept as a named list for the prompts; the lint below uses
# word boundaries so "knowledge" does not trip on "know". It deliberately does NOT match the
# "-ing" gerund forms ("learning", "understanding"): those are domain nouns (e.g. "supervised
# learning") that saturate a subject like ML, not the weak objective verb the lint targets.
BANNED_OBJECTIVE_VERBS = ("understand", "know", "learn", "appreciate", "grasp", "be aware", "familiar")
_BANNED_VERB_RE = _re.compile(
    r"\b(understands?|knows?|learns?|appreciates?|grasps?|aware|familiar)\b", _re.I
)


def valid_objective(obj):
    if not isinstance(obj, dict):
        return False
    text = obj.get("text")
    if not (isinstance(text, str) and text.strip()):
        return False
    if _BANNED_VERB_RE.search(text):
        return False
    return obj.get("bloom") in BLOOM_LEVELS and obj.get("knowledge") in KNOWLEDGE_DIMS


def valid_outcomes(items):
    return isinstance(items, list) and len(items) >= 1 and all(valid_objective(o) for o in items)


def valid_prereq_graph(modules):
    """Prereq edges must reference lessons appearing strictly earlier in the flat
    module->lesson order. Earlier-only edges are inherently acyclic, so this single check
    enforces both the DAG and the topological-order requirements."""
    if not isinstance(modules, list):
        return False
    seen = set()
    for module in modules:
        if not isinstance(module, dict):
            return False
        for lesson in module.get("lessons", []):
            if not (isinstance(lesson, dict) and lesson.get("id")):
                return False
            prereqs = lesson.get("prereqs", [])
            if not isinstance(prereqs, list):
                return False
            if any(p not in seen for p in prereqs):  # unknown, self, or forward edge
                return False
            seen.add(lesson["id"])
    return True


def valid_compiled_course(obj):
    if not isinstance(obj, dict) or obj.get("schemaVersion") != 2:
        return False
    if not (isinstance(obj.get("title"), str) and obj["title"].strip()):
        return False
    level = obj.get("level")
    if not (isinstance(level, dict) and level.get("code") in LEVEL_CODES
            and isinstance(level.get("label"), str) and level["label"].strip()):
        return False
    if not (isinstance(obj.get("targetHours"), (int, float)) and obj["targetHours"] > 0):
        return False
    skills = obj.get("skills")
    if not (isinstance(skills, list) and skills and all(isinstance(s, str) and s.strip() for s in skills)):
        return False
    if not valid_outcomes(obj.get("outcomes")):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for module in modules:
        if not (isinstance(module, dict) and module.get("title") and valid_outcomes(module.get("outcomes"))):
            return False
        lessons = module.get("lessons")
        if not (isinstance(lessons, list) and lessons):
            return False
        for lesson in lessons:
            if not (isinstance(lesson, dict) and lesson.get("id") and lesson.get("title")):
                return False
            if not valid_outcomes(lesson.get("objectives")):
                return False
            if not (isinstance(lesson.get("estMinutes"), (int, float)) and lesson["estMinutes"] > 0):
                return False
    return valid_prereq_graph(modules)


def detect_brief(text):
    return claude_client.extract_fenced_json(text, "learnerBrief")


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
    if not valid_check(obj.get("preQuiz")):
        return False
    if not spine.valid_spine_entry(obj.get("spine")):
        return False
    return all(valid_check(c) for c in checks)


SPINE_RECENT = 8


def spine_block(earlier, spine_lessons):
    """Render the 'already covered' prompt block for a lesson at position N.

    earlier: flatten_lessons entries for syllabus positions 1..N-1, in order.
    spine_lessons: the course spine's "lessons" map. The most recent SPINE_RECENT
    lessons get full term definitions; older ones contribute summary + term names
    (bounds prompt growth on long courses). A lesson with no spine entry yet (never
    generated) falls back to its syllabus objectives, marked as planned-only.
    """
    if not earlier:
        return ""
    cutoff = max(0, len(earlier) - SPINE_RECENT)
    lines = []
    for i, meta in enumerate(earlier):
        title = meta.get("title", "")
        entry = spine_lessons.get(meta["id"])
        if isinstance(entry, dict):
            concepts = [c for c in entry.get("concepts", []) if isinstance(c, dict)]
            if i >= cutoff:
                taught = "; ".join(
                    f"{c.get('term', '')} = {c.get('definition', '')}" for c in concepts)
            else:
                terms = ", ".join(c.get("term", "") for c in concepts)
                taught = f"{entry.get('summary', '')} (terms: {terms})"
            lines.append(f'- "{title}" taught: {taught}')
        else:
            objs = "; ".join(
                o.get("text", "") for o in meta.get("objectives", [])
                if isinstance(o, dict) and o.get("text"))
            lines.append(
                f'- "{title}" (planned, not yet studied — assume familiarity at '
                f"objective level only): {objs or 'no stated objectives'}")
    return (
        "\n\nThe learner has ALREADY covered these earlier lessons of this course, "
        "in order:\n" + "\n".join(lines) + "\n"
        "Build directly on that material and do NOT re-teach it — a one-clause "
        "reminder is fine, a re-explanation is not. Reuse the EXACT terms listed "
        "above; never switch to a synonym for a concept an earlier lesson already "
        "named. Where it genuinely helps (at most twice), reference an earlier "
        'lesson by its quoted title, e.g. As you saw in "<lesson title>", ... '
        "Never refer to lessons by number.\n"
    )


def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
                  performance="", directive="", objectives=None, spine_context=""):
    perf_line = f"Learner performance so far: {performance}\n" if performance else ""
    directive_line = f"\n{directive}\n" if directive else ""
    obj_block = ""
    if objectives:
        listed = "; ".join(
            f"{o.get('text', '')} (Bloom: {o.get('bloom', '')})"
            for o in objectives if isinstance(o, dict) and o.get("text")
        )
        if listed:
            obj_block = (
                "\n\nThis lesson must teach to these MEASURABLE learning objectives, and its exercise "
                "AND every concept-check must require the learner to perform each objective's action "
                f"verb (constructive alignment): {listed}.\n"
            )
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
        '  sources: a list of the accredited sources you actually drew on, each {"title","url"} '
        "with the REAL url from your web search (see the grounding note below),\n"
        "  checks: a list of 1-3 concept-check items. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,'
        '"explanation":"<specific, encouraging one-sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact expected answer>",'
        '"explanation":"<specific, encouraging one-sentence why>"}.\n'
        '  preQuiz: ONE warm-up question in the same item format as a check (mcq or fill), '
        "about the lesson's single core idea. The learner answers it BEFORE reading the "
        "lesson, so it must be attemptable with intuition or general prior knowledge — never "
        "require a term, label, or fact that only this lesson introduces. Make mcq "
        "distractors plausible. Its explanation is shown immediately after the attempt as a "
        "one-sentence preview of the key insight.\n"
        "Before emitting, re-answer each mcq check and the preQuiz (if it is mcq) independently "
        "from its question text alone. Confirm the choice at answer is the answer you get, and "
        "that no distractor is also defensibly correct — if one is, rewrite it.\n"
        '  spine: {"summary":"<one plain-text sentence stating what this lesson taught>",'
        '"concepts":[{"term":"<term name>","definition":"<one plain-text sentence>"}]} '
        "with 1-4 concepts. This indexes the lesson so FUTURE lessons can build on it: "
        "name only the concepts THIS lesson introduces, use the EXACT term spelling from "
        "your lesson body, and use NO HTML in any spine field.\n"
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
        "thing to watch, never a bare 'wrong'.\n\n"
        # Self-containment + consistency: the learner is assessed on THIS lesson, so everything the
        # end-questions need must be taught here, in one consistent vocabulary. This is the fix for
        # lessons whose diagram/prose/exercise/solution drifted apart (e.g. a phase called
        # "Slowdown" in the graphic but "early contraction" in the answer).
        "Make the lesson SELF-CONTAINED and internally CONSISTENT — to the standard of an "
        "accredited university:\n"
        "- Every concept-check AND the main exercise must be answerable using ONLY what you teach "
        "in promptHtml. Never require a term, label, phase/step name, formula, or fact the body "
        "did not clearly introduce and explain.\n"
        "- Use ONE consistent set of terms. Whatever you name a concept in the prose, use that "
        "EXACT same name in any diagram or table, in the exercise, in solutionAns, in solutionNote, "
        "and in every check. Do not switch to a synonym or a textbook variant partway through.\n"
        "- Any visual aid must match the prose exactly — same labels, same phases/steps, no "
        "contradiction between what the diagram shows and what the text says.\n\n"
        # Visual aids (#visual-aids): evidence says a visual helps ONLY when it carries
        # structure/process/comparison prose can't; decorative visuals measurably hurt.
        "Add a visual aid ONLY when it shows structure, a process/sequence, or a comparison that "
        "prose alone conveys poorly — never decorative. When one genuinely helps, use exactly one "
        "of these (they are the only visual markup that renders):\n"
        "- A small diagram inside <pre>: use Unicode box-drawing characters (│ ─ ┌ ┐ └ ┘ ├ → ↓) for "
        "boxes/arrows/trees/number-lines. Keep every line <= 32 characters (it renders on a narrow "
        "phone). Good for nesting, flows, and relationships.\n"
        '- A comparison <table> with a header row and AT MOST 3 columns: '
        "<table><thead><tr><th>...</th></tr></thead><tbody><tr><td>...</td></tr></tbody></table>. "
        "Tables and their cells must carry NO attributes.\n"
        '- A short framed aside for a key idea or warning: <div class="callout">...</div> (use it '
        'sparingly), or <div class="box">...</div> for a neutral framed note. Use those EXACT class '
        "strings; no other div/class/attribute will render.\n"
        "Prefer an annotated worked example over an abstract diagram. If in doubt, use prose.\n\n"
        # Phase 2 grounding: teach from real, accredited sources and cite the ones used.
        "Ground this lesson in real, ACCREDITED sources: use web search to consult authoritative "
        "material (university course pages/.edu, official documentation, peer-reviewed papers, "
        "established textbooks), and base your explanation on what you find. In the `sources` field, "
        "list ONLY the specific sources you actually drew on, each with its exact real URL from your "
        "search — never invent or guess a URL. If a claim is contested, prefer the primary source."
        + spine_context + obj_block + directive_line
    )


# ---- #4 answer grading: Claude judges the learner's typed free-text answer ----

_GRADE_VERDICTS = ("correct", "close", "incorrect")


def valid_grade(obj):
    if not isinstance(obj, dict) or obj.get("verdict") not in _GRADE_VERDICTS:
        return False
    note = obj.get("note")
    return isinstance(note, str) and bool(note.strip())


def valid_explain(obj):
    if not valid_grade(obj):
        return False
    follow = obj.get("followUp")
    return isinstance(follow, str) and bool(follow.strip())


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


def explain_prompt(*, prompt_html, solution_ans, solution_note, explanation):
    return (
        "You are a warm, honest tutor. The learner just finished a lesson and is explaining "
        "the core idea back in their own words — the strongest form of retrieval practice. "
        "Judge whether their explanation shows real understanding of the core idea. Judge "
        "understanding, not wording, and do not demand completeness of detail.\n\n"
        f"Lesson body (HTML): {prompt_html}\n"
        f"Reference answer: {solution_ans}\n"
        f"Why it is right: {solution_note}\n"
        f"Learner's explanation: {explanation}\n\n"
        "Decide whether the explanation is correct, close (right idea, a gap or error), or "
        "incorrect. Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"verdict":"correct"|"close"|"incorrect","note":"<one or two encouraging sentences '
        "addressed to 'you': what your explanation captured, then the single most important "
        'idea it missed or got wrong>","followUp":"<ONE short reflective question addressed '
        "to 'you' that targets the weakest point of the explanation and pushes you to justify "
        "or connect it; if the explanation was fully correct, ask a transfer question that "
        'connects the idea to a new situation instead>"}'
    )


def explain_answer(content_dir, course_id, lesson_id, explanation, *, generate):
    lesson = courses.load_lesson(content_dir, course_id, lesson_id)
    if lesson is None:
        return None
    prompt = explain_prompt(
        prompt_html=lesson.get("promptHtml", ""),
        solution_ans=lesson.get("solutionAns", ""),
        solution_note=lesson.get("solutionNote", ""),
        explanation=explanation,
    )
    result = generate(prompt)
    if not isinstance(result, dict):
        raise claude_client.ClaudeError("explain grader returned a non-dict result")
    return {"verdict": result["verdict"], "note": sanitize_html(result["note"]),
            "followUp": sanitize_html(result["followUp"])}


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
        "papers. Use a source NAME, never a URL (the app builds the link). Use only examples so "
        "widely documented you are certain they exist; if unsure of one, choose a more famous "
        "one instead."
    )


def ensure_capstone(content_dir, course_id, scope, profile, *, generate):
    path = Path(content_dir) / course_id / "capstones" / f"{scope}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass  # regenerate a corrupt cache
    with _gen_lock(("capstone", course_id, scope)):
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
        fsutil.write_text_atomic(path, json.dumps(capstone, indent=2, ensure_ascii=False))
        return capstone


# ---- grounded sources / course Library (Phase 1) ----
# The teaching is grounded in REAL sources retrieved via web search. We display a source
# only if the URL the model cites was actually in the captured search results, and we derive
# the source "type" from the domain (reliable) rather than trusting the model. Labels are
# honest, not aspirational: preprint servers (arxiv, biorxiv) and DOI resolvers are labeled
# "preprint" — they are explicitly NOT peer review — while genuine peer-reviewed journal
# venues keep "peer-reviewed".

_SOURCE_TYPE_RANK = ["university", "preprint", "peer-reviewed", "textbook", "official-docs", "reference"]

# Named domains matched on registrable-suffix (host equals the domain, or is a subdomain of
# it) — never on raw substring, so e.g. "summit.org" can never match "mit.edu".
_UNIVERSITY_DOMAINS = ("ethz.ch",)                 # institutions without a generic academic TLD
_UNIVERSITY_LAST_LABELS = ("edu",)                 # bare .edu TLD, e.g. mit.edu, web.mit.edu
_UNIVERSITY_SECOND_LABELS = ("ac", "edu")          # ac.uk, ac.jp, edu.au, edu.sg, ...

_PREPRINT_DOMAINS = ("arxiv.org", "biorxiv.org", "doi.org", "hal.science", "semanticscholar.org")
_PREPRINT_SECOND_LABELS = ("nih",)                 # *.nih.gov — PubMed/PMC: indexes, not journals

_PEER_REVIEWED_DOMAINS = ("acm.org", "ieee.org", "nature.com", "sciencedirect.com",
                           "jstor.org", "plos.org")

_TEXTBOOK_DOMAINS = ("link.springer.com", "springer.com", "oreilly.com", "cambridge.org",
                     "oup.com", "manning.com", "packtpub.com", "wiley.com",
                     "taylorfrancis.com", "mitpress.org")

_OFFICIAL_DOCS_DOMAINS = ("python.org", "pytorch.org", "tensorflow.org", "scikit-learn.org",
                          "developer.mozilla.org", "kubernetes.io", "readthedocs.io",
                          "numpy.org", "pandas.pydata.org")
_OFFICIAL_DOCS_FIRST_LABELS = ("docs", "developer")  # only as the host's FIRST label


def _url_host(url):
    m = _re.match(r"https?://([^/]+)", url.strip(), _re.I)
    return m.group(1).lower() if m else ""


def _host_labels(host):
    return host.split(".") if host else []


def _domain_suffix_match(labels, domains):
    """True if `labels` (a dot-split host) IS or ENDS WITH one of the given registrable
    domains — matched whole-label, so "summit.org" never matches a "mit.*" pattern."""
    for d in domains:
        d_labels = d.split(".")
        if len(labels) >= len(d_labels) and labels[-len(d_labels):] == d_labels:
            return True
    return False


def _first_label_match(labels, first_labels):
    """True only if the host's FIRST label is one of `first_labels` and the host has more
    than one label — e.g. "docs" matches "docs.python.org" but not a bare "docs" host."""
    return len(labels) > 1 and labels[0] in first_labels


def source_type(url):
    host = _url_host(url)
    labels = _host_labels(host)
    if not labels:
        return "reference"
    if (_domain_suffix_match(labels, _UNIVERSITY_DOMAINS)
            or labels[-1] in _UNIVERSITY_LAST_LABELS
            or (len(labels) >= 2 and labels[-2] in _UNIVERSITY_SECOND_LABELS)):
        return "university"
    if (_domain_suffix_match(labels, _PREPRINT_DOMAINS)
            or (len(labels) >= 2 and labels[-2] in _PREPRINT_SECOND_LABELS)):
        return "preprint"
    if _domain_suffix_match(labels, _PEER_REVIEWED_DOMAINS):
        return "peer-reviewed"
    if _domain_suffix_match(labels, _TEXTBOOK_DOMAINS):
        return "textbook"
    if (_domain_suffix_match(labels, _OFFICIAL_DOCS_DOMAINS)
            or _first_label_match(labels, _OFFICIAL_DOCS_FIRST_LABELS)):
        return "official-docs"
    return "reference"


def _norm_url(url):
    u = str(url).strip().lower()
    for p in ("https://", "http://"):
        if u.startswith(p):
            u = u[len(p):]
            break
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def _resolve_sources(cited, captured):
    """Turn the model's cited sources into displayable ones, keeping ONLY those whose URL
    was actually in the captured web-search results (the trust guarantee). Derives the
    accreditation type from the domain and sanitizes the learner-facing text. Deduped."""
    retrieved = {_norm_url(s.get("url", "")) for s in (captured or []) if isinstance(s, dict)}
    out, seen = [], set()
    for s in (cited or []):
        if not isinstance(s, dict):
            continue
        url = s.get("url", "")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            continue
        n = _norm_url(url)
        if n not in retrieved or n in seen:
            continue
        seen.add(n)
        out.append({
            "title": sanitize_html(s.get("title", "")),
            "url": url,
            "type": source_type(url),
            "note": sanitize_html(s["note"]) if isinstance(s.get("note"), str) else "",
        })
    out.sort(key=lambda s: _SOURCE_TYPE_RANK.index(s["type"]))
    return out


def course_lesson_sources(content_dir, course_id):
    """Deduped roll-up of the sources cited across every generated lesson (Phase 2).
    Read live so the course Library reflects lessons as they are generated. Sanitizing is
    already done at store time, but the "type" is ALWAYS recomputed from the URL here (not
    trusted from disk) — cached lesson JSON can predate a source_type() rule change and
    carry a now-stale/legacy type string, so re-deriving it keeps the label honest without
    needing to rewrite the cache."""
    lessons_dir = Path(content_dir) / course_id / "lessons"
    if not lessons_dir.exists():
        return []
    seen = {}
    for f in sorted(lessons_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except ValueError:
            continue
        for s in data.get("sources", []) if isinstance(data, dict) else []:
            if not (isinstance(s, dict) and isinstance(s.get("url"), str)):
                continue
            n = _norm_url(s["url"])
            if n and n not in seen:
                seen[n] = {
                    "title": s.get("title", ""),
                    "url": s["url"],
                    "type": source_type(s["url"]),
                }
    out = list(seen.values())
    out.sort(key=lambda s: _SOURCE_TYPE_RANK.index(s.get("type", "reference")))
    return out


def valid_bibliography(obj):
    if not isinstance(obj, dict):
        return False
    sources = obj.get("sources")
    if not (isinstance(sources, list) and 3 <= len(sources) <= 12):
        return False
    for s in sources:
        if not isinstance(s, dict):
            return False
        if not (isinstance(s.get("title"), str) and s["title"].strip()):
            return False
        if not (isinstance(s.get("note"), str) and s["note"].strip()):
            return False
        url = s.get("url")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            return False
    return True


def bibliography_prompt(*, title, brief, module_titles):
    mods = "; ".join(t for t in module_titles if t)
    return (
        f'You are the librarian for a personal university, compiling the reading list for a '
        f'course titled "{title}".\n'
        f"Course context: {brief}\n"
        f"Modules covered: {mods}\n\n"
        "Use web search to find the most authoritative, ACCREDITED sources on this subject — "
        "university course material (.edu), peer-reviewed papers, official documentation, and "
        "established textbooks. Prefer primary/authoritative sources over blogs. Only include a "
        "source you actually found via search, with its real URL. Reply with ONLY a JSON object, "
        "no prose, no fence:\n"
        '{"sources":[{"title":"<the source title>","url":"<the exact URL from search>",'
        '"note":"<one sentence on what it covers and why it is authoritative>"}]}'
        " Provide 4 to 10 of the best sources."
    )


def _with_refreshed_source_types(library):
    """Recompute each source's "type" from its URL rather than trusting the persisted value.
    A cached library.json can predate a source_type() rule change (e.g. arxiv used to be
    mislabeled "peer-reviewed") — re-deriving at read time keeps the label honest without
    rewriting the cache file on disk."""
    sources = library.get("sources") if isinstance(library, dict) else None
    if isinstance(sources, list):
        library = {**library, "sources": [
            {**s, "type": source_type(s["url"])} if isinstance(s, dict) and isinstance(s.get("url"), str) else s
            for s in sources
        ]}
    return library


def ensure_bibliography(content_dir, course_id, *, generate_sourced):
    path = Path(content_dir) / course_id / "library.json"
    if path.exists():
        try:
            return _with_refreshed_source_types(json.loads(path.read_text()))
        except ValueError:
            pass  # regenerate a corrupt cache
    with _gen_lock(("library", course_id)):
        if path.exists():
            try:
                return _with_refreshed_source_types(json.loads(path.read_text()))
            except ValueError:
                pass  # regenerate a corrupt cache
        manifest = courses.load_manifest(content_dir, course_id)
        if manifest is None:
            return None
        module_titles = [m.get("title", "") for m in manifest.get("modules", [])]
        prompt = bibliography_prompt(
            title=manifest.get("title", ""), brief=manifest.get("brief", ""),
            module_titles=module_titles,
        )
        obj, captured = generate_sourced(prompt)
        if not isinstance(obj, dict):
            raise claude_client.ClaudeError("bibliography generator returned a non-dict result")
        kept = _resolve_sources(obj.get("sources"), captured)
        library = {"courseId": course_id, "title": manifest.get("title", ""), "sources": kept}
        path.parent.mkdir(parents=True, exist_ok=True)
        fsutil.write_text_atomic(path, json.dumps(library, indent=2, ensure_ascii=False))
        return library


def build_chat_prompt(messages, profile):
    lines = [COURSE_SYSTEM_PROMPT, "", f"Learner preferences (JSON): {json.dumps(profile or {})}", ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)


# ---- lesson workspace: a lesson-aware side-chat (no web search) ----

LESSON_CHAT_SYSTEM = (
    "You are a friendly study companion helping a learner while they work through ONE "
    "lesson. They may ask questions or float side-thoughts about the lesson or a genuine "
    "tangent it sparks — answer concisely and clearly, like a knowledgeable tutor. Stay "
    "grounded in the lesson's topic; keep answers focused and short. Do not invent a new "
    "exercise or reveal the solution unless they ask for it. "
    "Mirror the lesson's OWN vocabulary: use the exact terms, labels, and phase/step names that "
    "appear in the lesson text below, even if you know a different textbook name for the same "
    "idea — the learner is being assessed on the lesson's wording, so switching terms confuses "
    "them. If the lesson's framing genuinely differs from standard usage and it matters, lead "
    "with the lesson's term and add the alternative in parentheses, rather than silently "
    "substituting your own. "
    "You can use web search — do so when the question needs current, recent, or factual "
    "information you are unsure of (prices, dates, latest developments); for purely "
    "conceptual questions, just answer directly without searching."
    " When the learner asks for help with the lesson's MAIN EXERCISE and the solution is "
    "not yet revealed, do not hand over the full approach: respond first with ONE short "
    "guiding question or a targeted hint that moves them a single step forward. The moment "
    "they explicitly ask for the direct answer, say they are stuck, or ask a second time, "
    "give it plainly — no gatekeeping, no lecture about how they should learn. Questions "
    "about concepts, background, or tangents get a direct concise answer as always; once "
    "the solution is revealed, discuss it directly."
)

# Socratic co-work: the committed never-reveals alternative to the side-chat's
# give-in-when-asked-twice behavior. The Reveal solution button is the escape hatch.
SOCRATIC_COWORK_SYSTEM = (
    "You are working through the lesson's MAIN EXERCISE with a learner who wants to reach "
    "the solution themselves. You have the reference answer below — NEVER state it, never "
    "lay out the full approach, and never confirm a bare guess as correct until the "
    "learner has explained the reasoning behind it. If they ask you directly for the "
    "answer or say they give up, warmly decline in one sentence, remind them the Reveal "
    "solution button is there if they want out, then offer a smaller step by breaking the "
    "current question into an easier one. Otherwise respond to the learner's LATEST step "
    "only: if it is right, confirm it in a few words and ask the ONE question that moves "
    "them a single step forward; if it is wrong or rests on a misconception, do not "
    "correct it outright — ask a short question or give a tiny concrete example that lets "
    "them see the problem themselves. One question per turn. Keep every turn under 80 "
    "words. Mirror the lesson's OWN vocabulary: use the exact terms, labels, and step "
    "names that appear in the lesson text below. When the learner has stated the complete "
    "solution in their own words, tell them plainly they have it and to type their final "
    "answer into the exercise answer box to check it."
)


def lesson_chat_prompt(lesson, messages, solution_revealed=False, socratic=False):
    revealed_line = ("The learner has already revealed the solution."
                     if solution_revealed
                     else "The learner has NOT yet revealed the solution.")
    ctx = (
        f"Lesson topic: {lesson.get('topic', '')}\n"
        f"Lesson prompt (HTML): {lesson.get('promptHtml', '')}\n"
        f"Reference answer: {lesson.get('solutionAns', '')}\n"
        f"Why it is right: {lesson.get('solutionNote', '')}\n"
    )
    system = SOCRATIC_COWORK_SYSTEM if socratic else LESSON_CHAT_SYSTEM
    lines = [system, "", "The lesson the learner is studying:", ctx,
             revealed_line, ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)


def lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False, socratic=False):
    prompt = lesson_chat_prompt(lesson, messages, solution_revealed=solution_revealed,
                                socratic=socratic)
    try:
        for chunk in stream_fn(prompt):
            yield _sse("delta", chunk)
    except claude_client.ClaudeAuthError:
        yield _sse("error", json.dumps({"message": "Claude needs re-authentication on the Pi — run `claude` there to log in again."}))
        return
    except claude_client.ClaudeError:
        yield _sse("error", json.dumps({"message": "Claude is unavailable right now."}))
        return
    yield _sse("done", "{}")


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
    brief = detect_brief("".join(full))
    if brief is not None:
        yield _sse("brief", json.dumps(brief))
    yield _sse("done", "{}")


# ---- university-grade self-consistency: an audit-first pass reconciles the lesson ----
# A single generation pass can let the diagram, prose, exercise, solution, and end-checks drift
# apart (different names for the same idea; a question that needs a term the body never taught).
# A cheap audit call decides whether the lesson is already consistent; only when it flags a real
# defect do we pay for a full rewrite that reconciles everything to ONE vocabulary and guarantees
# every end-question is answerable from the body. It falls back to the original on any failure, so
# it can only improve a lesson, never break one. Neither call web-searches (it reconciles existing
# content, not facts), so both are cheaper than the sourced generation.

def valid_audit(obj):
    if not isinstance(obj, dict) or not isinstance(obj.get("ok"), bool):
        return False
    if obj["ok"]:
        return True
    return isinstance(obj.get("issues"), list) and len(obj["issues"]) >= 1


def _objective_coverage_rule(objectives):
    rule = (
        "OBJECTIVE COVERAGE: the lesson body must teach enough for the learner to perform "
        "each stated objective's action verb. Flag any objective the body does not actually "
        "teach to."
    )
    if objectives:
        listed = "; ".join(
            o.get("text", "") for o in objectives if isinstance(o, dict) and o.get("text")
        )
        if listed:
            rule += f" Objectives: {listed}."
    return rule


def lesson_audit_prompt(lesson, objectives=None):
    return (
        "You are a meticulous course editor checking ONE generated lesson for internal "
        "consistency, to the standard of an accredited university. Here is the lesson as JSON:\n"
        f"{json.dumps(lesson, ensure_ascii=False)}\n\n"
        "Check it against these four rules:\n"
        "1. SELF-CONTAINED: every concept-check AND the main exercise is answerable using ONLY "
        "what the lesson body (promptHtml) actually teaches — no term, label, phase/step name, "
        "formula, or fact is required that the body did not introduce and explain.\n"
        "2. CONSISTENT TERMINOLOGY: the same concept is called by the EXACT same name everywhere "
        "— in the prose, any diagram or table, the exercise, solutionAns, solutionNote, and every "
        "check. No synonyms, no switching to a textbook variant partway through.\n"
        "3. VISUAL AID MATCHES PROSE: any <pre> diagram or <table> agrees with the surrounding "
        "text — same labels, same structure, no contradictions.\n"
        f"4. {_objective_coverage_rule(objectives)}\n"
        "Reply with ONLY a JSON object, no prose, no code fence. If the lesson fully satisfies all "
        'four rules, reply exactly {"ok": true}. Otherwise reply '
        '{"ok": false, "issues": ["<each specific inconsistency, quoting the mismatched terms>"]}.'
    )


def lesson_review_prompt(lesson, issues=None, objectives=None):
    issues_block = ""
    if issues:
        joined = "; ".join(str(i) for i in issues)
        issues_block = f"\nA reviewer already flagged these specific problems to fix: {joined}\n"
    return (
        "You are a meticulous course editor doing the final quality check on ONE generated "
        "lesson, to the standard of an accredited university. Here is the lesson as JSON:\n"
        f"{json.dumps(lesson, ensure_ascii=False)}\n"
        f"{issues_block}\n"
        "Audit it against these rules and return a CORRECTED version that satisfies ALL of them:\n"
        "1. SELF-CONTAINED: every concept-check AND the main exercise must be answerable using "
        "ONLY what the lesson body (promptHtml) actually teaches. If any question relies on a "
        "term, label, phase/step name, formula, or fact the body does not clearly introduce and "
        "explain, fix it — either add the missing explanation to promptHtml, or adjust the "
        "question — so nothing is required that was not taught.\n"
        "2. CONSISTENT TERMINOLOGY: use ONE consistent set of terms everywhere. Whatever a concept "
        "is named in the prose must be the EXACT same name used in any diagram or table, in the "
        "exercise, in solutionAns, in solutionNote, and in every check — no synonyms, no switching "
        "to a textbook variant partway through. (For example, a diagram labelling a phase "
        "'Slowdown' while the solution calls it 'early contraction' is a defect: pick one name and "
        "use it everywhere.)\n"
        "3. VISUAL AID MATCHES PROSE: any <pre> diagram or <table> must agree with the surrounding "
        "text — same labels, same structure, no contradictions.\n"
        f"4. {_objective_coverage_rule(objectives)}\n"
        "Do NOT invent new facts, do NOT change the underlying subject matter, and do NOT change "
        "the `sources`. Keep exactly the same JSON keys and shape. Change only what is needed to "
        "satisfy the rules; if the lesson already satisfies them, return it unchanged.\n"
        "Reply with ONLY the corrected JSON object, no prose, no code fence."
    )


def _reviewed_lesson(lesson, verify_generate, objectives=None):
    """Audit-first self-consistency pass. A cheap audit call decides whether the lesson is
    already consistent; only if it flags a real defect do we pay for the full rewrite. Returns
    the reconciled lesson, or the original unchanged if the audit clears it, errors, or the
    rewrite fails validation — verification must never make a lesson worse. Citations are carried
    through verbatim; the reviewer is told not to touch them, and we enforce it here.

    verify_generate(prompt, validate) forwards to a plain structured (non-web) generation.
    objectives (optional) lets the audit/review rules check objective coverage; omitted callers
    still get the general rule text with no specific objective list."""
    try:
        audit = verify_generate(lesson_audit_prompt(lesson, objectives), valid_audit)
    except claude_client.ClaudeError:
        return lesson  # fail open: never block a lesson on a flaky audit
    if isinstance(audit, tuple):
        audit = audit[0]
    if not (isinstance(audit, dict) and audit.get("ok") is False):
        return lesson  # already consistent (ok:true) or unparseable — trust the generated lesson
    issues = audit.get("issues") if isinstance(audit.get("issues"), list) else []
    original_sources = lesson.get("sources")
    try:
        reviewed = verify_generate(lesson_review_prompt(lesson, issues, objectives), valid_lesson)
    except claude_client.ClaudeError:
        return lesson
    if isinstance(reviewed, tuple):
        reviewed = reviewed[0]
    if not (isinstance(reviewed, dict) and valid_lesson(reviewed)):
        return lesson
    reviewed["sources"] = original_sources
    return reviewed


def _generate_and_store_lesson(content_dir, course_id, lesson_id, profile, *, generate,
                               performance="", directive="", verify_generate=None):
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
    spine_data = spine.load_spine(content_dir, course_id)
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
        objectives=meta.get("objectives"),
        spine_context=spine_block(flat[:position - 1], spine_data["lessons"]),
    )
    result = generate(prompt)
    # Phase 2: a sourced generator returns (lesson, captured_web_sources); a plain one
    # returns just the lesson dict. Accept both.
    lesson, captured = result if isinstance(result, tuple) else (result, [])
    if not isinstance(lesson, dict):
        raise claude_client.ClaudeError("generator returned a non-dict result")
    # University-grade self-consistency review: reconcile terminology across prose/diagram/
    # exercise/solution/checks and ensure every end-question is answerable from the body.
    if verify_generate is not None:
        lesson = _reviewed_lesson(lesson, verify_generate, objectives=meta.get("objectives"))
    lesson["id"] = lesson_id
    lesson["courseId"] = course_id
    lesson["step"] = position
    lesson["totalSteps"] = len(flat)
    # Keep only the cited sources whose URL was really retrieved (trust guarantee).
    lesson["sources"] = _resolve_sources(lesson.get("sources"), captured)
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
    pq = lesson.get("preQuiz")
    if isinstance(pq, dict):
        for f in ("prompt", "explanation"):
            if isinstance(pq.get(f), str):
                pq[f] = sanitize_html(pq[f])
        if isinstance(pq.get("choices"), list):
            pq["choices"] = [sanitize_html(c) if isinstance(c, str) else c for c in pq["choices"]]
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    # The spine entry is generation-side state, not lesson content: pop it before
    # caching so lesson files keep their existing shape, then record it for future
    # lessons. The per-course lock serializes concurrent read-modify-writes of
    # spine.json (the per-lesson lock alone does not).
    spine_entry = lesson.pop("spine")
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    fsutil.write_text_atomic(path, json.dumps(lesson, indent=2, ensure_ascii=False))
    with _gen_lock(("spine", course_id)):
        spine.upsert_entry(content_dir, course_id, lesson_id, spine_entry)
    return lesson


def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance="",
                  verify_generate=None):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    with _gen_lock(("lesson", course_id, lesson_id)):
        existing = courses.load_lesson(content_dir, course_id, lesson_id)
        if existing is not None:
            return existing  # a concurrent request generated it while we waited
        return _generate_and_store_lesson(
            content_dir, course_id, lesson_id, profile, generate=generate,
            performance=performance, verify_generate=verify_generate,
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


def deepen_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance="",
                  verify_generate=None):
    return _generate_and_store_lesson(
        content_dir, course_id, lesson_id, profile, generate=generate,
        performance=performance, directive=_DEEPEN_DIRECTIVE, verify_generate=verify_generate,
    )
