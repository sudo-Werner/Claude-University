# Fresh retrieval items for review sessions — design

**Date:** 2026-07-16. **Status:** approved (Werner interview 2026-07-16). Second slice of the
Claude-in-lessons wave (deep dive item 2, `docs/research/2026-07-15-claude-in-lessons-deep-dive.md`).

## Goal

When a lesson comes up for review, Claude generates 1-2 **fresh** retrieval questions from the
lesson's objectives and knowledge-spine entry, and the review serves those instead of
re-serving the lesson's original checks. Varied retrieval items beat repeated identical ones
(Butler 2010); identical-item re-testing decays fast (Roediger & Karpicke). This upgrades the
re-answer-before-rating gate that shipped with the pedagogy fixes.

## Decisions

1. **Replace, not append** (Werner, 2026-07-16). The review serves ~2 fresh questions
   *instead of* the lesson's original checks. If generation fails, times out, or the learner
   answers before items arrive, the review falls back to the original checks — today's
   behavior, unchanged.
2. **Cache stamp = review count** (self-approved; the remediation attempt-stamp idiom). Items
   are cached per lesson, stamped with the number of `lesson_reviewed` events for that lesson
   at generation time. Re-serving within one review pass (reload, retry) is free; the next
   review session regenerates. A same-day "again" retry counts as a new session and gets
   fresh items — pedagogically correct, costs one extra small call.
3. **No new event type** (self-approved). Answers log as `lesson_check` events with
   `source: "review"` in the payload — mastery, stats, SRS, and the remediation retake gate
   (which filters `source == "remediation"` plus examKey/attempt) all need zero changes.

**Cost shape** (surfaced to Werner with the design): one small non-web `run_structured` call
per due lesson per review session (~15-40s on the Pi, far smaller than a lesson generation),
fired in the background while the learner reads. Max-plan quota, not API dollars. Re-opens
free. Five due lessons = five small calls.

## Approach

A new backend module `backend/review_items.py` mirroring `backend/remediation.py`, which is
the direct precedent: fresh practice items in the exact lesson-check shape
(`generation.valid_check`), generated from objectives + spine, sanitized field-by-field,
cached as a stamped JSON file, graded client-side by the existing `gradeCheck`, logged as
source-tagged `lesson_check` events.

Rejected alternatives: **batching all due lessons into one generation call** — cheaper per
session but the cache key becomes the churning due-set, one failed call blocks the whole
review, and per-lesson latency already hides behind reading time (revisit only if latency
bites); **a new event type** — requires whitelist edits in mastery.py:49 plus decisions in
stats.py:9-15 for zero benefit over a source tag; **server-side grading** — the formative
check idiom ships answers to the client by design (app.py:172-174); exams remain the
integrity surface.

## Backend design

### New module `backend/review_items.py`

- `review_items_prompt(lesson_meta, spine_entry, existing_check_prompts)` — builds the
  generation prompt from: lesson title + module title; the lesson's objectives
  (`{text, bloom, knowledge}` lines; title-derived fallback when absent, the
  `exams._fallback_objective` idiom); the lesson's spine entry
  (`{summary, concepts: [{term, definition}]}`, may be absent on legacy courses — omit the
  block); and the original check prompts under an explicit "do NOT repeat or lightly reword
  these existing questions" instruction. Demands exactly 2 items (validator accepts 1-2) in
  the lesson-check shape, mix of mcq and fill where content allows, the remediation prompt's
  quality rules verbatim where applicable: fill answers must be "the exact word or short
  phrase", the mcq self-check paragraph ("re-answer each mcq independently... no distractor
  also defensibly correct"), "Reply with ONLY a JSON object, no prose, no fence".
  Output shape: `{"items": [<check>, <check>]}`.
- `valid_review_items(obj)` — pure predicate: dict with `items` a list of 1-2 objects each
  passing `generation.valid_check` (generation.py:191-205). Passed as `validate=` to
  `claude_client.run_structured` (one corrective retry then `ClaudeError` — no custom retry).
- `finalize_items(obj, lesson_id, review_count)` — explicit-fields-only copy (never persist
  unknown model keys, remediation.py:129-136 idiom): `prompt`/`explanation`/`choices` through
  `generation.sanitize_html`, mcq `answer` int kept, fill `answer` kept **verbatim**
  (client-side grading compares learner typing). Returns
  `{"lessonId", "reviewCount", "items": [...]}`.
- `save_items` / `load_items` / `_path` — JSON file at
  `content/courses/<course_id>/review-items/<lesson_id>.json` via
  `fsutil.write_text_atomic`; `load_items` returns None on missing/corrupt/wrong-shape
  (corrupt-reads-as-missing).
- `ensure_review_items(content_dir, course_id, lesson_id, review_count, *, lesson_meta,
  spine_entry, existing_checks, generate)` — serve the stored file when
  `existing.get("reviewCount") == review_count`, else generate → finalize → save → return
  (remediation.ensure_session:187-201 shape). Route wraps it in
  `generation._gen_lock(("review-items", course_id, lesson_id))` with a cache re-check
  inside the lock.
- `prune(content_dir, course_id, keep_lesson_ids)` — delete files for lesson ids no longer
  in the syllabus; called from `courses.apply_revision` alongside the existing
  `remediation.prune` (same unlocked at-worst-one-stale-file rationale).

### Route (`backend/app.py`)

`GET /api/courses/<course_id>/lessons/<lesson_id>/review-items`

- Both ids validated against `_ID_RE` (404 otherwise); 404 when the course manifest or the
  lesson id is unknown; the lesson's cached lesson file is NOT required (items come from the
  manifest + spine, not the lesson body).
