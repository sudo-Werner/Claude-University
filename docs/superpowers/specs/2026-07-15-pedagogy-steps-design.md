# Pedagogy Steps: Pre-Quiz + Explain-It-Back — Design

**Date:** 2026-07-15. **Decided with Werner:** pre-quiz is a dedicated generated question (not a reused check); pre-quiz must be attempted, explain-it-back is skippable.

## Why

Two of the strongest effects in learning science are missing from the lesson flow:
- **Pretesting**: attempting a question BEFORE studying measurably improves retention, even when the attempt is wrong. Currently a lesson opens straight into the exercise body.
- **Self-explanation / retrieval**: saying the idea back in your own words is a stronger test than recognition. Currently the lesson ends with recognition checks and a self-rated recall button.

Together these close charter item #4's remaining half (graded production, not just recognition).

## Pre-quiz (before the lesson body)

- **Data:** new lesson field `preQuiz` — exactly one item in the existing check shape (`{type:"mcq"|"fill", prompt, choices?, answer, explanation}`). Generated in the SAME `claude -p` call as the rest of the lesson (a few extra tokens, no extra latency pass). Validated with the existing `valid_check`; sanitized exactly like `checks`.
- **Prompt intent:** one warm-up question on the lesson's single core idea, attemptable with intuition or general prior knowledge — it must NOT require a term or fact only this lesson introduces (it is answered pre-learning). The `explanation` doubles as a one-sentence preview of the key insight, shown right after the attempt.
- **Back-compat:** `valid_lesson` requires `preQuiz`, so every NEW or deepened lesson has one. Cached lessons without it simply skip the pre-quiz (served as-is, never re-validated). The audit/rewrite pass carries the field through (full lesson JSON in, full lesson JSON out; an invalid rewrite already falls back to the original).
- **Flow:** on opening a lesson that has `preQuiz` and is NOT completed (no entry in the course's mastery map) and NOT part of a review session, the lesson screen shows a pre-quiz card instead of the exercise: question + choices/fill input. The learner must submit an attempt (one tap for mcq); then correct/incorrect + the explanation appear with a "Start the lesson" button. Graded client-side with the existing `gradeCheck`. Event `prequiz_attempt` `{correct, type}` is logged.
- Reviews and already-completed lessons go straight to the exercise, as today.

## Explain-it-back (after the solution)

- **Flow:** once the solution is revealed, a card appears below the concept checks: "Explain it back — in your own words, what is the core idea?" Textarea + "Get feedback". Entirely skippable — the recall rating buttons work regardless.
- **Grading:** new route `POST /api/courses/<cid>/lessons/<lid>/explain` `{explanation}` → `{verdict, note}`. Mirrors the existing `/grade` pipeline: `generation.explain_answer` builds `explain_prompt` (judge understanding of the core idea from the lesson body + reference solution; not wording, not completeness), reuses `valid_grade` (`correct|close|incorrect`) and `run_structured`, sanitizes the note. Frontend reuses the existing grade result styling.
- **Event:** `lesson_explained` `{verdict}` logged on each successful grading. Not yet consumed by `mastery.py` — sub-project D (mastery loop) will formalize how production-quality signals gate progression; logging now builds the history it will need.

## Not in scope

- No mastery/SRS changes (D). No changes to reviews. No regeneration of cached lessons (they gain a pre-quiz only when deepened/regenerated). `prequiz_attempt`/`lesson_explained` are NOT added to the activity-log or streak whitelists (streak already counts `lesson_view`).

## Testing

Backend: `valid_lesson` preQuiz requirement, sanitization, prompt content, `explain_answer` + route (mirroring existing grade tests). Frontend: pre-quiz card rendering/grading states, stage-gated `lessonHTML`, explain card states, fetch helper — plus the app.js import-resolution check.
