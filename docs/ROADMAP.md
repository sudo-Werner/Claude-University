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

### Slice 4 — Spaced-repetition engine (the #1 pillar) ← NEXT
**Closes:** done-item 1.
**Why first:** biggest missing learning pillar, and it's *unblocked* — it can run on an
**Anki-style self-rated recall signal** after each lesson (Again / Hard / Good / Easy), so it does
not depend on auto-grading.
**Scope:** SM-2/FSRS scheduling with four cheap per-lesson fields (`repetitions`, `interval_days`,
`ease_factor`, `next_review_date`) derived from review events; a post-lesson recall rating; the
per-course "reviews due" count becomes real; a **review surface** that resurfaces due lessons
(re-presenting the exercise, not regenerating). Scheduling state derived from the event log
(single source of truth), consistent with Slice 1.
**Depends on:** nothing new.

### Slice 5 — Checkable concept-check items + feedback
**Closes:** done-item 3; advances 4.
**Scope:** lessons gain a small `items` array in their JSON (MCQ / fill-in-the-blank with correct
answers + per-choice feedback), generated alongside the exercise; the lesson screen checks the
learner's answer and gives feedback instead of pure self-assessment. Gives an *objective* signal
that later sharpens spaced repetition and adaptivity.
**Depends on:** Slice 4 (the rating/review loop exists; checks feed it a better signal).

### Slice 6 — Adaptivity / mastery
**Closes:** done-item 2.
**Scope:** a 4-level mastery state per lesson (Attempted / Familiar / Proficient / Mastered)
derived from review history + check performance; generation and "what's next" react to it (e.g.
struggled → easier reinforcement or a prerequisite recap; mastered → advance). Feeds the course
`brief` + recent performance into lesson generation.
**Depends on:** Slices 4–5 (needs the performance signal).

### Slice 7 — Curriculum structure & lesson-player UX
**Closes:** done-items 6 and the UX half of 4–5.
**Scope (per research):** a **course-overview accordion** (modules expand to lessons with
completion checkmarks + per-section progress); a **two-panel lesson player** (content + a
curriculum sidebar with current-item highlight, Prev/Next, mark-complete, "X of Y"); a home
**"Continue Learning"** treatment. Keep the warm glass theme. Add minimal course metadata
(`objectives[]`, `difficulty`) only where it earns its place.
**Depends on:** Slices 4–6 (so the player reflects mastery/reviews).

### Slice 8 — Content-quality safeguards + loose ends
**Closes:** done-items 7, 8.
**Scope:** a lightweight check that generated lessons are sane (schema already enforced; add a
self-review/regenerate-on-obvious-failure pass); make the Pi's Claude-subscription login resilient
(detect 401 → surface "re-auth needed" instead of silent failure). **Streak: dropped** — research
flags it as zero-value for a single AI-taught learner (YAGNI); revisit only if Werner wants it.

## Explicitly NOT building (YAGNI, per research)
Video hosting, instructor/marketplace, enrollment/payments, ratings-by-others, peer review,
discussion forums, notes panel, XP/gamification, hard prerequisite gates. None serve one
AI-taught learner.

## Cadence
Build → review → deploy to the Pi → verify, one slice at a time. Update this file's status as each
lands. Surface Werner only for genuine forks, cost/risk, or blockers.
