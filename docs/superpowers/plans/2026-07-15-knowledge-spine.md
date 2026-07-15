# Knowledge Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-course knowledge spine so each generated lesson builds on what earlier lessons actually taught (consistent terms, no re-teaching, callbacks by lesson title), plus a one-off backfill for existing courses.

**Architecture:** New `backend/spine.py` owns the spine file (`content/courses/<id>/spine.json`), its validation, pruning, and the backfill. `backend/generation.py` harvests a `spine` field from every generated lesson (popped before caching, upserted into spine.json) and injects earlier lessons' spine entries into the generation prompt. `backend/courses.py` prunes the spine on course revision. No frontend changes; the spine never reaches the browser.

**Tech Stack:** Python 3 stdlib, Flask app untouched except transitively, pytest.

**Spec:** `docs/superpowers/specs/2026-07-15-knowledge-spine-design.md`

## Global Constraints

- Backend tests: `.venv/bin/pytest` from the repo root. Run the named test file per step, and the full backend suite before finishing a task.
- Commit per task on branch `feat/knowledge-spine`. Never merge or push.
- No emojis anywhere.
- Import direction: `spine.py` imports ONLY stdlib + `backend.fsutil` (never `courses` or `generation` at module level — `generation` and `courses` import `spine`, and a top-level back-import is a cycle). `valid_spine_entry` therefore lives in `spine.py`.
- Spine fields are plain text used only inside future generation prompts. They are NOT sanitized with `sanitize_html` and NOT rendered client-side. Do not add them to any sanitize loop.
- Spine file shape (exact): `{"lessons": {"<lesson_id>": {"summary": "<str>", "concepts": [{"term": "<str>", "definition": "<str>"}]}}}` with 1-4 concepts per entry.
- All spine.json writes go through `fsutil.write_text_atomic` with `json.dumps(..., indent=2, ensure_ascii=False)`.
- `SPINE_RECENT = 8`: the most recent 8 earlier lessons get full term definitions in the injected block; older ones get summary + term names only.
- Existing test fixtures: any test lesson that must pass `valid_lesson` will now also need a `spine` field (same ripple as when `preQuiz` became required). Repair fixtures by ADDING the field; never weaken an assertion.

---

### Task 1: backend/spine.py — spine file helpers + entry validation

**Files:**
- Create: `backend/spine.py`
- Test: `tests/test_spine.py` (create)

**Interfaces:**
- Produces: `spine.load_spine(content_dir, course_id) -> dict`, `spine.save_spine(content_dir, course_id, spine_data)`, `spine.upsert_entry(content_dir, course_id, lesson_id, entry)`, `spine.prune(content_dir, course_id, keep_ids)`, `spine.valid_spine_entry(obj) -> bool`. Tasks 2-5 rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spine.py`:

```python
import json

from backend import spine


def _entry(summary="Teaches recursion.", term="recursion",
           definition="A function calling itself on a smaller input."):
    return {"summary": summary, "concepts": [{"term": term, "definition": definition}]}


def test_load_spine_missing_file_returns_empty(tmp_path):
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_load_spine_corrupt_json_returns_empty(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "spine.json").write_text("{nope")
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_load_spine_wrong_shape_returns_empty(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "spine.json").write_text(json.dumps({"lessons": [1, 2]}))
    assert spine.load_spine(tmp_path, "c") == {"lessons": {}}


def test_upsert_entry_roundtrips_and_overwrites(tmp_path):
    (tmp_path / "c").mkdir()
    first = _entry()
    spine.upsert_entry(tmp_path, "c", "c-l1", first)
    assert spine.load_spine(tmp_path, "c")["lessons"]["c-l1"] == first
    second = _entry(summary="Teaches base cases.", term="base case",
                    definition="The input a recursive function answers directly.")
    spine.upsert_entry(tmp_path, "c", "c-l1", second)
    data = spine.load_spine(tmp_path, "c")
    assert data["lessons"] == {"c-l1": second}


def test_prune_keeps_only_named_ids(tmp_path):
    (tmp_path / "c").mkdir()
    spine.upsert_entry(tmp_path, "c", "c-l1", _entry())
    spine.upsert_entry(tmp_path, "c", "c-l2", _entry(term="stack", definition="Call bookkeeping."))
    spine.prune(tmp_path, "c", {"c-l1"})
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1"}


def test_prune_without_spine_file_is_a_noop(tmp_path):
    spine.prune(tmp_path, "c", {"c-l1"})  # must not raise or create anything
    assert not (tmp_path / "c" / "spine.json").exists()


