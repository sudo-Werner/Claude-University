# Fresh Review Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a lesson comes up for review, generate 1-2 fresh Claude retrieval questions from its objectives + spine entry and serve those instead of re-serving the lesson's original checks, falling back to the originals on any failure or timeout.

**Architecture:** A new backend module `backend/review_items.py` mirrors `backend/remediation.py` exactly (prompt builder, `generation.valid_check`-validated items, sanitize-and-persist finalize, stamped JSON cache, `_gen_lock`-wrapped route). The frontend fetches items in the background the moment a review lesson opens, and swaps them onto the already-loaded lesson object in place if nothing has been answered yet by the time they arrive — no new event type, no new screen, no schema change.

**Tech Stack:** Flask/SQLite backend (`backend/`), vanilla-JS ES-module frontend (`frontend/src/`), `node --test`, pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-fresh-review-items-design.md` — the single source of requirements. Implement exactly what it says, nothing extra.

## Ambiguity resolutions

Details the spec left to this plan, resolved by reading the real source (exact anchors):

1. **`exams._fallback_objective` is reused directly, not duplicated.** The spec says to mirror "the `exams._fallback_objective` idiom" for the title-derived objective fallback. `backend/remediation.py` already imports `exams` and calls its leading-underscore helper `exams._spine_vocab` directly (remediation.py:57) — cross-module reuse of a "private" helper is an established pattern here. `review_items.py` imports `from backend import exams, fsutil, generation` and calls `exams._fallback_objective(title)` (exams.py:37-38) rather than re-typing the same text — single source of truth, no duplicated logic. No circular import: `exams.py` imports `courses, events, fsutil, generation`, never `review_items`.
2. **mcq self-check paragraph source: `remediation.py`, not `exams.py`.** The spec calls it "the remediation/exam prompt['s]" paragraph. `exams.exam_prompt` verifies `answerIndex` (exam question shape); `remediation.remediation_prompt` verifies `answer` (remediation.py:86-88) — the exact same field name the lesson-check shape (`generation.valid_check`) uses. Review items are check-shaped (`answer`, not `answerIndex`), so the plan copies remediation's paragraph verbatim: `"Before emitting, re-answer each mcq question independently from the question text alone. Confirm the choice at answer is the answer you get, and that no distractor is also defensibly correct — if one is, rewrite it."`
3. **`ensure_review_items` has no internal lock/double-check** — it is exactly the shape of `remediation.ensure_session` (remediation.py:187-201): a single `existing.get(...) == stamp` check, no lock inside the function. The spec's "cache re-check inside the lock" is satisfied because the *route* wraps the entire `ensure_review_items` call in `generation._gen_lock(...)` (mirroring `start_remediation` in app.py:334-338) — so that one check already executes while holding the lock. No extra pre-lock check (unlike `generation.ensure_lesson`'s double-checked pattern) is needed or specified.
4. **`review_items.prune`'s keep-set is `seen` (lesson ids), not module/exam keys.** Unlike `remediation.prune`/`exams.prune_pending` (keyed by module id + `"final"`), review items are keyed by **lesson id** — same key space as `spine.json`. Reading `courses.apply_revision` (courses.py:175-193) shows a `seen` set of lesson ids is already built and reused for `spine.prune(content_dir, course_id, seen)`. `review_items.prune` reuses that exact same `seen` set, placed unlocked alongside `remediation.prune` per the spec's explicit "same unlocked at-worst-one-stale-file rationale."
5. **Backend test file split mirrors the remediation precedent exactly, verified by reading both files.** `tests/test_remediation.py` (all 259 lines) contains zero Flask-client tests — every pure function (`remediation_prompt`, `valid_remediation`, `finalize_session`, `ensure_session`, `prune`, `session_completed`) is tested directly. All HTTP-route tests for remediation (`test_remediation_404_without_failed_exam`, `test_remediation_generates_serves_and_reuses`, `test_remediation_grade_*`, etc.) live in `tests/test_courses_api.py`. This plan follows the identical split: `tests/test_review_items.py` gets pure-function tests only; the new GET route's tests and the `apply_revision`-prunes-review-items test are appended to `tests/test_courses_api.py`.
6. **Frontend test file split by module, not all in `views.test.js`.** `frontend/tests/courses.test.js` already has one test block per `frontend/src/courses.js` export (`loadLesson`, `loadCapstone`, `startRemediation`, etc. — verified lines 1-247); `frontend/tests/checks.test.js` already tests `checksHTML`/`gradeCheck` directly (its only exports). This plan puts `loadReviewItems` tests in `courses.test.js` and the `checksHTML` fresh-heading test in `checks.test.js`, matching that convention; only the `lessonHTML`-level composition tests (placeholder, byte-identical, rating-gate-with-fresh-fixture) go in `views.test.js`, which is where every other `lessonHTML` test already lives.
7. **60s AbortController timeout is not exercised with a real 60-second wait in tests.** No fake-timer utility is used elsewhere in this repo's frontend tests. The test suite instead asserts the two behavioral contracts directly and fast: (a) `loadReviewItems` passes an `AbortSignal` to `fetch` (proving the wiring exists), and (b) any thrown fetch error — including a simulated `AbortError` — is mapped to the `{error}` shape (proving "on abort return the `{error}` shape" without waiting on the real timer).
8. **Route placement in `backend/app.py`:** inserted directly after `GET /api/courses/<course_id>/reviews` (app.py:542-551) and before `POST /api/courses/<course_id>/revise` (app.py:553) — grouped with the other SRS/review-related route since both use `srs`. No spec constraint on exact position; this is the most legible placement given existing file organization.
9. **`fetchFreshItems` call sites verified exactly.** The spec says "right after the review `lessonState` is created" in both `startReviewSession` and `advanceAfterLesson`. Reading `frontend/src/app.js` confirms both functions build `ui.lessonState = {..., isReview: true}` as a single literal assignment (lines 989 and 1012) with no intervening code before the next statement — `fetchFreshItems(ui.lessonState, ui.lesson)` is inserted as the very next line in both places.

## Global Constraints

Binding requirements copied from the spec, one per line — every task must satisfy all of these:

- Fresh items must pass `generation.valid_check` (backend/generation.py:191-205) — no other validation path.
- Every learner-facing generated string (`prompt`, `choices`, `explanation`) passes `generation.sanitize_html` server-side before persisting; fill `answer` stays verbatim (grading contract compares learner typing).
- Explicit-fields-only copying — unknown model keys never reach the stored file.
- A `validate=` predicate is passed to `claude_client.run_structured`; no custom retry loop (the client already retries once).
- Route error contract: `ClaudeAuthError` → 503 `{"error", "code":"reauth"}`; `ClaudeError` → 502 `{"error"}`; unknown course/lesson or bad id → 404, never 500; both ids gated by `_ID_RE` before any filesystem access.
- Cache file at `content/courses/<course_id>/review-items/<lesson_id>.json`, written via `fsutil.write_text_atomic`; corrupt or missing reads as missing (regenerate), never a 500.
- Cache stamp = review count = number of `lesson_reviewed` events for that lesson at generation time.
- Route wraps `ensure_review_items` in `generation._gen_lock(("review-items", course_id, lesson_id))`, with the cache re-check happening inside that lock.
- `lesson_check` events from fresh items carry `source: "review"` in the payload; no new event type; no mastery/stats whitelist changes.
- Backend tests: `.venv/bin/pytest -q` (from repo root). Frontend tests: `node --test frontend/tests/*.test.js` — the explicit glob is required; a bare directory silently runs nothing.
- After any `frontend/src/app.js` change, run the import-resolution check: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` (app.js is not unit-tested by repo convention).
- Commit after each task; every commit message ends with the trailer line:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Backend — `review_items.py` module + route + `apply_revision` prune

**Files:**
- Create: `backend/review_items.py`
- Modify: `backend/app.py` (import line 6; new route inserted after `get_reviews`, which ends line 551, before `post_course_revise` at line 553)
- Modify: `backend/courses.py` (`apply_revision`: import line 197; prune call inserted after line 200, before `return revised`)
- Create: `tests/test_review_items.py`
- Modify: `tests/test_courses_api.py` (one test inserted after `test_apply_revision_404_for_illegal_id`, which ends line 704; six more tests appended at the end of the file, after `test_retake_gate_full_corrective_loop_via_api`)

**Interfaces:**
- Consumes: `generation.valid_check(item)` (generation.py:191-205); `generation.sanitize_html(value)` (generation.py:62-67); `generation._gen_lock(key)` (generation.py:16-21); `exams._fallback_objective(title)` (exams.py:37-38); `fsutil.write_text_atomic(path, text)`; `courses.flatten_lessons(manifest)` → entries `{id, title, moduleTitle, objectives}` (courses.py:31-41); `courses.load_lesson`/`load_manifest` (courses.py:11-28); `spine.load_spine(content_dir, course_id)["lessons"]` (spine.py:21-32); `srs.reviews_by_lesson(conn, course_id)` → `{lesson_id: [{"quality","date","at"}, ...]}` (srs.py:41-65); `claude_client.run_structured(prompt, *, validate=None)` (claude_client.py:170-182); `_ID_RE` and the `db.get_connection(path)` try/finally idiom (app.py).
- Produces: `review_items.review_items_prompt(lesson_meta, spine_entry, existing_check_prompts)`, `review_items.valid_review_items(obj)`, `review_items.finalize_items(obj, lesson_id, review_count)` → `{"lessonId","reviewCount","items"}`, `review_items.save_items/load_items/_path`, `review_items.ensure_review_items(content_dir, course_id, lesson_id, review_count, *, lesson_meta, spine_entry, existing_checks, generate)`, `review_items.prune(content_dir, course_id, keep_lesson_ids)`. Route `GET /api/courses/<course_id>/lessons/<lesson_id>/review-items` → `{"items": [...]}` — Task 2's `loadReviewItems` consumes this exact URL/shape.

- [ ] **Step 1: Write the failing pure-function tests**

Create `tests/test_review_items.py`:

```python
import json

from backend import generation, review_items


def _lesson_meta(objectives=None, title="Loops", module_title="Control Flow"):
    meta = {"id": "c1-l1", "title": title, "moduleTitle": module_title}
    if objectives is not None:
        meta["objectives"] = objectives
    return meta


OBJECTIVES = [{"text": "Write a for loop", "bloom": "apply", "knowledge": "procedural"}]
SPINE_ENTRY = {"summary": "Loops repeat a block of code.",
               "concepts": [{"term": "for loop", "definition": "repeats a block a fixed number of times"}]}


def _good_items():
    return {"items": [
        {"type": "mcq", "prompt": "Which keyword starts a for loop?", "choices": ["for", "if", "def"],
         "answer": 0, "explanation": "for introduces the loop"},
        {"type": "fill", "prompt": "How many times does `for i in range(3)` run?", "answer": "3",
         "explanation": "range(3) yields 0,1,2"},
    ]}


def test_prompt_includes_title_module_and_objectives():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert '"Loops"' in p and '"Control Flow"' in p
    assert "Write a for loop" in p and "Bloom: apply" in p


def test_prompt_includes_spine_terms_and_omits_when_absent():
    with_spine = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), SPINE_ENTRY, [])
    assert "for loop: repeats a block a fixed number of times" in with_spine
    assert "Loops repeat a block of code." in with_spine

    without_spine = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "repeats a block a fixed number of times" not in without_spine

    empty_spine = review_items.review_items_prompt(
        _lesson_meta(OBJECTIVES), {"summary": "", "concepts": []}, [])
    assert "What the lesson" not in empty_spine


def test_prompt_falls_back_to_title_derived_objective_when_absent():
    p = review_items.review_items_prompt(_lesson_meta(objectives=[], title="Recursion"), None, [])
    assert 'Explain the key ideas of "Recursion"' in p
    p2 = review_items.review_items_prompt(_lesson_meta(objectives=None, title="Recursion"), None, [])
    assert 'Explain the key ideas of "Recursion"' in p2


def test_prompt_includes_no_repeat_instruction_with_existing_prompts():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, ["What keyword starts a loop?"])
    assert "do NOT repeat or lightly reword these existing questions" in p
    assert "What keyword starts a loop?" in p

    without = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "do NOT repeat or lightly reword these existing questions" not in without


def test_prompt_demands_exactly_two_items_and_json_only():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert "EXACTLY 2" in p
    assert "Reply with ONLY a JSON object, no prose, no fence" in p
    assert '{"items":' in p


def test_prompt_has_mcq_self_verification_paragraph_verbatim():
    p = review_items.review_items_prompt(_lesson_meta(OBJECTIVES), None, [])
    assert ("Before emitting, re-answer each mcq question independently from the question "
            "text alone. Confirm the choice at answer is the answer you get, and that no "
            "distractor is also defensibly correct — if one is, rewrite it.") in p


def test_valid_review_items_accepts_one_or_two_good_items():
    assert review_items.valid_review_items(_good_items())
    one = {"items": [_good_items()["items"][0]]}
    assert review_items.valid_review_items(one)


def test_valid_review_items_rejects_zero_three_nonlist_and_bad_shapes():
    assert not review_items.valid_review_items({"items": []})
    three = _good_items()
    three["items"].append(dict(three["items"][1]))
    assert not review_items.valid_review_items(three)
    assert not review_items.valid_review_items({"items": "nope"})
    assert not review_items.valid_review_items({})
    assert not review_items.valid_review_items(None)
    bad_check = {"items": [{"type": "mcq", "prompt": "q", "choices": ["a"], "answer": 5, "explanation": "e"}]}
    assert not review_items.valid_review_items(bad_check)


def test_finalize_items_sanitizes_keeps_fill_verbatim_and_drops_unknown_keys():
    raw = _good_items()
    raw["items"][0]["prompt"] = "<p>Q <script>x()</script></p>"
    raw["items"][0]["choices"] = ["<b>for</b>", "if", "def"]
    raw["items"][1]["answer"] = "  3  "  # verbatim: whitespace preserved exactly
    raw["items"][0]["bogus"] = "should not survive"
    out = review_items.finalize_items(raw, "c1-l1", 2)
    assert out["lessonId"] == "c1-l1" and out["reviewCount"] == 2
    assert len(out["items"]) == 2
    assert "<script>" not in out["items"][0]["prompt"]
    assert "bogus" not in out["items"][0]
    assert set(out["items"][0].keys()) == {"type", "prompt", "answer", "explanation", "choices"}
    assert set(out["items"][1].keys()) == {"type", "prompt", "answer", "explanation"}
    assert out["items"][0]["answer"] == 0        # mcq answer int kept
    assert out["items"][1]["answer"] == "  3  "  # fill answer verbatim


def test_persistence_roundtrip_corrupt_and_prune(tmp_path):
    items = review_items.finalize_items(_good_items(), "c1-l1", 1)
    review_items.save_items(tmp_path, "c1", items)
    assert review_items.load_items(tmp_path, "c1", "c1-l1")["reviewCount"] == 1
    (tmp_path / "c1" / "review-items" / "c1-l1.json").write_text("{nope")
    assert review_items.load_items(tmp_path, "c1", "c1-l1") is None
    review_items.save_items(tmp_path, "c1", items)
    review_items.save_items(tmp_path, "c1", {**items, "lessonId": "c1-l2"})
    review_items.prune(tmp_path, "c1", {"c1-l2"})
    assert review_items.load_items(tmp_path, "c1", "c1-l1") is None
    assert review_items.load_items(tmp_path, "c1", "c1-l2") is not None


def test_ensure_review_items_reuses_fresh_and_regenerates_on_stamp_change(tmp_path):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = _good_items()
        assert validate(obj)
        return obj

    meta = _lesson_meta(OBJECTIVES)
    s1 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s1["reviewCount"] == 1 and len(calls) == 1
    s2 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s2["reviewCount"] == 1 and len(calls) == 1   # served from disk
    s3 = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 2, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=gen)
    assert s3["reviewCount"] == 2 and len(calls) == 2   # stamp changed -> regenerated


def test_ensure_review_items_corrupt_cache_regenerates(tmp_path):
    path = tmp_path / "c1" / "review-items" / "c1-l1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{corrupt")
    meta = _lesson_meta(OBJECTIVES)
    result = review_items.ensure_review_items(
        tmp_path, "c1", "c1-l1", 1, lesson_meta=meta, spine_entry=None,
        existing_checks=[], generate=lambda p, v: _good_items())
    assert result["reviewCount"] == 1 and len(result["items"]) == 2
```

- [ ] **Step 2: Run the new test file to verify it fails**

Run: `.venv/bin/pytest tests/test_review_items.py -q`
Expected: a collection error — `ModuleNotFoundError: No module named 'backend.review_items'` (the module does not exist yet).

- [ ] **Step 3: Implement `backend/review_items.py`**

Create `backend/review_items.py`:

```python
"""Fresh retrieval items for review sessions (Claude-in-lessons deep dive item 2).

When a lesson comes up for review, the review serves 1-2 FRESH retrieval questions
generated from the lesson's objectives and knowledge-spine entry, instead of
re-serving the lesson's original checks — varied retrieval beats identical-item
re-testing (Butler 2010; Roediger & Karpicke). Answers are graded client-side in the
exact lesson-check shape (generation.valid_check) exactly like ordinary checks, and
land as lesson_check events tagged source="review" — mastery, stats, and SRS need
zero new code. Items are cached per lesson, stamped with the review count (number of
lesson_reviewed events) at generation time: re-serving within one review pass is
free, the next review session regenerates (the remediation attempt-stamp idiom).
"""

import json
from pathlib import Path

from backend import exams, fsutil, generation

ITEMS_MIN = 1
ITEMS_MAX = 2


def review_items_prompt(lesson_meta, spine_entry, existing_check_prompts):
    title = lesson_meta.get("title", "")
    module_title = lesson_meta.get("moduleTitle", "")
    objectives = [o for o in (lesson_meta.get("objectives") or [])
                  if isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip()]
    if not objectives:
        objectives = [exams._fallback_objective(title)]
    obj_lines = "; ".join(
        f"{o.get('text', '')} (Bloom: {o.get('bloom', '')})" for o in objectives)

    spine_block = ""
    if isinstance(spine_entry, dict):
        concepts = [c for c in (spine_entry.get("concepts") or []) if isinstance(c, dict)]
        term_lines = "\n".join(f"- {c.get('term', '')}: {c.get('definition', '')}" for c in concepts)
        summary = spine_entry.get("summary", "")
        if summary or term_lines:
            spine_block = (
                f'\nWhat the lesson "{title}" taught: {summary}\n'
                + (term_lines + "\n" if term_lines else "")
            )

    existing_block = ""
    if existing_check_prompts:
        joined = "\n".join(f"- {p}" for p in existing_check_prompts)
        existing_block = (
            "\nThis lesson's existing concept-check questions — do NOT repeat or lightly "
            f"reword these existing questions; write genuinely NEW retrieval items:\n{joined}\n"
        )

    return (
        "You are a tutor on a personal learning platform writing FRESH retrieval-practice "
        f'questions for a learner reviewing the lesson "{title}" (module: "{module_title}").\n'
        f"Learning objectives this lesson teaches to: {obj_lines}\n"
        + spine_block
        + existing_block +
        "\nWrite EXACTLY 2 NEW concept-check items testing these objectives, a mix of mcq and "
        "fill where the content allows. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,'
        '"explanation":"<specific, encouraging one-sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact word or short phrase>",'
        '"explanation":"<specific, encouraging one-sentence why>"}.\n'
        "Before emitting, re-answer each mcq question independently from the question text "
        "alone. Confirm the choice at answer is the answer you get, and that no distractor is "
        "also defensibly correct — if one is, rewrite it.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"items":[<check>, <check>]}'
    )


def valid_review_items(obj):
    if not isinstance(obj, dict):
        return False
    items = obj.get("items")
    if not (isinstance(items, list) and ITEMS_MIN <= len(items) <= ITEMS_MAX):
        return False
    return all(generation.valid_check(i) for i in items)


def finalize_items(obj, lesson_id, review_count):
    """Explicit-fields-only copy (never persist unknown model keys, remediation.py's
    finalize_session idiom): prompt/explanation/choices through generation.sanitize_html,
    mcq answer int kept, fill answer kept verbatim (client-side grading compares learner
    typing)."""
    items = []
    for it in obj["items"]:
        item = {
            "type": it["type"],
            "prompt": generation.sanitize_html(it["prompt"]),
            "answer": it["answer"],
            "explanation": generation.sanitize_html(it["explanation"]),
        }
        if it["type"] == "mcq":
            item["choices"] = [generation.sanitize_html(c) for c in it["choices"]]
        items.append(item)
    return {"lessonId": lesson_id, "reviewCount": review_count, "items": items}


def _path(content_dir, course_id, lesson_id):
    return Path(content_dir) / course_id / "review-items" / f"{lesson_id}.json"


def save_items(content_dir, course_id, items):
    path = _path(content_dir, course_id, items["lessonId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(items, indent=2, ensure_ascii=False))


def load_items(content_dir, course_id, lesson_id):
    path = _path(content_dir, course_id, lesson_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("items"), list) else None


def prune(content_dir, course_id, keep_lesson_ids):
    items_dir = Path(content_dir) / course_id / "review-items"
    if not items_dir.is_dir():
        return
    for f in items_dir.glob("*.json"):
        if f.stem not in keep_lesson_ids:
            f.unlink(missing_ok=True)


def ensure_review_items(content_dir, course_id, lesson_id, review_count, *,
                        lesson_meta, spine_entry, existing_checks, generate):
    """Serve the stored items when they were stamped with the current review count;
    otherwise generate, persist, and return fresh ones (remediation.ensure_session
    shape — the caller holds generation._gen_lock for the whole call, so this single
    check IS the cache re-check inside the lock)."""
    existing = load_items(content_dir, course_id, lesson_id)
    if existing is not None and existing.get("reviewCount") == review_count:
        return existing
    existing_check_prompts = [c.get("prompt", "") for c in (existing_checks or [])
                              if isinstance(c, dict) and isinstance(c.get("prompt"), str)]
    prompt = review_items_prompt(lesson_meta, spine_entry, existing_check_prompts)
    obj = generate(prompt, valid_review_items)
    items = finalize_items(obj, lesson_id, review_count)
    save_items(content_dir, course_id, items)
    return items
```

- [ ] **Step 4: Run the new test file to verify it passes**

Run: `.venv/bin/pytest tests/test_review_items.py -q`
Expected: all 12 tests PASS.

- [ ] **Step 5: Write the failing route + apply_revision-prune tests**

In `tests/test_courses_api.py`, insert this test directly after `test_apply_revision_404_for_illegal_id` (ends line 704), before the blank lines and `# ---- #5 explain-it-back grading ----` comment:

```python
def test_apply_revision_prunes_review_items(tmp_path, monkeypatch):
    from backend import review_items
    manifest = courses.write_course(tmp_path, COMPILED)
    cid = manifest["id"]
    kept_id = manifest["modules"][0]["lessons"][0]["id"]
    review_items.save_items(tmp_path, cid, {"lessonId": kept_id, "reviewCount": 0, "items": []})
    review_items.save_items(tmp_path, cid, {"lessonId": "ghost-lesson", "reviewCount": 0, "items": []})
    client = _client(tmp_path, monkeypatch)
    revised = {**manifest, "title": "Deep ML (Revised)"}
    r = client.post(f"/api/courses/{cid}/apply-revision", json={"course": revised})
    assert r.status_code == 200
    assert review_items.load_items(tmp_path, cid, kept_id) is not None
    assert review_items.load_items(tmp_path, cid, "ghost-lesson") is None
```

Then append this section at the very end of `tests/test_courses_api.py` (after `test_retake_gate_full_corrective_loop_via_api`, the last test in the file):

```python
# ---------------------------------------------------------------------------
# fresh review items
# ---------------------------------------------------------------------------

def test_review_items_route_returns_items(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    items = {"items": [
        {"type": "mcq", "prompt": "q1", "choices": ["a", "b"], "answer": 0, "explanation": "e1"},
        {"type": "fill", "prompt": "q2", "answer": "x", "explanation": "e2"},
    ]}
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None, **kw: items)
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["items"]) == 2
    assert (root / cid / "review-items" / f"{lesson_id}.json").exists()


def test_review_items_route_reuses_cache_for_same_review_count(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    calls = []

    def fake(prompt, validate=None, **kw):
        calls.append(prompt)
        return {"items": [{"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]}

    monkeypatch.setattr(claude_client, "run_structured", fake)
    r1 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    r2 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(calls) == 1  # served from disk on the second call


def test_review_items_route_review_count_from_seeded_events(client, tmp_path, monkeypatch):
    from backend import courses, claude_client, db, events
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    app_db = client.application.config["DB_PATH"]
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-1", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2026-07-10T09:00:00+00:00", "course_id": cid,
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()

    seen_prompts = []

    def fake(prompt, validate=None, **kw):
        seen_prompts.append(prompt)
        return {"items": [{"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]}

    monkeypatch.setattr(claude_client, "run_structured", fake)
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200
    stored = json.loads((root / cid / "review-items" / f"{lesson_id}.json").read_text())
    assert stored["reviewCount"] == 1        # one lesson_reviewed event seeded

    # A second review event bumps the stamp -> cache miss -> regenerates
    conn = db.get_connection(app_db)
    try:
        events.insert_events(conn, [{
            "client_event_id": "rev-2", "session_id": "s1", "event_type": "lesson_reviewed",
            "occurred_at": "2026-07-11T09:00:00+00:00", "course_id": cid,
            "topic_id": lesson_id, "payload": {"quality": "good"},
        }])
    finally:
        conn.close()
    resp2 = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp2.status_code == 200
    stored2 = json.loads((root / cid / "review-items" / f"{lesson_id}.json").read_text())
    assert stored2["reviewCount"] == 2
    assert len(seen_prompts) == 2


def test_review_items_route_404s(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    assert client.get(f"/api/courses/{cid}/lessons/nope/review-items").status_code == 404
    assert client.get("/api/courses/nope/lessons/x/review-items").status_code == 404
    assert client.get(f"/api/courses/Bad_Id/lessons/{lesson_id}/review-items").status_code == 404


def test_review_items_route_does_not_require_cached_lesson_file(client, tmp_path, monkeypatch):
    """Items come from the manifest + spine, not the lesson body — deleting the cached
    lesson file must not 404 the route."""
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    (root / cid / "lessons" / f"{lesson_id}.json").unlink()
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, validate=None, **kw: {"items": [
                            {"type": "fill", "prompt": "q", "answer": "x", "explanation": "e"}]})
    resp = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert resp.status_code == 200


def test_review_items_route_maps_claude_errors(client, tmp_path, monkeypatch):
    from backend import courses, claude_client
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]

    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items").status_code == 502

    def auth_boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/review-items")
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"
```

- [ ] **Step 6: Run the new tests to verify they fail**

Run: `.venv/bin/pytest tests/test_courses_api.py -q -k review_items`
Expected: FAIL — `test_apply_revision_prunes_review_items` raises `ModuleNotFoundError`/`ImportError` on `from backend import review_items`; every `test_review_items_route_*` test gets a 404 (route does not exist yet).

- [ ] **Step 7: Add the `review-items` route to `backend/app.py`**

Change the import line (currently line 6):

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats, exams, spine, remediation, transcript, capstone
```

to:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats, exams, spine, remediation, transcript, capstone, review_items
```

Then insert this new route directly after `get_reviews` (ends line 551 with `return jsonify({"due": due})`) and before `post_course_revise` (line 553):

```python
    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/review-items")
    def get_review_items(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        lesson_meta = next(
            (l for l in courses.flatten_lessons(manifest) if l["id"] == lesson_id), None)
        if lesson_meta is None:
            return jsonify({"error": "lesson not found"}), 404
        conn = db.get_connection(path)
        try:
            review_count = len(srs.reviews_by_lesson(conn, course_id).get(lesson_id, []))
        finally:
            conn.close()
        spine_entry = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"].get(lesson_id)
        cached_lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        existing_checks = cached_lesson.get("checks", []) if isinstance(cached_lesson, dict) else []
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        try:
            with generation._gen_lock(("review-items", course_id, lesson_id)):
                result = review_items.ensure_review_items(
                    courses.CONTENT_DIR, course_id, lesson_id, review_count,
                    lesson_meta=lesson_meta, spine_entry=spine_entry,
                    existing_checks=existing_checks, generate=generate,
                )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare fresh review questions"}), 502
        return jsonify({"items": result["items"]})
```

- [ ] **Step 8: Wire `review_items.prune` into `courses.apply_revision`**

In `backend/courses.py`, change (currently lines 194-201):

```python
    # Pending exams and gap reviews for modules dropped by the revision are dead.
    # (Not locked: a concurrent start for a just-dropped module can at worst leave
    # one stale file, which status/freshness checks ignore and the next revision removes.)
    from backend import exams, remediation
    module_ids = {m.get("id") for m in revised.get("modules", [])}
    exams.prune_pending(content_dir, course_id, module_ids | {"final"})
    remediation.prune(content_dir, course_id, module_ids | {"final"})
    return revised
```

to:

```python
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
    return revised
```

- [ ] **Step 9: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/test_courses_api.py -q -k review_items`
Expected: all 7 tests PASS.

- [ ] **Step 10: Run the full backend suite**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS (every pre-existing test plus the 19 new ones — 12 in `test_review_items.py`, 7 in `test_courses_api.py`).

- [ ] **Step 11: Commit**

```bash
git add backend/review_items.py backend/app.py backend/courses.py tests/test_review_items.py tests/test_courses_api.py
git commit -m "$(cat <<'EOF'
feat(review-items): backend module + route for fresh review items

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Frontend — fetch wrapper, pending placeholder, fresh-items heading

**Files:**
- Modify: `frontend/src/courses.js` (new `loadReviewItems` inserted after `loadReviews`, which ends line 87, before `createCourse` at line 89)
- Modify: `frontend/src/views/checks.js` (replace `checksHTML`, currently lines 40-44)
- Modify: `frontend/src/views/lesson.js` (replace the checks-render line, currently line 220)
- Modify: `frontend/styles.css` (insert after `.checks-title`, currently line 393)
- Modify: `frontend/tests/courses.test.js` (import line 3; append `loadReviewItems` tests at the end of the file)
- Modify: `frontend/tests/checks.test.js` (append 2 tests after line 41)
- Modify: `frontend/tests/views.test.js` (append 4 tests after `"lessonHTML outside review mode is unaffected by the rating gate"`, which ends line 350, before the `"dashboard shows a mastery breakdown..."` test at line 352)

**Interfaces:**
- Consumes: the route contract from Task 1 — `GET /api/courses/<course_id>/lessons/<lesson_id>/review-items` → 200 `{"items":[...]}` or non-200 `{"error", "code"?}`; the existing `{error}` fallback idiom used by every other wrapper in `frontend/src/courses.js` (e.g. `loadLesson`, `loadCapstone`); `checksHTML(checks, state)` (checks.js:40-44); `lessonHTML(lesson, state, nav)` (lesson.js:147-242).
- Produces: `loadReviewItems({ fetch, courseId, lessonId })` — Task 3's `fetchFreshItems` calls this exact function; `checksHTML` renders the heading `"Fresh review questions"` when `state.freshItems` is truthy (otherwise unchanged) — Task 3 sets `ls.freshItems = true` on adoption; `lessonHTML` renders `<p class="checks-pending">Preparing fresh review questions…</p>` when `state.isReview && state.freshPending` post-reveal — Task 3 sets/clears `ls.freshPending`.

- [ ] **Step 1: Write the failing frontend tests**

Append to `frontend/tests/courses.test.js`. First change the import line (currently line 3):

```js
import { listCourses, loadCourse, loadLesson, loadReviews, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript } from "../src/courses.js";
```

to:

```js
import { listCourses, loadCourse, loadLesson, loadReviews, loadReviewItems, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript } from "../src/courses.js";
```

Then append at the end of the file (after `test("loadTranscript returns body or null", ...)`):

```js
test("loadReviewItems fetches by course and lesson id and returns items", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ items: [{ type: "fill", prompt: "p", answer: "a", explanation: "e" }] }) };
  };
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/review-items");
  assert.ok(opts.signal instanceof AbortSignal);
  assert.equal(res.items.length, 1);
});

test("loadReviewItems returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "could not prepare fresh review questions" }) });
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(res.error, "could not prepare fresh review questions");
});

test("loadReviewItems returns an error shape when the fetch is aborted", async () => {
  const fetch = async () => { throw new DOMException("The operation was aborted.", "AbortError"); };
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(res.error);
});
```

Append to `frontend/tests/checks.test.js` (after `test("checksHTML renders nothing for no checks", ...)`, which ends line 41):

```js
test("checksHTML shows the fresh-items heading when state.freshItems is set", () => {
  const html = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {}, freshItems: true },
  );
  assert.match(html, /Fresh review questions/);
  assert.doesNotMatch(html, /Check your understanding/);
});

test("checksHTML keeps the default heading when freshItems is absent or false", () => {
  const absent = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {} },
  );
  assert.match(absent, /Check your understanding/);
  const falsy = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {}, freshItems: false },
  );
  assert.equal(absent, falsy);
});
```

Append to `frontend/tests/views.test.js`, directly after `test("lessonHTML outside review mode is unaffected by the rating gate", ...)` (ends line 350), before `test("dashboard shows a mastery breakdown when there is mastery data", ...)` (line 352):

```js
test("lessonHTML shows a pending placeholder instead of checks while fresh review items load", () => {
  const pending = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true, freshPending: true,
    checkAnswers: {}, checkResults: {},
  });
  assert.match(pending, /checks-pending/);
  assert.match(pending, /Preparing fresh review questions…/);
  assert.doesNotMatch(pending, /Check your understanding/);

  // once pending resolves (freshPending false) the checks render normally again
  const resolved = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true, freshPending: false,
    checkAnswers: {}, checkResults: {},
  });
  assert.doesNotMatch(resolved, /checks-pending/);
  assert.match(resolved, /Check your understanding/);

  // outside review mode, freshPending has no effect (placeholder never shows)
  const nonReviewPending = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, freshPending: true,
    checkAnswers: {}, checkResults: {},
  });
  assert.doesNotMatch(nonReviewPending, /checks-pending/);
});

test("lessonHTML shows the fresh-items heading once items have been swapped in (not pending)", () => {
  const html = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true,
    freshPending: false, freshItems: true, checkAnswers: {}, checkResults: {},
  });
  assert.match(html, /Fresh review questions/);
  assert.doesNotMatch(html, /Check your understanding/);
});

test("lessonHTML checks rendering is unaffected by fresh-item fields when absent (byte-identical)", () => {
  const withoutFields = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    checkAnswers: {}, checkResults: {},
  });
  const withFalsyFields = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    checkAnswers: {}, checkResults: {}, isReview: false, freshPending: false, freshItems: false,
  });
  assert.equal(withoutFields, withFalsyFields);
});

const FRESH_ITEMS_LESSON = {
  ...SAMPLE_LESSON,
  checks: [
    { type: "mcq", prompt: "Which is prime?", choices: ["4", "7"], answer: 1, explanation: "7 is prime" },
    { type: "fill", prompt: "5+5?", answer: "10", explanation: "sum" },
  ],
};

test("ratingLocked and suggestedQuality work unchanged against a swapped fresh-items set", () => {
  const locked = { isReview: true, freshItems: true, checkResults: { 0: { correct: true } } };
  assert.equal(ratingLocked(FRESH_ITEMS_LESSON, locked), true);
  const unlocked = { isReview: true, freshItems: true, checkResults: { 0: { correct: true }, 1: { correct: true } } };
  assert.equal(ratingLocked(FRESH_ITEMS_LESSON, unlocked), false);
  assert.equal(suggestedQuality(FRESH_ITEMS_LESSON, unlocked), "good");
});
```

- [ ] **Step 2: Run the frontend suite to verify the new tests fail**

Run: `node --test frontend/tests/*.test.js`
Expected: the courses.test.js import fails (`loadReviewItems` is not exported), and the new checks.test.js/views.test.js assertions FAIL (no `.checks-pending` markup, no "Fresh review questions" heading yet); all pre-existing tests still pass.

- [ ] **Step 3: Implement `loadReviewItems` in `frontend/src/courses.js`**

Insert after `loadReviews` (currently ends line 87), before `createCourse` (line 89):

```js
export async function loadReviewItems({ fetch, courseId, lessonId }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/review-items`, { signal: controller.signal });
    if (!resp.ok) {
      let message = "Couldn't prepare fresh review questions right now.";
      try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
      return { error: message };
    }
    return resp.json();
  } catch (e) {
    return { error: "Couldn't prepare fresh review questions right now." };
  } finally {
    clearTimeout(timer);
  }
}
```

- [ ] **Step 4: Change the checks heading in `frontend/src/views/checks.js`**

Replace `checksHTML` (currently lines 40-44):

```js
export function checksHTML(checks, state) {
  if (!checks || !checks.length) return "";
  const items = checks.map((c, i) => item(c, i, state)).join("");
  return `<section class="checks"><div class="checks-title">Check your understanding</div>${items}</section>`;
}
```

with:

```js
export function checksHTML(checks, state) {
  if (!checks || !checks.length) return "";
  const items = checks.map((c, i) => item(c, i, state)).join("");
  const title = state && state.freshItems ? "Fresh review questions" : "Check your understanding";
  return `<section class="checks"><div class="checks-title">${title}</div>${items}</section>`;
}
```

- [ ] **Step 5: Add the pending placeholder in `frontend/src/views/lesson.js`**

Replace the checks-render line (currently line 220):

```js
    ${state.solutionRevealed ? checksHTML(lesson.checks || [], state) : ""}
```

with:

```js
    ${state.solutionRevealed
      ? (state.isReview && state.freshPending
          ? '<p class="checks-pending">Preparing fresh review questions…</p>'
          : checksHTML(lesson.checks || [], state))
      : ""}
```

- [ ] **Step 6: Add the `.checks-pending` CSS rule**

In `frontend/styles.css`, insert directly after `.checks-title` (currently line 393):

```css
.checks-pending{font-size:13px; color:var(--text-dim); font-style:italic; margin-top:4px}
```

(`--text-dim` is declared in `:root` at styles.css:10 — no new variable needed.)

- [ ] **Step 7: Run the frontend suite to verify the new tests pass**

Run: `node --test frontend/tests/*.test.js`
Expected: all tests PASS, including the 3 new `courses.test.js` tests, 2 new `checks.test.js` tests, and 4 new `views.test.js` tests, plus every pre-existing test unchanged.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/courses.js frontend/src/views/checks.js frontend/src/views/lesson.js frontend/styles.css frontend/tests/courses.test.js frontend/tests/checks.test.js frontend/tests/views.test.js
git commit -m "$(cat <<'EOF'
feat(review-items): frontend pending placeholder + fresh-items heading

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `app.js` wiring — fetch, adopt, tag

**Files:**
- Modify: `frontend/src/app.js` only (not unit-tested by repo convention):
  - import line 7 (add `loadReviewItems`)
  - `answerCheck` (lines 968-980) + new `fetchFreshItems` helper + `advanceAfterLesson` (lines 982-997) — one combined edit, contiguous block
  - `startReviewSession` (lines 999-1016)

**Interfaces:**
- Consumes: `loadReviewItems({ fetch, courseId, lessonId })` from Task 2 (`frontend/src/courses.js`); the `state.freshPending`/`state.freshItems` render contract from Task 2 (`frontend/src/views/lesson.js`, `frontend/src/views/checks.js`); existing in-scope identifiers `ui`, `fetch`, `paintLesson`, `log`, `gradeCheck`.
- Produces: `fetchFreshItems(ls, lesson)` helper; `ls.freshPending` / `ls.freshItems` flags; `lesson.checks` swapped in place on adoption; `source: "review"` added to the `lesson_check` event payload when `state.freshItems`.

- [ ] **Step 1: Add `loadReviewItems` to the import**

Change (currently line 7):

```js
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply, submitCapstone } from "./courses.js";
```

to:

```js
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews, loadReviewItems, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply, submitCapstone } from "./courses.js";
```

- [ ] **Step 2: Tag `answerCheck`, add `fetchFreshItems`, wire it into `advanceAfterLesson`**

Replace the whole block from `answerCheck` through the end of `advanceAfterLesson` (currently lines 968-997):

```js
  function answerCheck(i, answer) {
    const check = ui.lesson.checks && ui.lesson.checks[i];
    if (!check || ui.lessonState.checkResults[i]) return;
    const result = gradeCheck(check, answer);
    ui.lessonState.checkAnswers[i] = answer;
    ui.lessonState.checkResults[i] = { correct: result.correct };
    log("lesson_check", {
      courseId: ui.courseId,
      topicId: ui.lesson.id,
      payload: { index: i, type: check.type, correct: result.correct },
    });
    paintLesson();
  }

  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (ui.screen !== "lesson") return; // navigated away while loading the next review
      ui.lesson = lesson;
      if (lessonFailed(ui.lesson)) { await refreshSummary(); if (ui.screen !== "lesson") return; showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    if (ui.screen !== "lesson") return; // navigated away — don't yank them to the dashboard
    showCourse();
  }
```

with:

```js
  function answerCheck(i, answer) {
    const check = ui.lesson.checks && ui.lesson.checks[i];
    if (!check || ui.lessonState.checkResults[i]) return;
    const result = gradeCheck(check, answer);
    ui.lessonState.checkAnswers[i] = answer;
    ui.lessonState.checkResults[i] = { correct: result.correct };
    log("lesson_check", {
      courseId: ui.courseId,
      topicId: ui.lesson.id,
      payload: {
        index: i, type: check.type, correct: result.correct,
        ...(ui.lessonState.freshItems ? { source: "review" } : {}),
      },
    });
    paintLesson();
  }

  // Fires the fresh-retrieval-items generation for a review lesson right after its
  // lessonState is created. Sets freshPending synchronously — before the caller's first
  // paint — so the placeholder shows immediately. On resolve, adopts the items onto the
  // CAPTURED lesson/lessonState only if the learner is still on that same lessonState
  // (capture-then-guard, per sendWsChat's onScreen idiom) and hasn't already answered
  // with the original checks. Every outcome clears freshPending; repaint only happens
  // while still on the lesson screen for this same lessonState.
  function fetchFreshItems(ls, lesson) {
    ls.freshPending = true;
    loadReviewItems({ fetch, courseId: ui.courseId, lessonId: lesson.id }).then((res) => {
      if (ui.lessonState === ls && !res.error && Array.isArray(res.items) && res.items.length
          && Object.keys(ls.checkResults).length === 0) {
        lesson.checks = res.items;
        ls.freshItems = true;
      }
      ls.freshPending = false;
      if (ui.lessonState === ls && ui.screen === "lesson") paintLesson();
    });
  }

  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (ui.screen !== "lesson") return; // navigated away while loading the next review
      ui.lesson = lesson;
      if (lessonFailed(ui.lesson)) { await refreshSummary(); if (ui.screen !== "lesson") return; showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
      fetchFreshItems(ui.lessonState, ui.lesson);
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    if (ui.screen !== "lesson") return; // navigated away — don't yank them to the dashboard
    showCourse();
  }
```

- [ ] **Step 3: Wire `fetchFreshItems` into `startReviewSession`**

Replace `startReviewSession` (currently lines 999-1016):

```js
  async function startReviewSession() {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "review-loading";
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

with:

```js
  async function startReviewSession() {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "review-loading";
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
    fetchFreshItems(ui.lessonState, ui.lesson);
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

- [ ] **Step 4: Run the import-resolution check**

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected output: `imports ok`

- [ ] **Step 5: Run both test suites as a regression check**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS (app.js has no direct unit tests, but this proves Task 2's view/wrapper changes still pass with app.js now consuming them).
Run: `.venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app.js
git commit -m "$(cat <<'EOF'
feat(review-items): wire fresh item fetch/adopt/tag in app.js

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

Checked against `docs/superpowers/specs/2026-07-16-fresh-review-items-design.md`, item by item:

- **Replace, not append; fallback to original checks on any failure/timeout/early-answer** — Task 3's `fetchFreshItems` only swaps `lesson.checks` when `ui.lessonState === ls`, `!res.error`, `res.items.length`, and `Object.keys(ls.checkResults).length === 0`; every other path leaves the original checks untouched. Covered.
- **Cache stamp = review count of `lesson_reviewed` events** — Task 1 route computes `review_count = len(srs.reviews_by_lesson(conn, course_id).get(lesson_id, []))`; `ensure_review_items`/`finalize_items` stamp and compare it. Covered.
- **No new event type; `source: "review"` tag only** — Task 3's `answerCheck` adds `source: "review"` to the existing `lesson_check` payload only when `state.freshItems`; no new event type anywhere in any task. Covered.
- **`review_items_prompt` contents** (title+module, objectives w/ fallback, spine block omitted when absent, no-repeat instruction over existing prompts, exactly-2 demand with 1-2 validated, mcq/fill check shape, mcq self-check paragraph verbatim, JSON-only instruction, `{"items":[...]}` shape) — all present, each covered by its own prompt test in Task 1 Step 1/5.
- **`valid_review_items`** (dict, 1-2 items, each `generation.valid_check`) — Task 1, tested directly.
- **`finalize_items`** (sanitize prompt/explanation/choices, mcq answer int kept, fill answer verbatim, explicit-fields-only, `{"lessonId","reviewCount","items"}` shape) — Task 1, tested directly including the dropped-unknown-key assertion.
- **`save_items`/`load_items`/`_path`** at `content/courses/<course_id>/review-items/<lesson_id>.json` via `fsutil.write_text_atomic`, corrupt-reads-as-missing — Task 1, tested with a literal corrupt-file write.
- **`ensure_review_items`** cache-hit-on-matching-stamp (remediation.ensure_session shape) — Task 1, tested for reuse, stamp-change regeneration, and corrupt-cache regeneration.
- **`prune`** called from `apply_revision` alongside `remediation.prune`, unlocked — Task 1 Step 8, tested with `test_apply_revision_prunes_review_items`.
- **Route contract**: both ids `_ID_RE`-gated, 404 on unknown course/lesson, lesson file NOT required, `review_count` from `srs.reviews_by_lesson`, `lesson_meta` from `flatten_lessons`, `spine_entry` from `spine.load_spine`, `existing_checks` from cached lesson file (else `[]`), `generate` lambda over `run_structured`, wrapped in `_gen_lock`, `{"items":[...]}` response, 503/502 error mapping — Task 1 route + all 6 new route tests.
- **`loadReviewItems`**: `{error}` fallback idiom + 60s `AbortController` timeout, abort maps to `{error}` — Task 2, tested (signal wiring + abort-to-error mapping; see Ambiguity resolution 7 for why the literal 60s wait isn't exercised).
- **`lesson.js` placeholder** while `isReview && freshPending` post-reveal, **heading swap** when `freshItems`, **non-review byte-identical** — Task 2, all three asserted directly in `views.test.js`.
- **CSS**: minimal `.checks-pending` rule, `var(--text-dim)` confirmed declared in `:root` (styles.css:10) — Task 2 Step 6.
- **`fetchFreshItems(ls, lesson)`**: called from both `startReviewSession` and `advanceAfterLesson` immediately after `lessonState` creation; `freshPending = true` set synchronously before first paint; capture-guard on resolve; adopts only when checkResults empty, no error, items present; sets `ls.freshItems = true`; `freshPending` always cleared; repaint only when still on the lesson screen — Task 3, matches the spec's description line for line.
- **`answerCheck` source tag** — Task 3.
- **Fast-rating race** — no special-case code needed: the capture-guard (`ui.lessonState === ls`) alone discards a late-arriving result once `advanceAfterLesson`/`startReviewSession` has replaced `ui.lessonState` for the next lesson — inherent in the guard, documented in the code comment.
- **Security**: `sanitize_html` on every learner-facing field, fill answer verbatim, explicit-fields-only, spine text never sent to the browser raw (only sanitized generated text derived from it is), path ids `_ID_RE`-gated before any filesystem access — Task 1.
- **Error handling**: generation failure/timeout/offline → original checks stand (Task 2/3); corrupt cache → regenerate (Task 1, tested); malformed/forged ids → 404 never 500 (Task 1, tested).
- **Testing** — every backend and frontend test bullet from the spec's Testing section is present across Task 1 (19 backend tests) and Task 2 (9 frontend tests) plus Task 3's import-resolution check.
- **Deploy notes** — no schema/data change; `review-items/` is created lazily via `path.parent.mkdir(parents=True, exist_ok=True)` in `save_items`, same as every other per-course subdirectory in this codebase. No action needed beyond the standard `docs/DEPLOY.md` procedure.
- **Out of scope** — no batching, no pre-generation, no difficulty adaptation, no exam/capstone changes anywhere in any task. Confirmed by scope of files touched (review_items.py, one app.py route, one courses.py prune call, and the frontend files listed above only).

**Placeholder scan:** no `TODO`, `FIXME`, or `...` stub code in any task's implementation snippets — every function body above is complete, runnable code.

**Type/name consistency across tasks:**
- `loadReviewItems({ fetch, courseId, lessonId })` — defined in Task 2 Step 3, imported and called identically in Task 3 Step 1/2.
- `res.items` (array) — the exact shape Task 1's route returns (`{"items": result["items"]}`) and Task 3's `fetchFreshItems` reads (`Array.isArray(res.items)`).
- `state.freshPending` / `state.freshItems` — set only in Task 3 (`ls.freshPending`, `ls.freshItems`), read only in Task 2's `checksHTML`/`lessonHTML`. Same two field names used everywhere, no aliasing.
- `ensure_review_items(content_dir, course_id, lesson_id, review_count, *, lesson_meta, spine_entry, existing_checks, generate)` — defined in Task 1 Step 3, called with identical keyword names from the Task 1 route (Step 7) and every Task 1 test.
- `source: "review"` — the exact literal string in Task 3's `answerCheck`; no other spelling used anywhere.

No spec contradictions found.
