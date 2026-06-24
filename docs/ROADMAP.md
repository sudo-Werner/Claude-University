# Claude University — Roadmap to the Vision

**Derived from:** [CHARTER.md](CHARTER.md) + [research/online-universities-reference.md](research/online-universities-reference.md)
**Updated:** 2026-06-23

Ordered sequence of slices to "finish" the system. Each is its own brainstorm → spec → plan →
subagent build → deploy cycle. I execute these autonomously under the charter; this file is the
steering map and gets updated as slices land. Items can be re-ordered if reality demands.

## Status so far (shipped + deployed)
- Foundation: Flask+SQLite backend, event log, profile/diagnostic, offline-first sync, styled
  screens, session timer.
- Slice 1 — multi-course foundation (JSON courses, per-course progress from events, home→course→lesson).
- Slice 2 — conversational course creation + just-in-time lesson generation (Pi Max-subscription `claude -p`).
- Slice 3 — empty start + fixed add-course composer.

## The remaining slices

### Slice 4 — Spaced-repetition engine (the #1 pillar) ✅ SHIPPED 2026-06-23
**Closes:** done-item 1. Deployed: Anki-style recall rating → SM-2 schedule from `lesson_reviewed`
events, real per-course reviews-due, `/reviews` endpoint, Review session. Verified on the Pi.
**Why first:** biggest missing learning pillar, and it's *unblocked* — it can run on an
**Anki-style self-rated recall signal** after each lesson (Again / Hard / Good / Easy), so it does
not depend on auto-grading.
**Scope:** SM-2/FSRS scheduling with four cheap per-lesson fields (`repetitions`, `interval_days`,
`ease_factor`, `next_review_date`) derived from review events; a post-lesson recall rating; the
per-course "reviews due" count becomes real; a **review surface** that resurfaces due lessons
(re-presenting the exercise, not regenerating). Scheduling state derived from the event log
(single source of truth), consistent with Slice 1.
**Depends on:** nothing new.

### Slice 5 — Checkable concept-check items + feedback ✅ SHIPPED 2026-06-24
**Closes:** done-item 3; advances 4. Deployed + Pi-verified: lessons carry a required `checks`
array (1–3 items, MCQ or fill-in-the-blank) generated alongside the exercise and sanitized
server-side; after the solution is revealed a "Check your understanding" section grades each answer
(correct/incorrect + explanation) and logs a `lesson_check` event `{index, type, correct}` — the
objective signal Slice 6 will consume. E2E confirmed: real generated lesson, mcq-wrong + fill-correct
graded, two `lesson_check` events landed.
**Depends on:** Slice 4 (the rating/review loop exists; checks feed it a better signal).

### Slice 6 — Adaptivity / mastery ✅ SHIPPED 2026-06-24
**Closes:** done-item 2. Deployed + Pi-verified: per-lesson mastery (attempted/familiar/proficient/
mastered) derived purely from the event log — SM-2 repetitions capped by `lesson_check` accuracy —
plus a course-level performance summary that makes lesson generation adapt (deeper/faster when
strong, reinforce fundamentals when struggling). Mastery exposed on `GET /api/courses/<id>`, shown
as a dashboard breakdown that refreshes after each lesson. E2E confirmed on a 2-lesson course: both
completed, mastery derived correctly, performance summary fed the second lesson's generation.
**Deferred (YAGNI):** dynamic curriculum reordering / inserted recap lessons / regenerating cached
lessons — adaptivity lives in the generation prompt, not in mutating the manifest. Per-lesson
mastery badges wait for Slice 7's curriculum view.
**Depends on:** Slices 4–5 (needs the performance signal).

### Slice 7 — Curriculum structure & lesson-player UX ✅ SHIPPED 2026-06-24
**Closes:** done-item 6 + the UX half of 4–5. Deployed + Pi-verified: a **curriculum accordion**
(modules→lessons with completion ✓, mastery badges, per-module + overall progress, tap any lesson to
open it — generating just-in-time on first open) reachable from the course dashboard's "View all
lessons"; a **lesson player nav bar** (Curriculum · Prev · Next, with "Step X of Y", Prev/Next
disabled at the ends). Pure frontend — completion/badges read from the Slice-6 mastery map; no
backend change. E2E confirmed on a 2-module course (jump to a non-next lesson, Prev/Next, completion
✓ + badge appearing after finishing a lesson).
**Adapted from the roadmap's "two-panel player":** the app is a deliberate ~448px phone-first
warm-glass column, so the curriculum is a dedicated accordion screen + a nav bar rather than a
desktop side panel. **Deferred (YAGNI):** generated metadata (`objectives[]`, `difficulty`); a
desktop wide layout; a separate home "Continue Learning" hero (the dashboard session card + grid
"Continue →" already cover it); mark-complete (lessons complete via the recall rating).
**Depends on:** Slices 4–6 (the player reflects mastery/reviews).