- `review_count = len(srs.reviews_by_lesson(conn, course_id).get(lesson_id, []))` — the
  stamp. Uses the existing conn try/finally idiom.
- `lesson_meta` from `courses.flatten_lessons` (id, title, moduleTitle, objectives);
  `spine_entry` from `spine.load_spine(...)["lessons"].get(lesson_id)`; `existing_checks`
  prompts from the cached lesson file when present (empty list when not — legacy lessons).
- `generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)`
  (non-web; the exam/remediation precedent).
- Response `{"items": [...]}` (sanitized at finalize). Errors: `ClaudeAuthError` → 503
  `{"error", "code": "reauth"}`; `ClaudeError` → 502 `{"error": <short friendly message>}`.
- GET-with-generation matches the existing lesson GET idiom.

## Frontend design

### `frontend/src/courses.js`

`loadReviewItems({ fetch, courseId, lessonId })` — wrapper following the existing `{error}`
fallback idiom, with a **60s AbortController timeout** so a hung generation degrades to the
original checks instead of holding the learner (the server timeout is 240s; plain HTTP is not
a secure context but AbortController is not secure-context gated).

### `frontend/src/app.js` (not unit-tested; import-check before deploy)

- A `fetchFreshItems(ls, lesson)` helper called from both `startReviewSession` and
  `advanceAfterLesson` right after the review `lessonState` is created: set
  `ls.freshPending = true`, fire `loadReviewItems`; on resolve, capture-guard
  (`ui.lessonState === ls`) and adopt only when nothing is answered yet
  (`Object.keys(ls.checkResults).length === 0`): swap `lesson.checks = res.items` on the
  captured lesson object, set `ls.freshItems = true`. In every outcome set
  `ls.freshPending = false` and repaint only when still on the lesson screen. On error,
  timeout, or late arrival: no swap — the original checks stand.
- Swapping `lesson.checks` in place means `ratingLocked`, `suggestedQuality`, `checksHTML`,
  and `answerCheck` all work **unchanged** — the client lesson object is a per-load fetch,
  never a shared cache (courses.js fetches fresh every time).
- `answerCheck`: when `state.freshItems`, the `lesson_check` payload additionally carries
  `source: "review"`. Fallback answers (original checks) log exactly as today.
- Fast-rating race (legacy no-checks lesson rated before items arrive): the capture-guard
  discards the late result; that lesson simply misses fresh items this session. Self-heals
  next session.

### `frontend/src/views/lesson.js`

- While `state.isReview && state.freshPending` and the solution is revealed, the checks area
  renders a static placeholder — *"Preparing fresh review questions…"* — instead of
  `checksHTML`. Rating stays locked by the original checks count until the swap or fallback
  resolves (at most 60s).
- When `state.freshItems`, the checks heading indicates fresh items (e.g. "Fresh review
  questions"), so the learner knows these are not the lesson's originals. Non-review
  rendering byte-identical to today.

## Security

- Every learner-facing generated string (`prompt`, `choices`, `explanation`) passes
  `generation.sanitize_html` server-side before persisting — `checksHTML` injects these RAW.
  Fill `answer` stays verbatim (grading contract). Explicit-fields-only copying; unknown
  model keys never reach the stored file.
- Spine text remains generation-side only; it enters prompts as-is, and everything derived
  from it for the browser goes through sanitize.
- `lesson_check` events remain client-forgeable formative signals — no new server read path
  over them is added (mastery already parses defensively). The `source: "review"` tag cannot
  trip the remediation retake gate (which also requires examKey + attempt).
- Path ids gated by `_ID_RE` before any filesystem access.

## Error handling

- Generation failure, timeout, or offline → client falls back to the original checks; the
  review is never blocked. The 60s client abort caps how long the placeholder can hold.
- Corrupt cache file → treated as missing → regenerate.
- Malformed/forged request ids → 404, never 500.

## Testing

- **Backend** (`.venv/bin/pytest -q`, monkeypatched `generate`): `valid_review_items`
  accept/reject (0 items, 3 items, non-list, bad check shapes); prompt contains objectives,
  spine terms, no-repeat instruction, JSON-only instruction; objectives/spine-absent
  fallbacks; `finalize_items` sanitizes prompt/choices/explanation, keeps fill answer
  verbatim, drops unknown keys; `ensure_review_items` cache hit on matching stamp (generate
  NOT called), regenerate on stamp change, corrupt file regenerates; `prune` removes only
  dropped ids; route: bad ids → 404, unknown lesson → 404, `ClaudeAuthError` → 503 reauth,
  `ClaudeError` → 502, success → `{"items": [...]}`, review_count derived from seeded
  `lesson_reviewed` events; `apply_revision` calls the new prune.
- **Frontend** (`node --test frontend/tests/*.test.js`): placeholder renders only when
  `isReview && freshPending` post-reveal; fresh-items heading when `freshItems`; non-review
  markup byte-identical; `ratingLocked`/`suggestedQuality` against a swapped 2-item set
  (existing behavior, new fixture). Plus the app.js import-resolution check.

## Deploy notes

No schema or data changes; the `review-items/` subdir is created lazily per course. Standard
`docs/DEPLOY.md` procedure (no `--delete`, verify `/api/health` and all 4 courses).

## Out of scope

- Batching generation across due lessons (revisit if per-lesson latency is ever visible).
- Pre-generating items before a lesson is due; offline review support (reviews are
  online-only today).
- Item difficulty adaptation from past performance (misconception profile is a later slice).
- Any change to exam/capstone integrity surfaces.
