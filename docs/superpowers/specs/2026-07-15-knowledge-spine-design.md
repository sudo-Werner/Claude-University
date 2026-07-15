# Knowledge Spine: Cross-Lesson Coherence — Design

**Date:** 2026-07-15. **Decided with Werner:** continuity + explicit callbacks (lessons build on prior material, use one vocabulary, and reference earlier lessons by title); one-time backfill so the four live courses benefit immediately.

## Why

Today a lesson generation prompt knows the course brief, the lesson's own title/module/position, and its objectives — nothing about what any other lesson actually taught. Each lesson is written blind: concepts get re-explained, terminology drifts between lessons, and nothing ever says "as you saw earlier". Sub-project B (roadmap: knowledge/coherence) fixes this with a per-course *knowledge spine*.

## The spine

- **File:** `content/courses/<course_id>/spine.json` — server-side only, never sent to the browser (no new sanitization surface). Shape:
  `{"lessons": {"<lesson_id>": {"summary": "<one sentence>", "concepts": [{"term": "...", "definition": "<one sentence>"}]}}}`
- Written atomically (`fsutil.write_text_atomic`); read-modify-write is guarded by the existing `_gen_lock` keyed `("spine", course_id)` so concurrent lesson generations in one course cannot lose updates. Missing or corrupt file reads as `{}` (same policy as manifests).

## Harvest (generation side)

- `lesson_prompt` asks for one more JSON key: `spine` — `{"summary", "concepts": [1–4 {"term","definition"}]}` — plain text (no HTML), naming the concepts THIS lesson introduced, with the exact term names used in the lesson body.
- `valid_lesson` requires a valid `spine` entry (new `valid_spine_entry`), exactly like `preQuiz` became required: cached lessons are never re-validated, `_reviewed_lesson` fails open, generation retries are bounded — so no back-compat break.
- `_generate_and_store_lesson` pops `spine` off the lesson before caching (spine.json is the single source of truth; the lesson file keeps its existing shape) and upserts it into spine.json. Deepen/regenerate overwrites the entry.

## Inject (generation side)

- When generating a lesson at position N, the prompt gains a "what the learner already covered" block built from all syllabus-earlier lessons (positions 1..N-1), in order:
  - Lesson **with** a spine entry: title + its concepts (term — definition).
  - Lesson **without** one (not yet generated): title + its syllabus objectives, marked as planned — assume familiarity at objective level only.
- Prompt-size control: the most recent 8 earlier lessons get full definitions; older ones contribute terms + summary only. Entries are single lines; a 30-lesson course stays a few KB.
- Instructions in the prompt: build on this material, do NOT re-teach it; reuse these EXACT terms; where natural (at most 1–2 times), reference an earlier lesson by its **title** ("As you saw in 'Recursion basics'…"). Titles, not numbers — course revision renumbers lessons.
- Lesson 1 of a course gets no block. Reviews/grading/explain are untouched (they don't generate lessons).

## Backfill (one-off)

- `backfill_spine(content_dir, course_id, *, generate)` in a new `backend/spine.py`: reads every already-cached lesson missing from spine.json, batches them (up to 10 lesson bodies per Claude call), asks for `{lesson_id: {summary, concepts}}`, validates each entry, merges. Idempotent — already-present ids are skipped, so it can be re-run safely.
- Invoked via `python -m backend.spine` (small `__main__` block iterating all courses), run once on the Pi after deploy using the existing `claude_client.run_structured` (no web search needed).

## Housekeeping

- `apply_revision` prunes spine entries whose lesson ids left the syllabus. Injection iterates current syllabus ids only, so stale entries are harmless even before pruning.
- Known limitation (accepted): already-cached lessons don't retroactively gain callbacks — the spine changes future generations only, consistent with how pre-quiz shipped.

## Not in scope

No frontend changes. No mastery/SRS changes. No compile-time spine seeding beyond the objectives fallback. No capstone/bibliography prompt changes.

## Testing

Backend only: spine load/save/upsert (missing, corrupt, lock-free correctness), `valid_spine_entry`, `valid_lesson` requires spine, `lesson_prompt` contains the harvest instruction and the injected block (with-entry, objectives-fallback, recent-8 cap, lesson-1 empty), `_generate_and_store_lesson` pops spine from the cached file and writes spine.json, `apply_revision` prunes, backfill batching/merge/idempotency with a mocked generator. Existing lesson fixtures gain a `spine` field (same ripple as preQuiz).
