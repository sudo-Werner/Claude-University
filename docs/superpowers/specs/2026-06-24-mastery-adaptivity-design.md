# Claude University — Mastery & Adaptivity (Slice 6)

**Date:** 2026-06-24
**Status:** Design — self-approved under the build charter (see [CHARTER.md](../../CHARTER.md))
**Builds on:** Slices 1–5. Closes roadmap done-item 2.

## For Werner (plain-language summary)

Today the platform knows two things about each lesson: "done or not" and "due for review or
not". It does not know **how well** you actually know something. This slice adds a **mastery
level** per lesson — Attempted → Familiar → Proficient → Mastered — worked out automatically from
your review ratings and how you did on the concept checks. Two payoffs: (1) you can **see** where
you stand, and (2) when the platform writes your **next** lesson, it adapts — if you've been
breezing through, it goes deeper/faster; if you've been struggling, it slows down and reinforces
the basics. It's the first time the system teaches *to you* rather than the same way regardless.

## Decisions made (self-approved under charter)

- **Mastery is derived, never stored** — computed by replaying the event log (same principle as
  SM-2 reviews and progress). No schema change, no new tables.
- **Four levels: Attempted / Familiar / Proficient / Mastered.** Driven by two signals already in
  the log: SM-2 **repetitions** (depth of successful recall over time) and **check accuracy** (the
  objective signal from Slice 5's `lesson_check` events).
- **Adaptivity lives in generation, not in curriculum reordering.** New lessons are generated with
  a short *performance summary* so Claude calibrates difficulty/pace. We do **not** dynamically
  reorder the manifest, insert recap lessons, or regenerate cached lessons — that's heavier,
  riskier on a linear single-track course, and YAGNI for now (revisit if the need is real).
- **Minimal UI surface this slice.** A mastery breakdown (counts per level) on the course
  dashboard so the signal is visible. Rich per-lesson mastery badges wait for Slice 7's curriculum
  view — that's where a per-lesson list will exist.

## Mastery model

Per lesson, from the event log:

- `reps` = SM-2 repetitions from replaying that lesson's `lesson_reviewed` events (reuses
  `srs.sm2`). A `q<3` ("again") rating resets reps to 0 — i.e. "not currently retaining".
- `acc` = correct ÷ total over that lesson's `lesson_check` events (`None` if no checks answered).

Level (with `ATTEMPTED=0, FAMILIAR=1, PROFICIENT=2, MASTERED=3`):

```
base = ATTEMPTED  if reps == 0      # last recall failed/reset, or only just attempted
       FAMILIAR   if reps == 1
       PROFICIENT if reps == 2
       MASTERED   if reps >= 3       # retained across ~3 weeks of SM-2 intervals

# objective-check gate — weak checks cap optimistic self-ratings:
if acc is not None:
    if acc < 0.5:  base = min(base, ATTEMPTED)
    elif acc < 0.8: base = min(base, PROFICIENT)
```

Only **completed** lessons (have a `lesson_reviewed`/`lesson_completed` event) get a level; others
are absent from the map (UI treats absent = not started).

## Performance summary (drives generation)

A short, course-level natural-language directive aggregated over completed lessons:

- counts per level + overall check accuracy across the course.
- **Strong** (≥60% of completed lessons Proficient+ AND acc ≥ 0.8, or acc≥0.8 with no weak
  lessons): "performing strongly — you may go a bit deeper/faster and assume earlier lessons are
  retained."
- **Struggling** (any Attempted with low acc, or overall acc < 0.6): "has been struggling —
  reinforce fundamentals, go step-by-step, add scaffolding and a brief recap of prerequisites."
- **Steady** (everything else): "progressing steadily — keep a balanced pace."
- **No history** (first lesson, nothing completed): empty string → inject nothing (no noise).

## Architecture

