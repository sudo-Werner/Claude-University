# Mastery Loop — Design

**Date:** 2026-07-15. **Sub-project D** of the Claude University roadmap.

**Decided with Werner:** soft gating on modules + a hard-locked course final; remediation = generated
corrective session ("Fix the gaps") + weak-spot SRS scheduling; a global transcript page; mid-lesson
production checkpoints deferred to their own sub-project. Signal wiring and stats whitelists are
routine under the charter. Werner granted overnight autonomous execution through deploy
(2026-07-15 22:28 CEST directive).

## Why

Sub-project C produces evidence (exam results per objective/lesson) but nothing acts on it: mastery
badges ignore exams and explain-it-back, failure leads nowhere except a free retake, the
"comprehensive" final can be sat before proving a single module, and no record of achievement
exists. D closes Bloom's mastery loop: evidence feeds mastery, failure triggers a corrective path,
the final is earned, and a transcript records it.

## 1. Signal wiring into mastery

`mastery.level_for` keeps its ladder (attempted/familiar/proficient/mastered) and reps-cap logic;
only the per-lesson accuracy pool that caps levels widens:

- `lesson_check` items: weight 1 (unchanged). Includes remediation practice — see section 2.
- `lesson_explained` verdicts: correct = 1 point, close = 0.5, incorrect = 0; weight 1 per event.
- `exam_result` per-question points (each question carries `lessonId`; payload `perQuestion` has
  `points` 1/0.5/0): **weight 2** per question — summative evidence under exam conditions outweighs
  a formative check. Every recorded attempt counts (all evidence, not just the latest).
- `prequiz_attempt` is **deliberately excluded** from mastery: the pre-quiz precedes instruction, so
  counting it penalizes not-yet-taught knowledge. It is a diagnostic. (It does count toward the
  streak — section 5.)

Accuracy = weighted points / weighted total across the pool. No new mastery levels, no schema
change. Weak exam performance drags lesson badges down, which flips `performance_summary` toward
"reinforce fundamentals" — generation adaptation now sees summative evidence.

## 2. Remediation — "Fix the gaps" (Bloom's corrective loop)

On a failed exam the result screen gains a **"Fix the gaps"** button.

- `POST /api/courses/<cid>/exams/<exam_key>/remediation` reads the **latest failed** `exam_result`
  for that exam key (404 if none, or if the latest result is a pass) and makes ONE Claude call
  producing a corrective session: for each weak-spot objective, a short re-explanation **explicitly
  prompted to take a different angle than the lesson** (analogy, worked example, contrast — not a
  summary), plus 2–3 fresh check-style practice items (mcq or fill, same shape as lesson checks).
  Validated with bounded retries → 502 on failure (result screen stays intact); sanitized
  server-side with the same boundary as lessons (explanations and practice prompts/choices render
  raw client-side; everything else escaped client-side).
- Persisted atomically to `content/courses/<cid>/remediation/<exam_key>.json` stamped with the
  attempt number it remediates. A repeat request re-serves the stored session free; a newer failed
  attempt (higher attempt number) regenerates; corrupt file → regenerate. Generation runs under
  `_gen_lock(("remediation", course_id, exam_key))`.
- `GET` of the same path returns the stored session if fresh (matching latest failed attempt),
  else 404 — so a page refresh never costs a Claude call.
- Frontend remediation screen: per gap, the re-explanation, then practice items graded client-side
  exactly like lesson checks. Practice answers log `lesson_check` events with the gap's real
  `lessonId` as `topic_id` and `payload.source = "remediation"` — they feed the mastery pool with
  zero new mastery code. A "Retake exam" CTA closes the screen's loop; opening the session logs
  `remediation_started` (course-level, `topic_id = exam_key`).
- **SRS follow-up (derived, never mutated):** `srs.due_lesson_ids` gains one rule — a lesson is
  also due when the latest `exam_result` for an exam covering it (its module's exam or the final)
  is a fail listing it in `weakSpots`, and that result is more recent than the lesson's last
  review. Reviewing clears it naturally; a later passed attempt clears it. Pure event derivation,
  revision-safe, no SM-2 corruption. `reviews_due_count` picks this up for free.
- `apply_revision` prunes remediation files for dropped modules, mirroring exam/spine pruning.

## 3. Gating — soft on modules, hard on the final

- **Locked final:** the start-exam route returns **409** `{"error": ...}` for `exam_key = "final"`
  until every module exam is passed (computed from `exam_status` on the current manifest). The
  submit route needs no gate (nothing pending can exist). The curriculum's final row shows
  "Locked — pass all module exams" instead of the Take-exam button; the course payload already
  carries `exams`, so the client can compute lock state without a new field.
- **Soft module gating (client-side, no new API):** the curriculum computes a single
  **recommended next** step — the first incomplete lesson in manifest order, or, if a module's
  lessons are all complete but its exam unpassed, that exam — shown as a chip on that row. Any
  module the learner has moved beyond (a later module has a completed lesson) whose exam is
  unpassed gets an "exam not passed" flag on its header. Nothing ever locks at module level.

## 4. Global transcript

- `GET /api/transcript`: for every course — title, per-module rows (module title, best score,
  attempts, passed, date first passed from `exam_result` timestamps), the final row, coursePassed,
  and mastery counts. Computed live from events + manifests; nothing stored; deleted courses
  simply absent.
- A **Transcript** screen reachable from home, styled as an academic record in the warm-glass
  theme, with an explicit line that it records learning and is not a credential (charter). Scores
  and titles are plain text (esc()'d client-side).

## 5. Stats whitelists

- `STUDY_EVENTS` += `exam_result`, `remediation_started`, `prequiz_attempt` (all are studying;
  streak counts them).
- `ACTIVITY_EVENTS` += `exam_result`, `remediation_started`. The activity log resolves exam topic
  ids (module id or "final") to "Module-title exam" / "Final exam" labels and shows score/passed
  from the payload for `exam_result` rows.

## Not in scope

Mid-lesson checkpoints (own sub-project later), hard module gating, certificates, changes to exam
generation/grading/blueprints, changes to SM-2 math, per-course record sections (global page only).

## Risks / honest caveats

- Corrective quality depends on one LLM call; mitigations: same bounded-retry validation as
  lessons, practice items are objectively gradable, and the retake remains free regardless.
- Double-weighting exam evidence is a judgment call; the constant lives in one place
  (`mastery.EXAM_WEIGHT = 2`) and is trivially tunable.
- The weak-spot due rule can make many lessons due at once after a bad final — accepted; that is
  what "you have gaps" means, and reviewing clears them.

## Testing

Backend: accuracy-pool math (weights, explain verdict mapping, prequiz exclusion, remediation
checks counted via source-tagged lesson_check), locked-final 409 + unlocked after passes,
remediation route contracts (404 no-fail/latest-pass, fresh vs stale persistence, corrupt file
regenerate, 502 keeps result reachable, prune on revision), SRS weak-spot due rule (set on fail,
cleared by review and by later pass, revision-safe), transcript assembly (dates, best scores,
deleted course absent), stats whitelists + exam label resolution. Frontend: remediation screen
render/grade/log, transcript render, final lock row, recommended-next chip + module flag logic,
stale-screen guards, app.js import check. Full suites: `.venv/bin/pytest`,
`node --test frontend/tests/*.test.js`.
