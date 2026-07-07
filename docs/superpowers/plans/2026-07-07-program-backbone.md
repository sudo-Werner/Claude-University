# Program Backbone (Sub-Project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn course creation into a rigorous program-design flow — an intake interview that emits a structured learner brief, a staged web-grounded compiler that produces a Bloom-tagged, prerequisite-graphed, level-declared syllabus, a review screen before committing, and a migration that retrofits the four existing courses to the same shape.

**Architecture:** A new intake system prompt emits a fenced `learnerBrief` block. A new `backend/compiler.py` turns that brief into a compiled course through four staged calls (grounded outline → objectives + prereq graph → web-grounded accuracy sweep → contract assembly). Grounded stages use `run_sourced` (web search + the `_resolve_sources` trust guarantee); structured stages use `run_structured`. The compiled shape is additive over today's `course.json` (`schemaVersion: 2`); legacy courses still load. New lesson generation is extended to receive each lesson's objectives for constructive alignment.

**Tech Stack:** Python 3 / Flask / SQLite backend (`.venv/bin/pytest`), plain ES-module frontend (`node --test frontend/tests/*.test.js`), Claude via the Pi's `claude -p` CLI (`run_sourced`, `run_structured`).

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec.

- **Enums (exact):** `bloom` ∈ {remember, understand, apply, analyze, evaluate, create}. `knowledge` ∈ {factual, conceptual, procedural, metacognitive}. `level.code` ∈ {foundation, bachelor-y1, bachelor-y2, bachelor-y3, master}.
- **Objective shape:** `{text, bloom, knowledge}`. `text` centers on an observable action verb and must NOT contain the banned non-measurable verbs: understand, know, learn, appreciate, grasp, "be aware/familiar".
- **Prereq graph:** `prereqs` are earlier lesson IDs only (reference a lesson appearing strictly earlier in flat module→lesson order); earlier-only ⟹ acyclic.
- **`schemaVersion: 2`** marks a compiled course. All new fields are additive; a legacy `course.json` (no `schemaVersion`) must still load and render.
- **`targetHours` = `round(Σ estMinutes / 60)`** — a declared scope target, NOT realized effort. Framed as "estimated total effort," never "you have done N of 130 hours."
- **Source trust guarantee:** every web-grounded stage keeps only sources whose URL was really retrieved — always pass model-cited sources through `generation._resolve_sources(cited, captured)`. Never trust a model-supplied URL directly.
- **Audit-first, never-worse:** the accuracy sweep runs a cheap `{ok, issues}` audit and only rewrites flagged parts; on audit-clean, any error, or a failed re-validation it returns the input UNCHANGED. Verification can only improve, never break.
- **Self-paced / time-neutral:** never ask the learner how much time they have per day or week; `estMinutes`/`targetHours` size the outline, they are not a daily-time tracker.
- **Migration is additive and ID-preserving:** enrichment never adds/removes/reorders/renames modules or lessons and never changes an ID — study progress is keyed on lesson IDs and must survive. Atomic writes; one course failing does not abort the batch.
- **Route errors match existing generation routes:** `ClaudeAuthError` → 503 with `{"error": "...", "code": "reauth"}`; `ClaudeError` → 502.
- **Test commands:** backend `.venv/bin/pytest`; frontend `node --test frontend/tests/*.test.js` (never `node --test frontend/` — the bare directory fails).
- **Never commit to git unless Werner explicitly asks.** (The commit steps below stage changes and write a message, but do not run `git commit` unless Werner has said to.)

---

### Task 1: Objective schema constants + objective/outcome validators

**Files:**
- Modify: `backend/generation.py` (add after `LESSON_KEYS`, before `detect_proposal`)
- Test: `tests/test_generation.py`

**Interfaces:**
- Produces: `BLOOM_LEVELS`, `KNOWLEDGE_DIMS`, `LEVEL_CODES` (tuples of str); `BANNED_OBJECTIVE_VERBS` (tuple of str); `valid_objective(obj) -> bool`; `valid_outcomes(items) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generation.py
from backend import generation

def test_valid_objective_accepts_action_verb_and_tags():
    assert generation.valid_objective(
        {"text": "Calculate the gradient of a loss function", "bloom": "apply", "knowledge": "procedural"})

def test_valid_objective_rejects_banned_verbs():
    for bad in ("Understand recursion", "Know the four phases", "Learn about markets",
                "Appreciate the design", "Be aware of the risks", "Grasp the concept"):
        assert not generation.valid_objective({"text": bad, "bloom": "understand", "knowledge": "conceptual"})

def test_valid_objective_allows_knowledge_word_not_matching_know():
    # "knowledge" must NOT trip the \bknow\b lint (word-boundary, not substring)
    assert generation.valid_objective(
        {"text": "Analyze a knowledge-representation scheme", "bloom": "analyze", "knowledge": "conceptual"})

def test_valid_objective_rejects_bad_tags():
    assert not generation.valid_objective({"text": "Derive Bayes' rule", "bloom": "prove", "knowledge": "conceptual"})
    assert not generation.valid_objective({"text": "Derive Bayes' rule", "bloom": "apply", "knowledge": "meta"})
    assert not generation.valid_objective({"text": "", "bloom": "apply", "knowledge": "procedural"})

def test_valid_outcomes_requires_nonempty_list_of_objectives():
    assert generation.valid_outcomes([{"text": "Compare two models", "bloom": "analyze", "knowledge": "conceptual"}])
    assert not generation.valid_outcomes([])
    assert not generation.valid_outcomes("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k "objective or outcomes" -v`
Expected: FAIL with `AttributeError: module 'backend.generation' has no attribute 'valid_objective'`

- [ ] **Step 3: Write minimal implementation**

Add near the top of `backend/generation.py` (the module already imports `re as _re`):

```python
# ---- Sub-project A: program-backbone schema (Bloom objectives, levels, prereq graph) ----

BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
KNOWLEDGE_DIMS = ("factual", "conceptual", "procedural", "metacognitive")
LEVEL_CODES = ("foundation", "bachelor-y1", "bachelor-y2", "bachelor-y3", "master")
# Non-observable verbs: an objective built on these cannot be measured, so backward design
# forbids them in objective text. Kept as a named list for the prompts; the lint below uses
# word boundaries so "knowledge" does not trip on "know".
BANNED_OBJECTIVE_VERBS = ("understand", "know", "learn", "appreciate", "grasp", "be aware", "familiar")
_BANNED_VERB_RE = _re.compile(
    r"\b(understand(?:ing|s)?|knows?|learn(?:ing|s)?|appreciates?|grasps?|aware|familiar)\b", _re.I
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -k "objective or outcomes" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(A): Bloom objective + outcome validators with banned-verb lint"
```

---

### Task 2: Prerequisite-graph + compiled-course validators

**Files:**
- Modify: `backend/generation.py` (add directly after `valid_outcomes`)
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `valid_objective`, `valid_outcomes`, `LEVEL_CODES` (Task 1).
- Produces: `valid_prereq_graph(modules) -> bool` (modules is the manifest's module list); `valid_compiled_course(obj) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generation.py
OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def _mods_with_prereqs(edges):
    # edges: {lessonId: [prereqIds]} over lessons l1,l2,l3 in one module
    return [{"id": "m1", "title": "M", "outcomes": [OBJ],
             "lessons": [{"id": lid, "title": lid, "objectives": [OBJ], "estMinutes": 60,
                          "prereqs": edges.get(lid, [])} for lid in ("l1", "l2", "l3")]}]

def test_valid_prereq_graph_accepts_earlier_only_dag():
    assert generation.valid_prereq_graph(_mods_with_prereqs({"l2": ["l1"], "l3": ["l1", "l2"]}))

def test_valid_prereq_graph_rejects_forward_edge():
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l1": ["l2"]}))

def test_valid_prereq_graph_rejects_self_and_unknown_edge():
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l2": ["l2"]}))
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l3": ["l9"]}))

def _compiled():
    return {"schemaVersion": 2, "title": "T", "subtitle": "",
            "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
            "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ],
            "groundingSources": [], "modules": _mods_with_prereqs({"l2": ["l1"]})}

def test_valid_compiled_course_accepts_full_shape():
    assert generation.valid_compiled_course(_compiled())

def test_valid_compiled_course_rejects_missing_pieces():
    c = _compiled(); c.pop("outcomes"); assert not generation.valid_compiled_course(c)
    c = _compiled(); c["level"] = {"code": "phd", "label": "x"}; assert not generation.valid_compiled_course(c)
    c = _compiled(); c["schemaVersion"] = 1; assert not generation.valid_compiled_course(c)
    c = _compiled(); c["modules"][0]["lessons"][0].pop("objectives"); assert not generation.valid_compiled_course(c)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k "prereq or compiled" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'valid_prereq_graph'`

- [ ] **Step 3: Write minimal implementation**

Add after `valid_outcomes` in `backend/generation.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -k "prereq or compiled" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(A): prereq-graph + compiled-course whole-schema validators"
```

---

### Task 3: Intake interview prompt + learnerBrief detection + brief SSE event

**Files:**
- Modify: `backend/generation.py` (`COURSE_SYSTEM_PROMPT`, add `detect_brief`, `chat_sse`)
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `claude_client.extract_fenced_json`, `_sse` (existing).
- Produces: rewritten `COURSE_SYSTEM_PROMPT` (str); `detect_brief(text) -> dict | None`; `chat_sse` now emits a `brief` SSE event (replacing `proposal`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generation.py
def test_detect_brief_parses_fenced_block():
    text = ('Great, here is your brief.\n```learnerBrief\n'
            '{"goal":"build ML models","background":"python dev","priorKnowledge":["python"],'
            '"motivation":"career","desiredDepth":"deep"}\n```')
    brief = generation.detect_brief(text)
    assert brief["goal"] == "build ML models" and brief["priorKnowledge"] == ["python"]

