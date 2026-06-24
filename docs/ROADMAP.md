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

### Slice 6 — Adaptivity / mastery ← NEXT
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

## Known issues (discovered during build, not yet scheduled)
- **Lesson body renders raw HTML tags as literal text (HIGH — degrades every lesson).** The
  generator emits rich lesson HTML (`<h1>/<h2>/<h3>/<p>/<pre>/<ul>/<li>`), but the default-deny
  sanitizer allowlist only keeps `<code>/<em>/<strong>/<br>/<span class="mono">`, so all structural
  tags are escaped and shown to the learner as literal `<h2>…</h2>` text. Found in the Slice 5 Pi
  e2e (2026-06-24). Fix: widen the allowlist to safe block tags (h1–h3, p, pre, ul/ol, li — not XSS
  vectors) and style them, OR constrain the prompt to the allowlist. Recommend doing this BEFORE
  Slice 6 — adaptivity over unreadable lessons is premature.
- **"12-day streak" still shown on the course dashboard** though streak was dropped (YAGNI). A
  leftover placeholder constant; remove the line.

## Explicitly NOT building (YAGNI, per research)
Video hosting, instructor/marketplace, enrollment/payments, ratings-by-others, peer review,
discussion forums, notes panel, XP/gamification, hard prerequisite gates. None serve one
AI-taught learner.

## Cadence
Build → review → deploy to the Pi → verify, one slice at a time. Update this file's status as each
lands. Surface Werner only for genuine forks, cost/risk, or blockers.