def test_valid_spine_entry_accepts_good_entry():
    assert spine.valid_spine_entry(_entry())
    four = {"summary": "s", "concepts": [
        {"term": f"t{i}", "definition": f"d{i}"} for i in range(4)]}
    assert spine.valid_spine_entry(four)


def test_valid_spine_entry_rejects_malformed():
    assert not spine.valid_spine_entry(None)
    assert not spine.valid_spine_entry("recursion")
    assert not spine.valid_spine_entry({"summary": "s", "concepts": []})
    assert not spine.valid_spine_entry({"summary": "", "concepts": [{"term": "t", "definition": "d"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": [{"term": " ", "definition": "d"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": [{"term": "t"}]})
    assert not spine.valid_spine_entry({"summary": "s", "concepts": ["t"]})
    five = {"summary": "s", "concepts": [
        {"term": f"t{i}", "definition": f"d{i}"} for i in range(5)]}
    assert not spine.valid_spine_entry(five)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_spine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.spine'` (or ImportError).

- [ ] **Step 3: Write the implementation**

Create `backend/spine.py`:

```python
"""Per-course knowledge spine: what each lesson actually taught.

The spine lives in content/courses/<course_id>/spine.json and is used ONLY on the
generation side — entries are harvested from generated lessons and injected into
later lessons' prompts so they build on prior material with consistent terms.
It is never sent to the browser, so its fields carry plain text, not sanitized HTML.
"""

import json
from pathlib import Path

from backend import fsutil

MAX_CONCEPTS = 4


def _spine_path(content_dir, course_id):
    return Path(content_dir) / course_id / "spine.json"


def load_spine(content_dir, course_id):
    """Return the spine dict; a missing, corrupt, or malformed file reads as empty."""
    path = _spine_path(content_dir, course_id)
    if not path.exists():
        return {"lessons": {}}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {"lessons": {}}
    if not isinstance(data, dict) or not isinstance(data.get("lessons"), dict):
        return {"lessons": {}}
    return data


def save_spine(content_dir, course_id, spine_data):
    fsutil.write_text_atomic(
        _spine_path(content_dir, course_id),
        json.dumps(spine_data, indent=2, ensure_ascii=False),
    )


def upsert_entry(content_dir, course_id, lesson_id, entry):
    spine_data = load_spine(content_dir, course_id)
    spine_data["lessons"][lesson_id] = entry
    save_spine(content_dir, course_id, spine_data)


def prune(content_dir, course_id, keep_ids):
    """Drop entries for lessons no longer in the syllabus. No-op when nothing changes."""
    spine_data = load_spine(content_dir, course_id)
    kept = {lid: e for lid, e in spine_data["lessons"].items() if lid in keep_ids}
    if kept != spine_data["lessons"]:
        spine_data["lessons"] = kept
        save_spine(content_dir, course_id, spine_data)


def valid_spine_entry(obj):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("summary"), str) and obj["summary"].strip()):
        return False
    concepts = obj.get("concepts")
    if not (isinstance(concepts, list) and 1 <= len(concepts) <= MAX_CONCEPTS):
        return False
    for c in concepts:
        if not isinstance(c, dict):
            return False
        for field in ("term", "definition"):
            if not (isinstance(c.get(field), str) and c[field].strip()):
                return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_spine.py -v`
Expected: all PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS (no existing behavior touched).

```bash
git add backend/spine.py tests/test_spine.py
git commit -m "feat(spine): per-course knowledge spine file helpers + entry validation"
```

---

### Task 2: Harvest — generated lessons carry a required spine entry

**Files:**
- Modify: `backend/generation.py` (imports; `valid_lesson`; `lesson_prompt` JSON-keys section; `_generate_and_store_lesson` tail)
- Modify: `tests/test_generation.py` (new tests + fixture ripple)
- Modify: `tests/test_courses_api.py` (fixture ripple in the deepen mock)

**Interfaces:**
- Consumes: `spine.upsert_entry`, `spine.valid_spine_entry` (Task 1).
- Produces: every lesson dict returned by the generator must include `spine` (validated by `valid_lesson`); `_generate_and_store_lesson` pops it before caching and writes it to spine.json under `_gen_lock(("spine", course_id))`. Cached lesson files never contain a `spine` key.

**Back-compat note (same mechanism as preQuiz):** cached lessons are served as-is and never re-validated, `_reviewed_lesson` falls back to the original on an invalid rewrite, and `run_sourced` retries validation-failed generations a bounded number of times — so requiring `spine` cannot break existing courses.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generation.py`, add near `_OK_PREQUIZ`:

```python
def _ok_spine():
    return {"summary": "Teaches what recursion is.",
            "concepts": [{"term": "recursion",
                          "definition": "A function calling itself on a smaller input."}]}
```

Add tests:

```python
def test_valid_lesson_requires_spine():
    good = {
        "id": "l1", "courseId": "c", "topic": "t", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "<p>q</p>", "hintHtml": "<p>h</p>",
        "solutionAns": "a", "solutionNote": "n",
        "checks": [{"type": "fill", "prompt": "p", "answer": "a", "explanation": "e"}],
        "preQuiz": dict(_OK_PREQUIZ),
    }
    assert not generation.valid_lesson(good)  # missing spine
    good["spine"] = _ok_spine()
    assert generation.valid_lesson(good)
    good["spine"] = {"summary": "s", "concepts": []}
    assert not generation.valid_lesson(good)


def test_lesson_prompt_asks_for_spine():
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l1", lesson_title="T",
        module_title="M", position=1, total=2)
    assert "spine:" in prompt
    assert "NO HTML in any spine field" in prompt
    assert "EXACT term spelling" in prompt


def test_ensure_lesson_pops_spine_and_writes_spine_json(tmp_path):
    cdir = _course(tmp_path)
    made = _made_lesson()  # if the file has no such helper, copy the lesson dict pattern used by test_ensure_lesson_generates_validates_and_caches
    made["spine"] = _ok_spine()
    lesson = generation.ensure_lesson(cdir, "c", "c-l1", {}, generate=lambda p: made)
    assert "spine" not in lesson
    cached = json.loads((cdir / "c" / "lessons" / "c-l1.json").read_text())
    assert "spine" not in cached
    from backend import spine as spine_mod
    assert spine_mod.load_spine(cdir, "c")["lessons"]["c-l1"] == _ok_spine()
```

(Adapt `test_ensure_lesson_pops_spine_and_writes_spine_json` to this file's existing `_course` fixture and lesson-dict style — reuse whatever complete lesson dict the neighboring `ensure_lesson` tests build, plus `preQuiz` and `spine`.)

**Fixture ripple:** every place in `tests/test_generation.py` that sets `made["preQuiz"] = dict(_OK_PREQUIZ)` (or otherwise builds a lesson that must pass `valid_lesson`) must ALSO set `["spine"] = _ok_spine()`. Same for the deepen-mock lesson payload in `tests/test_courses_api.py` (the one place there that sets `preQuiz`). Add the field; do not change any assertion. Where an existing test asserts the exact set of keys in a cached file or response, `spine` must NOT be in that set (it is popped server-side).

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: the three new tests FAIL (`valid_lesson` accepts a spineless lesson; prompt lacks the text; no spine.json written). Pre-existing tests may also fail until Step 3 makes `spine` required AND the ripple is applied — apply the ripple in Step 1 so only the three new tests fail.

- [ ] **Step 3: Implement**

In `backend/generation.py`:

(a) Add to the imports block: `from backend import spine`.

(b) In `valid_lesson`, directly after the `preQuiz` check:

```python
    if not spine.valid_spine_entry(obj.get("spine")):
        return False
```

(c) In `lesson_prompt`, directly after the `preQuiz:` instruction lines (the block ending `"one-sentence preview of the key insight.\n"`), add:

```python
        '  spine: {"summary":"<one plain-text sentence stating what this lesson taught>",'
        '"concepts":[{"term":"<term name>","definition":"<one plain-text sentence>"}]} '
        "with 1-4 concepts. This indexes the lesson so FUTURE lessons can build on it: "
        "name only the concepts THIS lesson introduces, use the EXACT term spelling from "
        "your lesson body, and use NO HTML in any spine field.\n"
```

(d) In `_generate_and_store_lesson`, replace the tail

```python
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    fsutil.write_text_atomic(path, json.dumps(lesson, indent=2, ensure_ascii=False))
    return lesson
```

with

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_courses_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS.

```bash
git add backend/generation.py tests/test_generation.py tests/test_courses_api.py
git commit -m "feat(generation): required spine entry on generated lessons, harvested to spine.json"
```

---

### Task 3: Inject — earlier lessons' spine entries shape the generation prompt

**Files:**
- Modify: `backend/generation.py` (`SPINE_RECENT` + `spine_block` above `lesson_prompt`; `lesson_prompt` signature + tail; `_generate_and_store_lesson` prompt construction)
- Modify: `tests/test_generation.py`

**Interfaces:**
- Consumes: `spine.load_spine` (Task 1); `courses.flatten_lessons` entries (`{"id","title","moduleTitle","objectives"}`).
- Produces: `spine_block(earlier, spine_lessons) -> str` (pure); `lesson_prompt(..., spine_context="")` new keyword-only param appended to the prompt.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generation.py`:

```python
def test_spine_block_empty_when_no_earlier_lessons():
    assert generation.spine_block([], {"c-l1": _ok_spine()}) == ""


def test_spine_block_definitions_for_recent_terms_only_for_older():
    earlier = [{"id": f"c-l{i}", "title": f"Lesson {i}", "objectives": []}
               for i in range(1, 11)]  # 10 earlier lessons
    entries = {f"c-l{i}": {"summary": f"Sum {i}.",
                           "concepts": [{"term": f"term{i}", "definition": f"def {i}"}]}
               for i in range(1, 11)}
    block = generation.spine_block(earlier, entries)
    # oldest two fall outside SPINE_RECENT=8: summary + term name, no definition
    # (compare full "term = def" pairs — "def 1" alone is a substring of "def 10")
    assert "Sum 1." in block and "term1" in block and "term1 = def 1" not in block
    assert "Sum 2." in block and "term2 = def 2" not in block
    # the recent eight carry full definitions
    assert "term3 = def 3" in block and "term10 = def 10" in block
    assert "do NOT re-teach" in block
    assert "Never refer to lessons by number" in block


def test_spine_block_falls_back_to_objectives_for_ungenerated_lessons():
    earlier = [{"id": "c-l1", "title": "Recursion basics",
                "objectives": [{"text": "Trace a recursive call", "bloom": "apply"}]}]
    block = generation.spine_block(earlier, {})
    assert "Recursion basics" in block
    assert "planned, not yet studied" in block
    assert "Trace a recursive call" in block


def test_lesson_prompt_appends_spine_context():
    ctx = "\n\nThe learner has ALREADY covered these earlier lessons"
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l2", lesson_title="T",
        module_title="M", position=2, total=2, spine_context=ctx)
    assert ctx in prompt
    without = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l2", lesson_title="T",
        module_title="M", position=2, total=2)
    assert "ALREADY covered" not in without


def test_ensure_lesson_injects_earlier_spine_into_prompt(tmp_path):
    cdir = _course_with_two_lessons(tmp_path)  # a manifest with c-l1 then c-l2; reuse/extend the existing _course fixture pattern
    from backend import spine as spine_mod
    spine_mod.upsert_entry(cdir, "c", "c-l1", _ok_spine())
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        made = _made_lesson_for("c-l2")  # complete valid lesson dict incl. preQuiz + spine
        return made

    generation.ensure_lesson(cdir, "c", "c-l2", {}, generate=fake_generate)
    assert "recursion = A function calling itself on a smaller input." in prompts[0]
    assert 'As you saw in' in prompts[0]
```

(As in Task 2, adapt fixture helpers to the file's existing style; a two-lesson manifest is the existing `_course` manifest with a second lesson appended to the same module.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_generation.py -v -k spine`
Expected: new tests FAIL (`spine_block` missing; `lesson_prompt` rejects the kwarg).

- [ ] **Step 3: Implement**

In `backend/generation.py`, directly above `lesson_prompt`:

```python
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
```

Change the `lesson_prompt` signature to:

```python
def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
                  performance="", directive="", objectives=None, spine_context=""):
```

and change its final concatenation from `+ obj_block + directive_line` to `+ spine_context + obj_block + directive_line`.

In `_generate_and_store_lesson`, change the prompt construction to:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: all PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS.

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(generation): inject earlier lessons' spine into generation prompts (callbacks by title)"
```

---

### Task 4: Prune the spine on course revision

**Files:**
- Modify: `backend/courses.py` (import + two lines in `apply_revision`)
- Modify: `tests/test_courses.py`

**Interfaces:**
- Consumes: `spine.prune` (Task 1); `apply_revision` already builds `seen` = the revised syllabus's lesson-id set.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_courses.py`, next to the existing `apply_revision` tests (reuse their manifest/`revised` construction style):

```python
def test_apply_revision_prunes_spine_entries_for_removed_lessons(tmp_path):
    # build a course "c" with lessons c-l1 and c-l2 the way the neighboring
    # apply_revision tests do, then:
    from backend import spine
    entry = {"summary": "s", "concepts": [{"term": "t", "definition": "d"}]}
    spine.upsert_entry(cdir, "c", "c-l1", entry)
    spine.upsert_entry(cdir, "c", "c-l2", entry)
    # revised manifest keeps only c-l1
    out = courses.apply_revision(cdir, "c", revised, now="20260715T120000Z")
    assert out is not None
    assert set(spine.load_spine(cdir, "c")["lessons"]) == {"c-l1"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_courses.py -v -k prune`
Expected: FAIL — both entries survive.

- [ ] **Step 3: Implement**

In `backend/courses.py`: add `from backend import spine` to the imports. In `apply_revision`, after the `fsutil.write_text_atomic(manifest_path, ...)` line and before `return revised`, add:

```python
    spine.prune(content_dir, course_id, seen)
```

Extend the docstring's "Never touches the lessons/ directory." with: "Prunes spine.json entries for lessons removed from the syllabus."

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_courses.py -v`
Expected: all PASS.

- [ ] **Step 5: Full backend suite, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS.

```bash
git add backend/courses.py tests/test_courses.py
git commit -m "feat(courses): prune spine entries when a revision removes lessons"
```

---

### Task 5: One-off backfill for existing courses

**Files:**
- Modify: `backend/spine.py` (add `backfill_prompt`, `valid_backfill`, `backfill_course`, `__main__` block)
- Modify: `tests/test_spine.py`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `spine.backfill_course(content_dir, course_id, *, generate, batch_size=10) -> int` where `generate(prompt, validate) -> dict` (the `run_structured` calling convention used elsewhere: `lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)`). CLI: `python -m backend.spine` backfills every course under the default content dir.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_spine.py`:

```python
def _cached_lesson(topic="Recursion"):
    return {"id": "x", "topic": topic, "promptHtml": "<p>body</p>",
            "solutionNote": "worked example"}


def _write_lessons(tmp_path, course_id, lesson_ids):
    ldir = tmp_path / course_id / "lessons"
    ldir.mkdir(parents=True)
    for lid in lesson_ids:
        (ldir / f"{lid}.json").write_text(json.dumps(_cached_lesson()))
    return ldir


def test_backfill_prompt_lists_each_lesson_id():
    batch = [("c-l1", _cached_lesson()), ("c-l2", _cached_lesson("Base cases"))]
    prompt = spine.backfill_prompt(batch)
    assert "c-l1" in prompt and "c-l2" in prompt
    assert "ONLY a JSON object" in prompt
    assert "No HTML" in prompt


def test_valid_backfill_requires_exact_ids_and_valid_entries():
    good = {"c-l1": _entry(), "c-l2": _entry(term="base case", definition="d")}
    check = spine.valid_backfill(["c-l1", "c-l2"])
    assert check(good)
    assert not check({"c-l1": _entry()})                       # missing id
    assert not check({**good, "c-l3": _entry()})               # extra id
    assert not check({"c-l1": _entry(), "c-l2": {"summary": "s", "concepts": []}})
    assert not check([])


def test_backfill_course_batches_merges_and_reports_count(tmp_path):
    _write_lessons(tmp_path, "c", ["c-l1", "c-l2", "c-l3"])
    calls = []

    def fake_generate(prompt, validate):
        ids = [lid for lid in ("c-l1", "c-l2", "c-l3") if f"id={lid}" in prompt]
        calls.append(ids)
        result = {lid: _entry(summary=f"about {lid}") for lid in ids}
        assert validate(result)
        return result

    added = spine.backfill_course(tmp_path, "c", generate=fake_generate, batch_size=2)
    assert added == 3
    assert len(calls) == 2 and calls[0] == ["c-l1", "c-l2"] and calls[1] == ["c-l3"]
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1", "c-l2", "c-l3"}


def test_backfill_course_skips_ids_already_in_spine(tmp_path):
    _write_lessons(tmp_path, "c", ["c-l1", "c-l2"])
    spine.upsert_entry(tmp_path, "c", "c-l1", _entry())

    def fake_generate(prompt, validate):
        assert "id=c-l1" not in prompt
        return {"c-l2": _entry(term="t2", definition="d2")}

    added = spine.backfill_course(tmp_path, "c", generate=fake_generate)
    assert added == 1
    assert set(spine.load_spine(tmp_path, "c")["lessons"]) == {"c-l1", "c-l2"}


def test_backfill_course_missing_lessons_dir_returns_zero(tmp_path):
    assert spine.backfill_course(tmp_path, "c", generate=None) == 0


def test_backfill_course_skips_corrupt_lesson_files(tmp_path):
    ldir = _write_lessons(tmp_path, "c", ["c-l1"])
    (ldir / "c-l2.json").write_text("{nope")
    added = spine.backfill_course(
        tmp_path, "c",
        generate=lambda p, validate: {"c-l1": _entry()})
    assert added == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_spine.py -v -k backfill`
Expected: FAIL with AttributeError (functions missing).

- [ ] **Step 3: Implement**

Append to `backend/spine.py`:

```python
# ---- One-off backfill: index lessons cached before the spine existed ----


def backfill_prompt(batch):
    """batch: list of (lesson_id, cached_lesson_dict)."""
    lessons_txt = "\n\n".join(
        f"LESSON id={lid}\nTopic: {lesson.get('topic', '')}\n"
        f"Body: {lesson.get('promptHtml', '')}\n"
        f"Worked example: {lesson.get('solutionNote', '')}"
        for lid, lesson in batch
    )
    return (
        "You are indexing existing lessons of a course for a knowledge spine that "
        "future lessons will build on.\n"
        "For EACH lesson below, state what it taught. Reply with ONLY a JSON object "
        "(no prose, no fence) mapping each lesson id to "
        '{"summary":"<one plain-text sentence>","concepts":[{"term":"<exact term as '
        'used in the lesson>","definition":"<one plain-text sentence>"}]} with 1-4 '
        "concepts per lesson. No HTML in any field. Include every id exactly once.\n\n"
        + lessons_txt
    )


def valid_backfill(expected_ids):
    """Validator factory for one backfill batch: exact id set, every entry valid."""
    expected = set(expected_ids)

    def check(obj):
        return (isinstance(obj, dict)
                and set(obj.keys()) == expected
                and all(valid_spine_entry(v) for v in obj.values()))

    return check


def backfill_course(content_dir, course_id, *, generate, batch_size=10):
    """Extract spine entries for cached lessons missing from the spine.

    generate(prompt, validate) -> validated dict (the run_structured convention).
    Idempotent: lessons already in the spine are skipped, so re-running is safe.
    Returns the number of entries added.
    """
    lessons_dir = Path(content_dir) / course_id / "lessons"
    if not lessons_dir.is_dir():
        return 0
    present = load_spine(content_dir, course_id)["lessons"]
    pending = []
    for path in sorted(lessons_dir.glob("*.json")):
        lesson_id = path.stem
        if lesson_id in present:
            continue
        try:
            lesson = json.loads(path.read_text())
        except ValueError:
            continue  # corrupt cache file; ensure_lesson will regenerate it anyway
        if isinstance(lesson, dict):
            pending.append((lesson_id, lesson))
    added = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        ids = [lid for lid, _ in batch]
        result = generate(backfill_prompt(batch), valid_backfill(ids))
        spine_data = load_spine(content_dir, course_id)
        for lid in ids:
            spine_data["lessons"][lid] = result[lid]
        save_spine(content_dir, course_id, spine_data)
        added += len(ids)
    return added


if __name__ == "__main__":
    from backend import claude_client

    content_dir = Path(__file__).resolve().parent.parent / "content" / "courses"
    run = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
    for course_dir in sorted(p for p in content_dir.iterdir() if p.is_dir()):
        count = backfill_course(content_dir, course_dir.name, generate=run)
        print(f"{course_dir.name}: {count} spine entries added")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_spine.py -v`
Expected: all PASS.

- [ ] **Step 5: Full backend suite + frontend suite untouched check, then commit**

Run: `.venv/bin/pytest`
Expected: all PASS.
Run: `node --test frontend/tests/*.test.js`
Expected: all PASS (nothing frontend changed in this whole plan; this is the pre-ship sanity check).

```bash
git add backend/spine.py tests/test_spine.py
git commit -m "feat(spine): idempotent batched backfill for lessons cached before the spine"
```

---

## Deployment notes (controller, not a task)

After merge approval: rsync to the Pi (usual excludes incl. `backend/data/`), restart `claude-university` (after checking for in-flight generations), verify `/api/health`. Then run the backfill ONCE on the Pi as werner: `cd ~/claude_university && .venv/bin/python -m backend.spine` — while no lesson generation is in flight (the CLI and the service are separate processes; the in-process lock does not cover them). Re-running is safe (idempotent).