def test_detect_brief_ignores_prose():
    assert generation.detect_brief("just a normal chat reply, no block") is None

def test_chat_sse_emits_brief_event():
    brief_json = ('```learnerBrief\n{"goal":"g","background":"b","priorKnowledge":[],'
                  '"motivation":"m","desiredDepth":"d"}\n```')
    def fake_stream(prompt):
        yield brief_json
    frames = "".join(generation.chat_sse([{"role": "user", "content": "hi"}], None, stream_fn=fake_stream))
    assert "event: brief" in frames and '"goal": "g"' in frames
    assert "event: proposal" not in frames
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k "brief or chat_sse" -v`
Expected: FAIL — `detect_brief` missing; `chat_sse` emits `proposal` not `brief`.

- [ ] **Step 3: Write minimal implementation**

Replace `COURSE_SYSTEM_PROMPT` (lines ~61-79) with:

```python
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
```

Add beside `detect_proposal`:

```python
def detect_brief(text):
    return claude_client.extract_fenced_json(text, "learnerBrief")
```

In `chat_sse`, replace the proposal tail (the `proposal = detect_proposal(...)` block) with:

```python
    brief = detect_brief("".join(full))
    if brief is not None:
        yield _sse("brief", json.dumps(brief))
    yield _sse("done", "{}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -k "brief or chat_sse" -v`
Expected: PASS (3 tests). Then run the whole file to catch any old proposal-based `chat_sse` test: `.venv/bin/pytest tests/test_generation.py -v` — if a test asserts `event: proposal` from `chat_sse`, update it to assert `event: brief` (the intake now emits a brief, not a course proposal).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(A): intake-interview prompt emits learnerBrief; chat_sse brief event"
```

---

### Task 4: Compiler stage 1 — grounded outline

**Files:**
- Create: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `generation.LEVEL_CODES`, `generation._resolve_sources`, `claude_client.ClaudeError`.
- Produces: `valid_outline(obj) -> bool`; `_outline_prompt(learner_brief) -> str`; `_grounded_outline(learner_brief, *, generate_sourced) -> (outline_dict, sources_list)`. `generate_sourced(prompt, validate) -> (obj, captured_sources)`.

**Testing note (fakes used across Tasks 4–8):** stages receive injected generators. In tests:
```python
def sourced(result, captured=None):
    return lambda prompt, validate: (result, captured or [])
def verify_ok(result):
    return lambda prompt, validate: result
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compiler.py
from backend import compiler, generation, claude_client  # generation/claude_client used by later tasks

OUTLINE = {"title": "Intro ML", "subtitle": "hands-on",
           "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
           "targetHours": 130, "groundingSources": [{"title": "MIT 6.036", "url": "https://mit.edu/6036"}],
           "modules": [{"id": "m1", "title": "Basics",
                        "lessons": [{"id": "l1", "title": "Vectors", "estMinutes": 90}]}]}

def test_valid_outline_accepts_and_rejects():
    assert compiler.valid_outline(OUTLINE)
    bad = {**OUTLINE, "level": {"code": "phd", "label": "x"}}
    assert not compiler.valid_outline(bad)
    bad2 = {**OUTLINE, "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "l1", "title": "t", "estMinutes": 0}]}]}
    assert not compiler.valid_outline(bad2)

def test_grounded_outline_keeps_only_retrieved_sources():
    captured = [{"title": "MIT 6.036", "url": "https://mit.edu/6036"}]
    gen = lambda prompt, validate: (OUTLINE, captured)
    outline, sources = compiler._grounded_outline({"goal": "build models"}, generate_sourced=gen)
    assert outline["title"] == "Intro ML"
    assert [s["url"] for s in sources] == ["https://mit.edu/6036"]  # trust guarantee kept it

def test_grounded_outline_drops_uncaptured_source():
    gen = lambda prompt, validate: (OUTLINE, [])  # nothing actually retrieved
    _, sources = compiler._grounded_outline({"goal": "g"}, generate_sourced=gen)
    assert sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.compiler'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/compiler.py`:

```python
"""Staged, web-grounded course compiler (sub-project A). Turns a learner brief into a
compiled, Bloom-tagged, prerequisite-graphed syllabus. Grounded stages (outline, accuracy
sweep) use run_sourced + generation._resolve_sources (only real retrieved URLs survive);
structured stages (objectives/graph) use run_structured. Each stage validates its output."""
import json

from backend import claude_client, generation


def valid_outline(obj):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("title"), str) and obj["title"].strip()):
        return False
    level = obj.get("level")
    if not (isinstance(level, dict) and level.get("code") in generation.LEVEL_CODES
            and isinstance(level.get("label"), str) and level["label"].strip()):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and isinstance(m.get("title"), str) and m["title"].strip()):
            return False
        lessons = m.get("lessons")
        if not (isinstance(lessons, list) and lessons):
            return False
        for l in lessons:
            if not (isinstance(l, dict) and isinstance(l.get("id"), str) and l["id"]):
                return False
            if not (isinstance(l.get("title"), str) and l["title"].strip()):
                return False
            if not (isinstance(l.get("estMinutes"), (int, float)) and l["estMinutes"] > 0):
                return False
    return True


def _outline_prompt(learner_brief):
    return (
        "You are a university curriculum designer. Using web search, consult CANONICAL sources for "
        "this subject — university syllabi (.edu), established textbooks, and professional-society "
        "curricula — and design a course OUTLINE grounded in what a real course at the appropriate "
        "level covers.\n"
        f"Learner brief (JSON): {json.dumps(learner_brief, ensure_ascii=False)}\n\n"
        "Decide the DEPTH LEVEL from the learner's goal, background, and desired depth. Choose exactly "
        "one level code from: foundation, bachelor-y1, bachelor-y2, bachelor-y3, master. Size the "
        "outline to a real course at that level: enough modules and lessons, each lesson carrying an "
        "estimated total effort in minutes (estMinutes = reading + practice + review), so the whole "
        "course plausibly totals 125-150 hours. Give each lesson a stable id 'l1','l2',... in reading "
        "order and each module an id 'm1','m2',.... List ONLY grounding sources whose URL you actually "
        "retrieved via search.\n"
        "Reply with ONLY a JSON object, no prose, no code fence:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "bachelor-y2", "label": "Bachelor '
        'Year 2-equivalent"}, "targetHours": 130, "groundingSources": [{"title": "...", "url": '
        '"https://..."}], "modules": [{"id": "m1", "title": "...", "lessons": [{"id": "l1", '
        '"title": "...", "estMinutes": 90}]}]}'
    )


def _grounded_outline(learner_brief, *, generate_sourced):
    obj, captured = generate_sourced(_outline_prompt(learner_brief), valid_outline)
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    return obj, sources
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compiler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(A): compiler stage 1 — web-grounded outline with source trust guarantee"
```

---

### Task 5: Compiler stage 2 — objectives + prerequisite graph (with positional merge)

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `_grounded_outline` output shape; `generation.valid_outcomes`, `generation.valid_prereq_graph`.
- Produces: `valid_objectives_result(obj) -> bool`; `_objectives_prompt(outline) -> str`; `_objectives_and_graph(outline, *, verify) -> result_dict`; `_merge_objectives(outline, result) -> enriched_dict`. `enriched_dict` = `{outcomes, skills, modules:[{id,title,outcomes,lessons:[{id,title,estMinutes,objectives,prereqs}]}]}` with the outline's ids/titles/estMinutes authoritative and prereqs remapped earlier-only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compiler.py
OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def test_merge_objectives_keeps_outline_ids_and_filters_forward_prereqs():
    outline = {"modules": [{"id": "m1", "title": "Basics", "lessons": [
        {"id": "l1", "title": "Vectors", "estMinutes": 90},
        {"id": "l2", "title": "Matrices", "estMinutes": 60}]}]}
    # model echoed DIFFERENT ids and a forward edge; merge must fix both by position
    result = {"outcomes": [OBJ], "skills": ["do X"], "modules": [{"id": "x", "title": "renamed",
        "outcomes": [OBJ], "lessons": [
            {"id": "a", "title": "?", "objectives": [OBJ], "prereqs": ["b"]},   # forward -> dropped
            {"id": "b", "title": "?", "objectives": [OBJ], "prereqs": ["a"]}]}]}  # a==l1 -> l1
    enriched = compiler._merge_objectives(outline, result)
    lessons = enriched["modules"][0]["lessons"]
    assert [l["id"] for l in lessons] == ["l1", "l2"]           # outline ids win
    assert lessons[0]["prereqs"] == []                           # forward edge filtered
    assert lessons[1]["prereqs"] == ["l1"]                       # remapped a->l1
    assert enriched["modules"][0]["title"] == "Basics"          # outline title wins
    assert generation.valid_prereq_graph(enriched["modules"])

def test_objectives_and_graph_passes_result_through_verify():
    outline = {"modules": [{"id": "m1", "title": "M", "lessons": [{"id": "l1", "title": "t", "estMinutes": 60}]}]}
    result = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
        "outcomes": [OBJ], "lessons": [{"id": "l1", "title": "t", "objectives": [OBJ], "prereqs": []}]}]}
    got = compiler._objectives_and_graph(outline, verify=lambda p, v: result)
    assert got is result and compiler.valid_objectives_result(got)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -k "objectives or merge" -v`
Expected: FAIL — `_merge_objectives` / `valid_objectives_result` missing.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/compiler.py`:

```python
def valid_objectives_result(obj):
    if not isinstance(obj, dict):
        return False
    if not generation.valid_outcomes(obj.get("outcomes")):
        return False
    skills = obj.get("skills")
    if not (isinstance(skills, list) and skills and all(isinstance(s, str) and s.strip() for s in skills)):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and generation.valid_outcomes(m.get("outcomes"))):
            return False
        for l in m.get("lessons", []):
            if not (isinstance(l, dict) and l.get("id") and generation.valid_outcomes(l.get("objectives"))):
                return False
    return generation.valid_prereq_graph(modules)


def _objectives_prompt(outline):
    return (
        "You are designing learning objectives and a prerequisite graph using BACKWARD DESIGN. Here "
        "is the grounded outline as JSON:\n"
        f"{json.dumps(outline, ensure_ascii=False)}\n\n"
        "For EACH lesson write 1-3 MEASURABLE objectives. Every objective centers on an observable "
        "action verb and is tagged with a Bloom level (remember, understand, apply, analyze, evaluate, "
        "create) and a knowledge dimension (factual, conceptual, procedural, metacognitive). NEVER use "
        "'understand', 'know', 'learn', 'appreciate', 'grasp', 'be aware/familiar' in objective text — "
        "use verbs like calculate, derive, compare, implement, critique, design. Roll lesson objectives "
        "up into 1-3 outcomes per module and 3-6 course-level outcomes. For each lesson set 'prereqs' to "
        "the ids of EARLIER lessons it directly builds on (may be empty; a prereq MUST appear earlier in "
        "reading order). List the concrete SKILLS the learner can do by the end. Preserve every module "
        "and lesson id, title, and estMinutes EXACTLY.\n"
        "Reply with ONLY a JSON object, no prose, no code fence:\n"
        '{"outcomes": [{"text": "...", "bloom": "analyze", "knowledge": "conceptual"}], "skills": '
        '["..."], "modules": [{"id": "m1", "title": "...", "outcomes": [{"text": "...", "bloom": '
        '"apply", "knowledge": "procedural"}], "lessons": [{"id": "l1", "title": "...", "objectives": '
        '[{"text": "Calculate ...", "bloom": "apply", "knowledge": "procedural"}], "prereqs": []}]}]}'
    )


def _objectives_and_graph(outline, *, verify):
    return verify(_objectives_prompt(outline), valid_objectives_result)


def _merge_objectives(outline, result):
    """Graft the objectives result onto the outline BY POSITION: the outline's ids, titles, and
    estMinutes always win (the model is told to preserve them, but we enforce it), and prereqs are
    remapped from the result's lesson ids to the outline's and filtered to earlier-only/known edges.
    Guarantees a valid prereq graph for both new-course compile and existing-course enrich."""
    out_lessons = [l for m in outline.get("modules", []) for l in m.get("lessons", [])]
    res_lessons = [l for m in result.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict)]
    id_map = {r.get("id"): o.get("id") for r, o in zip(res_lessons, out_lessons)}
    res_modules = result.get("modules", [])
    seen, modules = set(), []
    for mi, m in enumerate(outline.get("modules", [])):
        rm = res_modules[mi] if mi < len(res_modules) and isinstance(res_modules[mi], dict) else {}
        r_lessons = rm.get("lessons", []) if isinstance(rm.get("lessons"), list) else []
        lessons = []
        for li, l in enumerate(m.get("lessons", [])):
            rl = r_lessons[li] if li < len(r_lessons) and isinstance(r_lessons[li], dict) else {}
            raw = rl.get("prereqs", []) if isinstance(rl.get("prereqs"), list) else []
            prereqs = [id_map.get(p, p) for p in raw]
            prereqs = [p for p in prereqs if p in seen]  # earlier-only + known
            lessons.append({
                "id": l.get("id"), "title": l.get("title"), "estMinutes": l.get("estMinutes"),
                "objectives": rl.get("objectives", []) if isinstance(rl.get("objectives"), list) else [],
                "prereqs": prereqs,
            })
            seen.add(l.get("id"))
        modules.append({
            "id": m.get("id"), "title": m.get("title"),
            "outcomes": rm.get("outcomes", []) if isinstance(rm.get("outcomes"), list) else [],
            "lessons": lessons,
        })
    return {"outcomes": result.get("outcomes", []), "skills": result.get("skills", []), "modules": modules}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compiler.py -k "objectives or merge" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(A): compiler stage 2 — objectives, outcomes, prereq graph + positional merge"
```

---

### Task 6: Compiler stage 3 — web-grounded accuracy sweep (audit-first)

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `generation.valid_audit`, `valid_objectives_result`, `claude_client.ClaudeError`.
- Produces: `_sweep_audit_prompt(enriched, grounding_sources) -> str`; `_sweep_correct_prompt(enriched, issues) -> str`; `_accuracy_sweep(enriched, grounding_sources, *, generate_sourced) -> enriched_dict`. Returns the input unchanged on audit-clean / error / failed re-validation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compiler.py
ENRICHED = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
    "outcomes": [OBJ], "lessons": [{"id": "l1", "title": "t", "estMinutes": 60, "objectives": [OBJ], "prereqs": []}]}]}

def test_accuracy_sweep_unchanged_when_audit_clean():
    gen = lambda prompt, validate: ({"ok": True}, [])
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen) == ENRICHED

def test_accuracy_sweep_applies_correction_when_flagged():
    corrected = {"outcomes": [OBJ], "skills": ["s2"], "modules": ENRICHED["modules"]}
    calls = iter([({"ok": False, "issues": ["topic X is wrong"]}, []), (corrected, [])])
    gen = lambda prompt, validate: next(calls)
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen)["skills"] == ["s2"]

def test_accuracy_sweep_falls_back_on_invalid_correction():
    bad = {"outcomes": [], "skills": [], "modules": []}  # fails valid_objectives_result
    calls = iter([({"ok": False, "issues": ["x"]}, []), (bad, [])])
    gen = lambda prompt, validate: next(calls)
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen) == ENRICHED

def test_accuracy_sweep_falls_back_on_error():
    def boom(prompt, validate):
        raise claude_client.ClaudeError("down")
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=boom) == ENRICHED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -k sweep -v`
Expected: FAIL — `_accuracy_sweep` missing.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/compiler.py`:

```python
def _sweep_audit_prompt(enriched, grounding_sources):
    return (
        "You are a subject-matter expert auditing a course's outline and objectives for ACCURACY "
        "against canonical sources. Use web search to verify. Course as JSON:\n"
        f"{json.dumps(enriched, ensure_ascii=False)}\n"
        f"Grounding sources: {json.dumps(grounding_sources, ensure_ascii=False)}\n\n"
        "Are the topics correct and current, the ordering sound, the objectives accurate and correctly "
        "leveled, with no glaring omissions for a course at this level? Reply with ONLY a JSON object, "
        'no prose, no fence. If it is sound, reply exactly {"ok": true}. Otherwise '
        '{"ok": false, "issues": ["<each specific inaccuracy or omission>"]}.'
    )


def _sweep_correct_prompt(enriched, issues):
    joined = "; ".join(str(i) for i in issues)
    return (
        "You are a subject-matter expert correcting a course's outline and objectives. Use web search "
        "to ground corrections in canonical sources. Course as JSON:\n"
        f"{json.dumps(enriched, ensure_ascii=False)}\n"
        f"A reviewer flagged these problems to fix: {joined}\n\n"
        "Return a CORRECTED version with the SAME JSON shape and the SAME module/lesson ids. Fix only "
        "what is needed for accuracy; keep objectives measurable and Bloom-tagged; keep prereqs "
        "earlier-only. Reply with ONLY the corrected JSON object, no prose, no code fence:\n"
        '{"outcomes": [...], "skills": [...], "modules": [...]}'
    )


def _accuracy_sweep(enriched, grounding_sources, *, generate_sourced):
    """Web-grounded, audit-first accuracy pass. Cheap audit against the sources; rewrite only the
    flagged parts. Returns the enriched course UNCHANGED if the audit clears it, anything errors, or
    the correction fails re-validation — the sweep can only improve accuracy, never make it worse."""
    try:
        audit, _ = generate_sourced(_sweep_audit_prompt(enriched, grounding_sources), generation.valid_audit)
    except claude_client.ClaudeError:
        return enriched
    if not (isinstance(audit, dict) and audit.get("ok") is False):
        return enriched  # clean or unparseable -> trust the input
    issues = audit.get("issues") if isinstance(audit.get("issues"), list) else []
    try:
        corrected, _ = generate_sourced(_sweep_correct_prompt(enriched, issues), valid_objectives_result)
    except claude_client.ClaudeError:
        return enriched
    return corrected if valid_objectives_result(corrected) else enriched
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compiler.py -k sweep -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(A): compiler stage 3 — audit-first web-grounded accuracy sweep"
```

---

### Task 7: Compiler stage 4 — contract assembly + `compile_course` orchestration

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `_grounded_outline`, `_objectives_and_graph`, `_merge_objectives`, `_accuracy_sweep`.
- Produces: `_brief_paragraph(learner_brief, level) -> str`; `_assemble_contract(learner_brief, outline, enriched, grounding_sources) -> compiled_dict`; `compile_course(learner_brief, *, generate_sourced, verify) -> compiled_dict`. Compiled dict has `schemaVersion: 2`, no `id` (assigned at write time), `targetHours = round(Σ estMinutes / 60)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compiler.py
def test_assemble_contract_computes_hours_and_shape():
    outline = {"title": "Intro ML", "subtitle": "s",
               "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
               "modules": [{"id": "m1", "title": "M", "lessons": [
                   {"id": "l1", "title": "a", "estMinutes": 90},
                   {"id": "l2", "title": "b", "estMinutes": 150}]}]}
    enriched = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
        "outcomes": [OBJ], "lessons": [
            {"id": "l1", "title": "a", "estMinutes": 90, "objectives": [OBJ], "prereqs": []},
            {"id": "l2", "title": "b", "estMinutes": 150, "objectives": [OBJ], "prereqs": ["l1"]}]}]}
    c = compiler._assemble_contract({"goal": "build models", "desiredDepth": "deep"}, outline, enriched, [])
    assert c["schemaVersion"] == 2 and c["targetHours"] == 4          # round(240/60)
    assert "id" not in c and c["level"]["code"] == "bachelor-y2"
    assert generation.valid_compiled_course(c)
    assert "build models" in c["brief"]

def test_compile_course_runs_all_stages():
    outline = {"title": "Intro ML", "subtitle": "s",
               "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
               "groundingSources": [{"title": "MIT", "url": "https://mit.edu/x"}],
               "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "l1", "title": "a", "estMinutes": 120}]}]}
    obj_result = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
        "outcomes": [OBJ], "lessons": [{"id": "l1", "title": "a", "objectives": [OBJ], "prereqs": []}]}]}
    captured = [{"title": "MIT", "url": "https://mit.edu/x"}]
    sourced_calls = iter([(outline, captured), ({"ok": True}, [])])  # outline, then sweep-audit
    gen_sourced = lambda p, v: next(sourced_calls)
    c = compiler.compile_course({"goal": "build"}, generate_sourced=gen_sourced, verify=lambda p, v: obj_result)
    assert generation.valid_compiled_course(c)
    assert c["targetHours"] == 2 and [s["url"] for s in c["groundingSources"]] == ["https://mit.edu/x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -k "assemble or compile_course" -v`
Expected: FAIL — `_assemble_contract` / `compile_course` missing.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/compiler.py`:

```python
def _brief_paragraph(learner_brief, level):
    goal = (learner_brief.get("goal") or "").strip()
    depth = (learner_brief.get("desiredDepth") or "").strip()
    background = (learner_brief.get("background") or "").strip()
    parts = []
    if goal:
        parts.append(f"The learner wants to be able to {goal}")
    parts.append(f"Pitch the material at {level.get('label', 'the declared level')}")
    if depth:
        parts.append(f"desired depth: {depth}")
    if background:
        parts.append(f"background: {background}")
    return ". ".join(parts) + "."


def _assemble_contract(learner_brief, outline, enriched, grounding_sources):
    # estMinutes is authoritative from the outline (objectives stage may not echo it); overlay it
    # onto the enriched lessons by id so the compiled course carries per-lesson estMinutes.
    est = {l["id"]: l.get("estMinutes", 0)
           for m in outline.get("modules", []) for l in m.get("lessons", [])}
    modules = []
    for m in enriched.get("modules", []):
        lessons = [{**l, "estMinutes": est.get(l.get("id"), l.get("estMinutes", 0))}
                   for l in m.get("lessons", [])]
        modules.append({**m, "lessons": lessons})
    total_minutes = sum(est.values())
    level = outline.get("level", {})
    return {
        "schemaVersion": 2,
        "title": outline.get("title", ""),
        "subtitle": outline.get("subtitle", ""),
        "brief": _brief_paragraph(learner_brief, level),
        "learnerBrief": learner_brief,
        "level": level,
        "targetHours": round(total_minutes / 60) or 1,
        "skills": enriched.get("skills", []),
        "outcomes": enriched.get("outcomes", []),
        "groundingSources": grounding_sources,
        "modules": modules,
    }


def compile_course(learner_brief, *, generate_sourced, verify):
    outline, sources = _grounded_outline(learner_brief, generate_sourced=generate_sourced)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    swept = _accuracy_sweep(enriched, sources, generate_sourced=generate_sourced)
    return _assemble_contract(learner_brief, outline, swept, sources)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compiler.py -k "assemble or compile_course" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(A): compiler stage 4 — contract assembly + compile_course orchestration"
```

---

### Task 8: `enrich_course` — the ID-preserving migration path

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `valid_outline`, `_objectives_and_graph`, `_merge_objectives`, `_accuracy_sweep`, `_assemble_contract`.
- Produces: `_brief_from_manifest(manifest) -> dict`; `_enrich_outline_prompt(manifest) -> str`; `_grounded_outline_for_existing(manifest, *, generate_sourced) -> (outline, sources)`; `enrich_course(existing_manifest, *, generate_sourced, verify) -> compiled_dict` with `id` == the manifest's id and every existing lesson id/order preserved.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compiler.py
LEGACY = {"id": "the-human-body", "title": "The Human Body", "subtitle": "engineer's view",
          "brief": "systems view of anatomy", "modules": [
              {"id": "m1", "title": "Cardio", "lessons": [
                  {"id": "the-human-body-l1", "title": "The Heart"},
                  {"id": "the-human-body-l2", "title": "Blood"}]}]}

def _enrich_gens():
    # 1st sourced call = enrich outline (model may echo junk ids; we ignore them);
    # 2nd sourced call = sweep audit -> clean
    outline_reply = {"title": "x", "subtitle": "y",
                     "level": {"code": "bachelor-y1", "label": "Bachelor Year 1-equivalent"},
                     "groundingSources": [], "modules": [{"id": "zz", "title": "zz", "lessons": [
                         {"id": "junk1", "title": "junk", "estMinutes": 80},
                         {"id": "junk2", "title": "junk", "estMinutes": 100}]}]}
    sourced = iter([(outline_reply, []), ({"ok": True}, [])])
    obj_result = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "Cardio",
        "outcomes": [OBJ], "lessons": [
            {"id": "the-human-body-l1", "title": "The Heart", "objectives": [OBJ], "prereqs": []},
            {"id": "the-human-body-l2", "title": "Blood", "objectives": [OBJ], "prereqs": ["the-human-body-l1"]}]}]}
    return (lambda p, v: next(sourced)), (lambda p, v: obj_result)

def test_enrich_course_preserves_ids_order_and_id():
    gs, vf = _enrich_gens()
    c = compiler.enrich_course(LEGACY, generate_sourced=gs, verify=vf)
    assert c["id"] == "the-human-body"
    flat = [l["id"] for m in c["modules"] for l in m["lessons"]]
    assert flat == ["the-human-body-l1", "the-human-body-l2"]     # existing ids + order preserved
    assert c["level"]["code"] == "bachelor-y1"
    assert generation.valid_compiled_course(c)

def test_enrich_course_is_idempotent_on_ids():
    gs, vf = _enrich_gens()
    once = compiler.enrich_course(LEGACY, generate_sourced=gs, verify=vf)
    gs2, vf2 = _enrich_gens()
    twice = compiler.enrich_course(once, generate_sourced=gs2, verify=vf2)
    assert [l["id"] for m in twice["modules"] for l in m["lessons"]] == \
           [l["id"] for m in once["modules"] for l in m["lessons"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -k enrich -v`