1. **`backend/mastery.py` (new, pure).**
   - `LEVELS = ["attempted", "familiar", "proficient", "mastered"]`.
   - `level_for(reps, acc) -> str` — the rule above.
   - `_checks_by_lesson(conn, course_id) -> {lessonId: (correct, total)}` — from `lesson_check`
     events' `{correct}` payload.
   - `lesson_mastery(conn, content_dir, course_id) -> {lessonId: level}` — combines `srs` reps
     (via `srs._reviews_by_lesson` + `srs.sm2`) with check accuracy, over completed lessons.
   - `mastery_counts(mastery_map) -> {level: count}` — for the UI tile.
   - `performance_summary(conn, content_dir, course_id) -> str` — the directive above ("" if none).

2. **Generation adaptivity (`backend/generation.py`).**
   - `lesson_prompt` gains a `performance=""` kwarg; when non-empty, add a line
     `Learner performance so far: {performance}` so Claude calibrates difficulty/pace.
   - `ensure_lesson` gains a `performance=""` kwarg passed straight through to `lesson_prompt`
     (keeps `ensure_lesson` pure / conn-free; the route computes the summary).

3. **API (`backend/app.py`, `backend/courses.py`).**
   - `GET /api/courses/<id>` response gains `mastery` (the map) and `masteryCounts`.
   - The lesson route (`get_lesson`) computes `performance_summary(conn, ...)` and passes it into
     `ensure_lesson(..., performance=summary)` so JIT generation is adaptive.

4. **Frontend (`frontend/src/courses.js`, `views/dashboard.js`, `app.js`).**
   - `loadCourse` already fetches `/api/courses/<id>`; mastery rides along.
   - `sessionData()` passes `masteryCounts` to the dashboard.
   - `dashboardHTML` renders a small **Mastery** breakdown (e.g. "2 mastered · 1 proficient ·
     1 familiar · 1 attempted"), shown only when there's at least one completed lesson.

## Data flow

```
review ratings + lesson_check events ─▶ mastery.lesson_mastery ─▶ map + counts
                                          │
   GET /api/courses/<id> ────────────────┘──▶ dashboard "Mastery" breakdown
   GET …/lessons/<id> (cache miss) ─▶ performance_summary ─▶ lesson_prompt ─▶ adaptive new lesson
```

## Testing

- **Backend (pure):** `level_for` across the reps×acc matrix (incl. the accuracy gate demotions);
  `lesson_mastery` over a seeded event log (completed-only, reset-on-again, check-accuracy cap);
  `mastery_counts`; `performance_summary` for strong / struggling / steady / no-history;
  `lesson_prompt` includes the performance line when given, omits it when empty;
  `ensure_lesson` forwards `performance` into the prompt (fake `generate` capturing the prompt).
- **API:** `GET /api/courses/<id>` includes `mastery` + `masteryCounts`.
- **Frontend (pure):** `dashboardHTML` renders the mastery breakdown from `masteryCounts` and
  omits it when all-zero.
- **Real-browser + Pi:** with some review/check history, confirm the dashboard shows a mastery
  breakdown, and a freshly generated lesson's prompt carries the performance signal (verify via a
  lesson that generates after history exists).

## Out of scope (deferred)

- Dynamic curriculum reordering, inserted prerequisite-recap lessons, regenerating cached lessons
  to match new mastery (heavier; revisit only with a real need).
- Per-lesson mastery badges in a curriculum/lesson-list view — Slice 7 (that's where the list
  lives).
- Auto-suggesting the recall rating from check results (kept manual; possible later refinement).

## Self-review notes

- **Event-derived, no schema change** — mastery and the performance summary are pure functions of
  the existing log, consistent with Slices 1/4/5.
- **Objective gate** — check accuracy caps optimistic self-ratings, so "Mastered" means both
  retained recall *and* correct checks.
- **Lean adaptivity** — one extra prompt line; no manifest mutation, no regeneration.
- **Pi-light** — a few extra event queries per course/lesson request; negligible footprint.
- **Feeds Slice 7** — the mastery map is exactly what the curriculum view will badge per lesson.