### Slice 8 — Content-quality safeguards + loose ends ✅ SHIPPED 2026-06-24 — ROADMAP COMPLETE
**Closes:** done-items 7, 8. Deployed + Pi-verified: Claude CLI auth failures are detected
(`ClaudeAuthError`, keyed on the CLI's `api_error_status` 401/403, content-safe — never text-scans a
successful generation) and surfaced as a clear "re-authenticate on the Pi" message on the lesson
screen and in the course-creation chat (no more silent/generic failure); generation rejects
empty/whitespace learner-facing fields and regenerates via the existing retry (a heuristic, not a
second LLM call — Pi-light); `<hr>` is allowed in the sanitizer; the dropped "streak" placeholder is
removed (UI + dead CSS). **All planned slices (1–8) are shipped.** The hourly loop now shifts to a
quality/maintenance pass (scan for bloat/dead code/non-SOTA patterns; keep the Pi light).
**Decision:** a true LLM self-review pass was rejected as Pi-heavy/YAGNI; the cheap heuristic +
existing retry deliver "regenerate-on-obvious-failure" without doubling per-lesson cost.

## Post-roadmap review features (from Werner's 2026-06-24 review of the live system)
Werner reviewed the finished system and raised 6 items. Triaged into 2 bugs + 3
features + research. Status:
- ✅ **#2 (bug) HTML `&lt;`/`&gt;` artifacts** — sanitizer was re-escaping the model's own
  entities. Fixed (entity-restore) + Pi-verified. (commit cb7310a)
- ✅ **#6 (bug) timer didn't pause off-lesson** — now counts only on the lesson screen.
  Fixed + Pi-verified. (commit cb7310a)
- ✅ **#4 Answer grading (Option B)** — "Check my answer" grades the typed answer
  (correct/close/incorrect + note), decoupled from reveal, re-checkable. Shipped +
  Pi-verified. (commit bc4dc1d)
- ✅ **#5 Per-lesson depth adaptation** — "Rusty on this? Explain it more deeply"
  regenerates the lesson deeper and overwrites the cache. Shipped + Pi-verified.
  (commit 5fb6e7e)
- ✅ **#1 Real-world evidence capstone** — module/course-end "Real-world connections"
  (search-based Explore links, no hallucinated URLs). Shipped + Pi-verified. (commit 65007f7)
- ⏳ **#3 readability/engagement + #3b loading states** — researched; PROPOSAL written
  (`specs/2026-06-24-readability-loading-proposal.md`), awaiting Werner's go to build
  Slice A (prompt) + B (skeleton/staged loading); Slice C (streaming) deferred.
- ⚠️ **Loose end:** Werner's real ML course has 2 lessons generated BEFORE the #2 fix;
  their cached JSON may still show `&lt;` artifacts. Fix = regenerate them (changes
  their content). Awaiting Werner's call.

## Known issues (discovered during build)
- ✅ **FIXED 2026-06-24 (commit 6fc932b):** lesson body rendered raw HTML tags as literal text.
  Widened the sanitizer allowlist to safe attribute-less block tags (h1–h3, p, pre, ul/ol, li),
  switched the prompt container `<p>`→`<div>`, and styled the tags. Security-reviewed + Pi-verified
  (lesson now renders as proper coursework).
- ✅ **FIXED 2026-06-24 (Slice 8):** the "12-day streak" placeholder is removed (UI pill + dashboard
  strip + constant + dead CSS).
- ✅ **FIXED 2026-06-24 (Slice 8):** `<hr>`/`<hr/>`/`<hr />` are now in the sanitizer allowlist and
  render as a divider instead of literal text.
- **Pi resource contention breaks lesson generation (INFRA — needs Werner).** On 2026-06-24 a
  fresh-lesson generation `claude -p` call timed out (120s) because the Pi was memory-exhausted
  (RAM ~7.1/7.6Gi, **swap 100% full**) and load spiked to ~6. Driver: **houston-mission-control**
  — its uvicorn holds ~56% RAM (~4GB+), it runs dev servers (vite/esbuild/tsx/hocuspocus), and it
  spawns its own heavy `claude -p` (opus-4-7) generations concurrently. Claude University itself is
  innocent (~33MB idle). Not touched (Pierre's project, in active use). Werner's call: cap/relocate
  houston, add swap, or accept that CU generation fails when houston is busy.

## Explicitly NOT building (YAGNI, per research)
Video hosting, instructor/marketplace, enrollment/payments, ratings-by-others, peer review,
discussion forums, notes panel, XP/gamification, hard prerequisite gates. None serve one
AI-taught learner.

## Cadence
Build → review → deploy to the Pi → verify, one slice at a time. Update this file's status as each
lands. Surface Werner only for genuine forks, cost/risk, or blockers.