Expected: FAIL — `enrich_course` missing.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/compiler.py`:

```python
def _brief_from_manifest(manifest):
    return {"goal": manifest.get("brief", ""), "background": "", "priorKnowledge": [],
            "motivation": "", "desiredDepth": ""}


def _enrich_outline_prompt(manifest):
    skeleton = {"title": manifest.get("title", ""), "subtitle": manifest.get("subtitle", ""),
                "modules": [{"id": m.get("id"), "title": m.get("title"),
                             "lessons": [{"id": l.get("id"), "title": l.get("title")}
                                         for l in m.get("lessons", [])]}
                            for m in manifest.get("modules", [])]}
    return (
        "You are retrofitting rigor onto an EXISTING course WITHOUT changing its structure. Using web "
        "search, consult canonical sources for the subject. Existing outline:\n"
        f"{json.dumps(skeleton, ensure_ascii=False)}\n\n"
        "Do NOT add, remove, reorder, or rename any module or lesson, and keep every id EXACTLY. Decide "
        "the appropriate level code (foundation, bachelor-y1, bachelor-y2, bachelor-y3, master) from the "
        "material, add an estimated total effort in minutes (estMinutes) to each existing lesson, and "
        "list the real grounding sources you used. Reply with ONLY a JSON object, no prose, no fence, "
        "echoing every id and title unchanged:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "...", "label": "..."}, '
        '"groundingSources": [{"title": "...", "url": "..."}], "modules": [{"id": "m1", "title": "...", '
        '"lessons": [{"id": "...", "title": "...", "estMinutes": 90}]}]}'
    )


def _grounded_outline_for_existing(manifest, *, generate_sourced):
    """Migration outline: rebuild the outline from the EXISTING manifest structure (ids, titles, and
    order preserved regardless of what the model echoes), taking only the level and per-lesson
    estMinutes from the grounded reply. Guarantees progress-critical ids survive."""
    obj, captured = generate_sourced(_enrich_outline_prompt(manifest), valid_outline)
    est = {l["id"]: l.get("estMinutes", 60)
           for m in obj.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict) and l.get("id")}
    # position-based fallback when the model did not echo the real ids
    reply_flat = [l for m in obj.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict)]
    existing_flat = [l for m in manifest.get("modules", []) for l in m.get("lessons", [])]
    for pos, l in enumerate(existing_flat):
        if l["id"] not in est and pos < len(reply_flat):
            est[l["id"]] = reply_flat[pos].get("estMinutes", 60)
    outline = {
        "title": manifest.get("title", ""), "subtitle": manifest.get("subtitle", ""),
        "level": obj.get("level", {}),
        "modules": [{"id": m.get("id"), "title": m.get("title"),
                     "lessons": [{"id": l.get("id"), "title": l.get("title"),
                                  "estMinutes": est.get(l.get("id"), 60)} for l in m.get("lessons", [])]}
                    for m in manifest.get("modules", [])],
    }
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    return outline, sources


def enrich_course(existing_manifest, *, generate_sourced, verify):
    outline, sources = _grounded_outline_for_existing(existing_manifest, generate_sourced=generate_sourced)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    swept = _accuracy_sweep(enriched, sources, generate_sourced=generate_sourced)
    compiled = _assemble_contract(_brief_from_manifest(existing_manifest), outline, swept, sources)
    compiled["id"] = existing_manifest["id"]
    return compiled
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_compiler.py -k enrich -v`
Expected: PASS (2 tests). Then run the full compiler suite: `.venv/bin/pytest tests/test_compiler.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(A): enrich_course — ID-preserving migration path for existing courses"
```

---

### Task 9: `write_course` persists the compiled shape (back-compatible)

**Files:**
- Modify: `backend/courses.py` (`write_course`)
- Test: `tests/test_courses.py`

**Interfaces:**
- Consumes: a compiled course dict (Task 7) whose lessons carry `l1..lN` ids + `objectives`/`prereqs`/`estMinutes`, plus top-level `schemaVersion`/`level`/`targetHours`/`skills`/`outcomes`/`groundingSources`/`learnerBrief`.
- Produces: `write_course(content_dir, proposal)` that slugs ids, remaps prereqs to slugged ids, and copies rich fields through. A legacy proposal (`{title, modules:[{title, lessons:[{title}]}]}`) still writes exactly as before.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_courses.py
from backend import courses

def test_write_course_legacy_shape_unchanged(tmp_path):
    m = courses.write_course(tmp_path, {"title": "Old Way", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L1"}, {"title": "L2"}]}]})
    assert m["id"] == "old-way"
    assert [l["id"] for l in m["modules"][0]["lessons"]] == ["old-way-l1", "old-way-l2"]
    assert "schemaVersion" not in m

def test_write_course_compiled_shape_slugs_ids_and_remaps_prereqs(tmp_path):
    OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
    compiled = {"schemaVersion": 2, "title": "Deep ML", "subtitle": "s", "brief": "b",
        "learnerBrief": {"goal": "g"}, "level": {"code": "master", "label": "Master-equivalent"},
        "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ], "groundingSources": [],
        "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
            {"id": "l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []},
            {"id": "l2", "title": "B", "estMinutes": 60, "objectives": [OBJ], "prereqs": ["l1"]}]}]}
    m = courses.write_course(tmp_path, compiled)
    assert m["schemaVersion"] == 2 and m["level"]["code"] == "master" and m["targetHours"] == 130
    lessons = m["modules"][0]["lessons"]
    assert [l["id"] for l in lessons] == ["deep-ml-l1", "deep-ml-l2"]
    assert lessons[1]["prereqs"] == ["deep-ml-l1"]                 # prereq remapped to slugged id
    assert lessons[0]["objectives"] == [OBJ] and lessons[0]["estMinutes"] == 90
    # persisted file matches the returned manifest
    import json
    on_disk = json.loads((tmp_path / "deep-ml" / "course.json").read_text())
    assert on_disk == m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_courses.py -k write_course -v`
Expected: FAIL — compiled fields dropped; prereqs not remapped.

- [ ] **Step 3: Write minimal implementation**

Replace `write_course` in `backend/courses.py` with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_courses.py -k write_course -v`
Expected: PASS (2 tests). Then the full file: `.venv/bin/pytest tests/test_courses.py -v` (confirms `load_manifest` already tolerates schemaVersion 2 — it is a plain `json.loads`, so no change needed).

- [ ] **Step 5: Commit**

```bash
git add backend/courses.py tests/test_courses.py
git commit -m "feat(A): write_course persists compiled schema, remaps prereqs, stays back-compatible"
```

---

### Task 10: Routes — `POST /api/courses/compile` (+ verify `POST /api/courses` accepts compiled)

**Files:**
- Modify: `backend/app.py` (import `compiler`; add compile route)
- Test: `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `compiler.compile_course`, `generation.valid_compiled_course`, `courses.write_course`.
- Produces: `POST /api/courses/compile` — body `{learnerBrief}` → `{course}` (200, NOT saved) or 400/502/503. `POST /api/courses` unchanged in code; a compiled body writes via `write_course`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_courses_api.py
from backend import app as app_module, claude_client, compiler, courses

OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
COMPILED = {"schemaVersion": 2, "title": "Deep ML", "subtitle": "s", "brief": "b",
    "learnerBrief": {"goal": "g"}, "level": {"code": "master", "label": "Master-equivalent"},
    "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ], "groundingSources": [],
    "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ],
                 "lessons": [{"id": "l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []}]}]}

def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path)
    app = app_module.create_app(db_path=str(tmp_path / "t.db"))
    return app.test_client()

def test_compile_returns_proposed_course_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler, "compile_course", lambda brief, **kw: COMPILED)
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses/compile", json={"learnerBrief": {"goal": "build models"}})
    assert resp.status_code == 200
    assert resp.get_json()["course"]["level"]["code"] == "master"
    assert not (tmp_path / "deep-ml").exists()                     # NOT saved

def test_compile_requires_goal(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/courses/compile", json={"learnerBrief": {}}).status_code == 400

def test_compile_maps_claude_errors(tmp_path, monkeypatch):
    def boom(brief, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(compiler, "compile_course", boom)
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/courses/compile", json={"learnerBrief": {"goal": "g"}})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"

def test_post_courses_writes_compiled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/courses", json=COMPILED)
    assert resp.status_code == 201
    assert resp.get_json()["course"]["schemaVersion"] == 2
    assert (tmp_path / "deep-ml" / "course.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_courses_api.py -k "compile or writes_compiled" -v`
Expected: FAIL — no `/api/courses/compile` route (404).

- [ ] **Step 3: Write minimal implementation**

In `backend/app.py`, add `compiler` to the import line:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler
```

Add this route directly after `post_course` (the existing `POST /api/courses`):

```python
    @app.post("/api/courses/compile")
    def post_course_compile():
        body = request.get_json(silent=True) or {}
        brief = body.get("learnerBrief")
        if not isinstance(brief, dict) or not brief.get("goal"):
            return jsonify({"error": "learnerBrief with a goal is required"}), 400
        # Grounded stages web-search; structured stages don't — same wiring as lessons.
        generate_sourced = lambda prompt, validate: claude_client.run_sourced(prompt, validate=validate)
        verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        try:
            compiled = compiler.compile_course(brief, generate_sourced=generate_sourced, verify=verify)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "couldn't build your program, try again"}), 502
        if not generation.valid_compiled_course(compiled):
            return jsonify({"error": "couldn't build your program, try again"}), 502
        return jsonify({"course": compiled})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_courses_api.py -k "compile or writes_compiled" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(A): POST /api/courses/compile route (proposes unsaved compiled course)"
```

---

### Task 11: New lessons receive their objectives (constructive alignment)

**Files:**
- Modify: `backend/courses.py` (`flatten_lessons`), `backend/generation.py` (`lesson_prompt`, `_generate_and_store_lesson`)
- Test: `tests/test_courses.py`, `tests/test_generation.py`

**Interfaces:**
- Consumes: manifest lessons that may carry `objectives` (Task 9).
- Produces: `flatten_lessons` entries gain an `objectives` key (empty list for legacy). `lesson_prompt(..., objectives=None)` appends a constructive-alignment block when objectives are present. `_generate_and_store_lesson` passes `objectives=meta.get("objectives")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_courses.py
def test_flatten_lessons_includes_objectives():
    OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
    manifest = {"modules": [{"id": "m1", "title": "M", "lessons": [
        {"id": "c-l1", "title": "A", "objectives": [OBJ]}, {"id": "c-l2", "title": "B"}]}]}
    flat = courses.flatten_lessons(manifest)
    assert flat[0]["objectives"] == [OBJ] and flat[1]["objectives"] == []
```

```python
# tests/test_generation.py
def test_lesson_prompt_includes_objectives_alignment():
    p = generation.lesson_prompt(brief="b", profile=None, lesson_id="c-l1", lesson_title="A",
        module_title="M", position=1, total=3,
        objectives=[{"text": "Calculate the mean", "bloom": "apply", "knowledge": "procedural"}])
    assert "Calculate the mean" in p and "constructive alignment" in p

def test_lesson_prompt_omits_block_without_objectives():
    p = generation.lesson_prompt(brief="b", profile=None, lesson_id="c-l1", lesson_title="A",
        module_title="M", position=1, total=3)
    assert "constructive alignment" not in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_courses.py::test_flatten_lessons_includes_objectives tests/test_generation.py -k "alignment or without_objectives" -v`
Expected: FAIL — no `objectives` key; `lesson_prompt` has no `objectives` param.

- [ ] **Step 3: Write minimal implementation**

In `backend/courses.py`, `flatten_lessons`, add the objectives key:

```python
            out.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "moduleTitle": module["title"],
                "objectives": lesson.get("objectives", []),
            })
```

In `backend/generation.py`, extend `lesson_prompt`'s signature and body. Change the signature to add `objectives=None`:

```python
def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
                  performance="", directive="", objectives=None):
```

Build the block near the top of the function (beside `directive_line`):

```python
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
```

Append `obj_block` to the returned prompt — change the final `+ directive_line` to `+ obj_block + directive_line`.

In `_generate_and_store_lesson`, pass the objectives from the manifest meta into the prompt call (the loop already binds `meta`):

```python
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
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_courses.py -k flatten tests/test_generation.py -k "alignment or without_objectives" -v`
Expected: PASS (3 tests). Then the full backend suite to confirm nothing regressed: `.venv/bin/pytest`

- [ ] **Step 5: Commit**

```bash
git add backend/courses.py backend/generation.py tests/test_courses.py tests/test_generation.py
git commit -m "feat(A): new lessons receive their Bloom objectives for constructive alignment"
```

---

### Task 12: One-off migration script for the four existing courses

**Files:**
- Create: `backend/migrate_courses.py`
- Test: `tests/test_migrate_courses.py`

**Interfaces:**
- Consumes: `compiler.enrich_course`, `generation.valid_compiled_course`, `claude_client.run_sourced`/`run_structured`.
- Produces: `migrate(content_dir=courses.CONTENT_DIR) -> {"enriched": int, "clean": int, "errors": int}`; atomic-writes each enriched `course.json`; skips already-`schemaVersion:2` courses; one failure never aborts the batch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_courses.py
import json
from backend import migrate_courses, compiler, generation

OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def _write(dirp, cid, manifest):
    (dirp / cid).mkdir(parents=True)
    (dirp / cid / "course.json").write_text(json.dumps(manifest))

def test_migrate_enriches_legacy_and_skips_current(tmp_path, monkeypatch):
    _write(tmp_path, "legacy", {"id": "legacy", "title": "Legacy", "subtitle": "", "brief": "b",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "legacy-l1", "title": "A"}]}]})
    _write(tmp_path, "current", {"id": "current", "schemaVersion": 2, "title": "Cur", "modules": []})

    def fake_enrich(manifest, **kw):
        return {"schemaVersion": 2, "id": manifest["id"], "title": manifest["title"], "subtitle": "",
                "brief": "b", "learnerBrief": {"goal": "g"},
                "level": {"code": "bachelor-y1", "label": "Bachelor Year 1-equivalent"},
                "targetHours": 120, "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": "legacy-l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []}]}]}
    monkeypatch.setattr(compiler, "enrich_course", fake_enrich)

    result = migrate_courses.migrate(tmp_path)
    assert result == {"enriched": 1, "clean": 1, "errors": 0}
    on_disk = json.loads((tmp_path / "legacy" / "course.json").read_text())
    assert on_disk["schemaVersion"] == 2 and on_disk["id"] == "legacy"
    assert generation.valid_compiled_course(on_disk)

def test_migrate_one_failure_does_not_abort_batch(tmp_path, monkeypatch):
    _write(tmp_path, "aaa", {"id": "aaa", "title": "A", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "aaa-l1", "title": "x"}]}]})
    _write(tmp_path, "bbb", {"id": "bbb", "title": "B", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "bbb-l1", "title": "y"}]}]})
    def flaky(manifest, **kw):
        if manifest["id"] == "aaa":
            raise RuntimeError("boom")
        return {"schemaVersion": 2, "id": "bbb", "title": "B", "subtitle": "", "brief": "b",
                "learnerBrief": {"goal": "g"}, "level": {"code": "foundation", "label": "Foundation"},
                "targetHours": 100, "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": "bbb-l1", "title": "y", "estMinutes": 60, "objectives": [OBJ], "prereqs": []}]}]}
    monkeypatch.setattr(compiler, "enrich_course", flaky)
    result = migrate_courses.migrate(tmp_path)
    assert result == {"enriched": 1, "clean": 0, "errors": 1}
    assert json.loads((tmp_path / "bbb" / "course.json").read_text())["schemaVersion"] == 2
    assert "schemaVersion" not in json.loads((tmp_path / "aaa" / "course.json").read_text())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_migrate_courses.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.migrate_courses'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/migrate_courses.py`:

```python
"""One-off migration: retrofit schemaVersion-2 rigor (level, hours, Bloom objectives,
prerequisite graph, grounding sources) onto existing courses, preserving lesson ids, order,
and study progress (progress is keyed on lesson ids in the DB, so preserving ids preserves it).
Run when the service is quiet (no in-flight generation). Re-runnable: already-v2 courses are
skipped. Usage: python -m backend.migrate_courses"""
import json
import sys
from pathlib import Path

from backend import claude_client, compiler, courses, generation


def _atomic_write(path, data):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def migrate(content_dir=courses.CONTENT_DIR):
    content_dir = Path(content_dir)
    generate_sourced = lambda prompt, validate: claude_client.run_sourced(prompt, validate=validate)
    verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
    enriched = clean = errors = 0
    for child in sorted(content_dir.iterdir()):
        manifest_path = child / "course.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schemaVersion") == 2:
            print(f"skip  {child.name}: already schemaVersion 2")
            clean += 1
            continue
        try:
            compiled = compiler.enrich_course(manifest, generate_sourced=generate_sourced, verify=verify)
        except Exception as exc:  # one course failing must not abort the batch
            print(f"ERROR {child.name}: {exc}")
            errors += 1
            continue
        if not (generation.valid_compiled_course(compiled) and compiled.get("id") == manifest.get("id")):
            print(f"ERROR {child.name}: enrichment failed validation")
            errors += 1
            continue
        _atomic_write(manifest_path, compiled)
        lessons = sum(len(m.get("lessons", [])) for m in compiled["modules"])
        print(f"OK    {child.name}: level={compiled['level']['code']} "
              f"hours={compiled['targetHours']} lessons={lessons}")
        enriched += 1
    print(f"\ndone: {enriched} enriched, {clean} already-current, {errors} errors")
    return {"enriched": enriched, "clean": clean, "errors": errors}


if __name__ == "__main__":
    migrate()
    sys.exit(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_migrate_courses.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/migrate_courses.py tests/test_migrate_courses.py
git commit -m "feat(A): one-off migration script enriches existing courses (atomic, id-preserving)"
```

**Deploy-time note (run by the controller, NOT in tests):** the real migration runs on the Pi against `/home/werner/claude_university/content/courses/` while the service is quiet. Before running it: confirm no generation is in flight (`pgrep -af "claude -p"` is empty), back up the four `course.json` files, run `python -m backend.migrate_courses`, then verify each course still loads and its lesson ids/progress are intact. This is an operational step in the deploy phase, not part of the code tasks.

---

### Task 13: Frontend — intake emits brief, compile call, staged loading

**Files:**
- Modify: `frontend/src/chat.js` (`streamChat` dispatches `brief`), `frontend/src/courses.js` (`compileProgram`), `frontend/src/views/loading.js` (`PROGRAM_STAGES`), `frontend/src/app.js` (chat flow)
- Test: `frontend/tests/chat.test.js`, `frontend/tests/courses.test.js`

**Interfaces:**
- Consumes: SSE `brief` event from `chat_sse` (Task 3); `POST /api/courses/compile` (Task 10).
- Produces: `streamChat({..., onBrief})` calls `onBrief(JSON.parse(data))` on a `brief` frame. `compileProgram({fetch, learnerBrief}) -> course | {error}`. `PROGRAM_STAGES` (array of status strings). `app.js` chat flow: brief → "Build my program" button → compile (loading) → syllabus review.

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/tests/chat.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { streamChat } from "../src/chat.js";

function fakeFetchSSE(frames) {
  const body = frames.map((f) => `event: ${f.event}\ndata: ${f.data}\n\n`).join("");
  const bytes = new TextEncoder().encode(body);
  return async () => ({
    body: { getReader: () => { let done = false;
      return { read: async () => done ? { done: true } : (done = true, { value: bytes, done: false }) }; } },
  });
}

test("streamChat dispatches brief event to onBrief", async () => {
  let brief = null;
  await streamChat({
    fetch: fakeFetchSSE([{ event: "brief", data: JSON.stringify({ goal: "build models" }) }, { event: "done", data: "{}" }]),
    messages: [], onDelta() {}, onBrief: (b) => { brief = b; }, onDone() {}, onError() {},
  });
  assert.equal(brief.goal, "build models");
});
```

```javascript
// frontend/tests/courses.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { compileProgram } from "../src/courses.js";

test("compileProgram posts the brief and returns the proposed course", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ course: { title: "Deep ML", level: { code: "master" } } }) }; };
  const course = await compileProgram({ fetch, learnerBrief: { goal: "g" } });
  assert.equal(sent.url, "/api/courses/compile");
  assert.deepEqual(sent.body, { learnerBrief: { goal: "g" } });
  assert.equal(course.level.code, "master");
});

test("compileProgram returns an error object on failure", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "couldn't build your program, try again" }) });
  const r = await compileProgram({ fetch, learnerBrief: { goal: "g" } });
  assert.ok(r.error);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/chat.test.js frontend/tests/courses.test.js`
Expected: FAIL — `onBrief` not dispatched; `compileProgram` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/chat.js`, change `streamChat`'s destructured params and event dispatch. Replace the signature `{ fetch, messages, endpoint = "/api/courses/chat", onDelta, onProposal, onDone, onError }` with `{ fetch, messages, endpoint = "/api/courses/chat", onDelta, onBrief, onDone, onError }`, and replace the proposal branch:

```javascript
      if (event === "delta") onDelta(data);
      else if (event === "brief") { if (onBrief) onBrief(JSON.parse(data)); }
      else if (event === "done") onDone();
      else if (event === "error") { if (onError) onError(JSON.parse(data)); }
```

In `frontend/src/courses.js`, append:

```javascript
export async function compileProgram({ fetch, learnerBrief }) {
  const resp = await fetch("/api/courses/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ learnerBrief }),
  });
  if (!resp.ok) {
    let message = "Couldn't build your program right now. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  const body = await resp.json();
  return body.course;
}
```

In `frontend/src/views/loading.js`, add:

```javascript
export const PROGRAM_STAGES = [
  "Reading your brief…",
  "Searching canonical sources…",
  "Designing modules and lessons…",
  "Writing measurable objectives…",
  "Fact-checking against the sources…",
  "Assembling your syllabus…",
];
```

In `frontend/src/app.js`:
- Update the import from loading to include `PROGRAM_STAGES`: `import { loadingHTML, LESSON_STAGES, DEEPEN_STAGES, CAPSTONE_STAGES, PROGRAM_STAGES } from "./views/loading.js";`
- Update the import from courses to include `compileProgram`.
- In `showChat`, change the state to `ui.chat = { messages: [], brief: null, pending: false };`.
- In `paintChat`, replace the `if (ui.chat.proposal)` block with a brief block that offers "Build my program":

```javascript
    if (ui.chat.brief) {
      const card = doc.createElement("div");
      card.className = "card proposal";
      card.innerHTML =
        `<div class="eyebrow">READY TO BUILD</div>` +
        `<h2 class="session-topic">Your learning brief is ready</h2>` +
        `<div class="session-sub">${esc(ui.chat.brief.goal || "")}</div>` +
        `<button class="btn-primary" data-action="build-program">Build my program</button>`;
      view.querySelector(".chat-thread").appendChild(card);
      card.querySelector('[data-action="build-program"]').addEventListener("click", buildProgram);
    }
```

- In `sendChat`, change the stream callback `onProposal: (p) => { ui.chat.proposal = p; }` to `onBrief: (b) => { ui.chat.brief = b; }`.
- Replace `createFromProposal` with `buildProgram` (compile → syllabus review, added in Task 14):

```javascript
  async function buildProgram() {
    pauseTimer();
    ui.screen = "compiling";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showChat);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", PROGRAM_STAGES);
    const course = await compileProgram({ fetch, learnerBrief: ui.chat.brief });
    if (ui.screen !== "compiling") return;
    if (!course || course.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((course && course.error) || "Couldn't build your program.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showChat);
      return;
    }
    showSyllabus(course);   // defined in Task 14
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/chat.test.js frontend/tests/courses.test.js`
Expected: PASS. If any existing test references `onProposal`, update it to `onBrief`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/chat.js frontend/src/courses.js frontend/src/views/loading.js frontend/src/app.js frontend/tests/chat.test.js frontend/tests/courses.test.js
git commit -m "feat(A): intake emits brief, compileProgram call, staged compile loading screen"
```

---

### Task 14: Frontend — syllabus-review screen + course-contract display

**Files:**
- Create: `frontend/src/views/syllabus.js`
- Modify: `frontend/src/app.js` (`showSyllabus`), `frontend/src/views/dashboard.js` (contract block)
- Test: `frontend/tests/views.test.js`

**Interfaces:**
- Consumes: the compiled course from `buildProgram` (Task 13); `createCourse` (existing).
- Produces: `syllabusHTML(course) -> string` rendering level badge, ~hours, skills, course outcomes, grounding sources, modules→lessons with objectives, and Accept / Request-changes buttons (`data-action="accept-syllabus"` / `"revise-syllabus"`). `dashboardHTML` shows a contract block when `data.contract` is present. `app.js` `showSyllabus(course)`: Accept → `createCourse({fetch, proposal: course})` → `openCourse`; Request-changes → `showChat`.

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/tests/views.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { syllabusHTML } from "../src/views/syllabus.js";

const OBJ = { text: "Calculate the gradient", bloom: "apply", knowledge: "procedural" };
const COURSE = {
  title: "Intro ML", subtitle: "hands-on",
  level: { code: "bachelor-y2", label: "Bachelor Year 2-equivalent" },
  targetHours: 130, skills: ["train a model", "evaluate a model"],
  outcomes: [{ text: "Compare two models", bloom: "analyze", knowledge: "conceptual" }],
  groundingSources: [{ title: "MIT 6.036", url: "https://mit.edu/6036", type: "university" }],
  modules: [{ id: "m1", title: "Foundations", outcomes: [OBJ],
    lessons: [{ id: "l1", title: "Vectors", estMinutes: 90, objectives: [OBJ], prereqs: [] }] }],
};

test("syllabusHTML renders level, hours, skills, objectives, and sources", () => {
  const html = syllabusHTML(COURSE);
  assert.ok(html.includes("Bachelor Year 2-equivalent"));
  assert.ok(html.includes("130"));                          // estimated total effort
  assert.ok(html.includes("train a model"));
  assert.ok(html.includes("Calculate the gradient"));       // a lesson objective
  assert.ok(html.includes("MIT 6.036"));
  assert.ok(html.includes('data-action="accept-syllabus"'));
  assert.ok(html.includes('data-action="revise-syllabus"'));
});

test("syllabusHTML escapes learner-derived text", () => {
  const evil = { ...COURSE, title: "<img src=x onerror=alert(1)>" };
  assert.ok(!syllabusHTML(evil).includes("<img src=x"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/views.test.js`
Expected: FAIL — `syllabus.js` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/views/syllabus.js`:

```javascript
import { esc } from "../escape.js";

function objList(objectives) {
  const items = (objectives || [])
    .filter((o) => o && o.text)
    .map((o) => `<li>${esc(o.text)} <span class="obj-tag">${esc(o.bloom || "")}</span></li>`)
    .join("");
  return items ? `<ul class="obj-list">${items}</ul>` : "";
}

function moduleBlock(module) {
  const lessons = (module.lessons || [])
    .map((l) => `<div class="syl-lesson"><div class="syl-lesson-title">${esc(l.title || "")}</div>${objList(l.objectives)}</div>`)
    .join("");
  return `<section class="syl-module"><h3>${esc(module.title || "")}</h3>${lessons}</section>`;
}

function sourceList(sources) {
  const items = (sources || [])
    .filter((s) => s && s.url)
    .map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a> <span class="src-type">${esc(s.type || "")}</span></li>`)
    .join("");
  return items ? `<ul class="src-list">${items}</ul>` : "<div class='muted'>No sources retrieved.</div>";
}

export function syllabusHTML(course) {
  const skills = (course.skills || []).map((s) => `<li>${esc(s)}</li>`).join("");
  const outcomes = objList(course.outcomes);
  const level = course.level || {};
  const modules = (course.modules || []).map(moduleBlock).join("");
  return (
    `<div class="syllabus">` +
    `<div class="eyebrow">PROPOSED PROGRAM</div>` +
    `<h1 class="session-topic">${esc(course.title || "")}</h1>` +
    `<div class="session-sub">${esc(course.subtitle || "")}</div>` +
    `<div class="syl-badges">` +
      `<span class="level-badge">${esc(level.label || level.code || "")}</span>` +
      `<span class="hours-badge">~${esc(String(course.targetHours || ""))} h estimated total effort</span>` +
    `</div>` +
    (skills ? `<h2>Skills you'll gain</h2><ul class="skill-list">${skills}</ul>` : "") +
    (outcomes ? `<h2>Course outcomes</h2>${outcomes}` : "") +
    `<h2>Syllabus</h2>${modules}` +
    `<h2>Grounding sources</h2>${sourceList(course.groundingSources)}` +
    `<div class="syl-actions">` +
      `<button class="btn-primary" data-action="accept-syllabus">Create this course</button>` +
      `<button class="btn-secondary" data-action="revise-syllabus" style="margin-top:8px">Request changes</button>` +
    `</div>` +
    `</div>`
  );
}
```

In `frontend/src/app.js`, add the import `import { syllabusHTML } from "./views/syllabus.js";` and the screen handler:

```javascript
  function showSyllabus(course) {
    pauseTimer();
    ui.screen = "syllabus";
    ui.proposedCourse = course;
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showChat);
    const view = root.querySelector("#view");
    view.innerHTML = syllabusHTML(course);
    view.querySelector('[data-action="accept-syllabus"]').addEventListener("click", acceptSyllabus);
    view.querySelector('[data-action="revise-syllabus"]').addEventListener("click", showChat);
  }

  async function acceptSyllabus() {
    const course = await createCourse({ fetch, proposal: ui.proposedCourse });
    if (course) { log("course_created", { courseId: course.id }); openCourse(course.id); }
  }
```

For the course-page contract block, extend `sessionData()` in `app.js` to pass contract info from the manifest, and render it in `dashboardHTML`. In `sessionData()`, add:

```javascript
      contract: (ui.manifest && ui.manifest.schemaVersion === 2) ? {
        level: (ui.manifest.level && (ui.manifest.level.label || ui.manifest.level.code)) || "",
        hours: ui.manifest.targetHours || null,
        skills: ui.manifest.skills || [],
      } : null,
```

In `frontend/src/views/dashboard.js`, add a helper and render it after the greeting. Add near the top:

```javascript
function contractHTML(contract) {
  if (!contract) return "";
  const skills = (contract.skills || []).slice(0, 6).map((s) => `<span class="chip">${s}</span>`).join("");
  const hours = contract.hours ? `<span class="hours-badge">~${contract.hours} h estimated total effort</span>` : "";
  return `<div class="contract"><span class="level-badge">${contract.level}</span>${hours}` +
         (skills ? `<div class="chips">${skills}</div>` : "") + `</div>`;
}
```

Then in `dashboardHTML`, insert `${contractHTML(data.contract)}` immediately after the `<div class="greeting">…</div>` line.

(Note: `data.contract.skills` come from a compiled `course.json` written by our own compiler and are not attacker-controlled, but they are course text — `dashboardHTML` already injects `data.topic`/`data.sub` unescaped in the same way, so this matches the existing pattern. Do not change the existing escaping convention in this task.)

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/views.test.js`
Expected: PASS (2 tests). Then the full frontend suite: `node --test frontend/tests/*.test.js`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/syllabus.js frontend/src/app.js frontend/src/views/dashboard.js frontend/tests/views.test.js
git commit -m "feat(A): syllabus-review screen + course-page contract badge"
```

---

## Final Verification (after all tasks)

- [ ] Backend suite green: `.venv/bin/pytest`
- [ ] Frontend suite green: `node --test frontend/tests/*.test.js`
- [ ] Frontend import-resolution check on changed modules (app.js is not unit-tested): `node --input-type=module -e "import('./frontend/src/app.js')"` — expect no unresolved-import error (see `frontend-import-check` memory).
- [ ] Manual smoke on the Pi (deploy phase): intake chat → brief → compile → syllabus review → create → first lesson generates with objectives. Then run the migration script against the Pi content dir per the Task 12 deploy-time note, and confirm the four courses still load with progress intact.

## Notes for the executor

- **Do not commit** unless Werner has explicitly said to. The per-task commit steps prepare the commit; hold them if commit permission has not been given, and batch at the end.
- The four real courses on the Pi are never destroyed. The migration is additive and id-preserving; back up the four `course.json` files before running it live.
- Compile latency: several grounded stages at ~50–190s each mean a full compile can take a few minutes. The waitress `channel-timeout=600` already covers this; if a real compile exceeds it, raise the timeout before blaming the code.
