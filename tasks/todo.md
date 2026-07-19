# Phase 2 backlog — evidence-driven refinement

Governed by [docs/CHARTER-PHASE-2.md](../docs/CHARTER-PHASE-2.md) — read it first, every
session. Evidence citations: **[R]** = [docs/research/2026-07-19-improvement-ideas-deep-dive.md](../docs/research/2026-07-19-improvement-ideas-deep-dive.md),
**[S]** = the 2026-07-18/19 project sweep (ledger: `.superpowers/sdd/progress.md`).
Work top-to-bottom within a tier. One branch + spec/plan per item (or per small-item batch).
Mark items done here with date + merge commit as they land.

## Tier 1 — approved, build in this order

- [x] **1. Lesson-chat guardrails audit + hardening** [R: PNAS RCT — unguarded chat = −17%
  on unassisted exams; hint-only guardrails eliminated the harm]
  The default lesson side-chat (`backend/generation.py:lesson_chat_prompt`) and the quiz
  question-chat must, whenever an exercise/check/exam item is ACTIVE (unrevealed): coach via
  hints, refuse to state the answer outright, and receive the canonical solution in-prompt so
  feedback stays accurate. Audit what the prompts do today (Socratic mode already complies;
  the default mode is the question), close gaps, and add prompt-content tests mirroring the
  existing `lesson_chat_prompt` test style. Acceptance: a chat asked point-blank for the
  active exercise's answer coaches instead of answering (live-verified); revealed/completed
  items unchanged; suites green.
- [x] **2. Study heatmap on the dashboard** [R: Anki Review Heatmap — the most-loved habit
  surface in the SRS world; passive + honest]
  GitHub-contribution-style calendar: past study days (from STUDY_EVENTS, all courses) AND
  forecast of upcoming review load (from the real SRS queue — we can forecast properly).
  Streak shown alongside. No notifications, no pressure copy. Backend: one endpoint
  aggregating events/day + due-counts/day. Frontend: render-only view, warm-glass styling.
  Acceptance: matches a hand-computed sample from the events table; renders on phone width;
  live-verified.
- [x] **3. Highlight → review item (one tap)** [R: highlighting is low-utility as study,
  retrieval is highest — convert one into the other]
  Tapping an existing highlight currently only offers removal. Add a second action: "Make
  review item" — creates a review/SRS item from the highlighted text + its lesson context
  (reuse the existing review-items machinery). Keep highlights otherwise inert (design doc
  decision stands). Acceptance: item appears in that lesson's review flow and in reviews-due
  counts; removal of the highlight does NOT delete the created item; live-verified.
- [ ] **4. Flexible streak** [R: rigid daily streaks are the top documented gamification
  complaint; Duolingo's own data — flexibility increases retention]
  Add a learner setting: streak cadence "daily" (default, current behavior) or "weekly"
  (a week with ≥N study days keeps the streak; pick N=1 or make it part of the setting —
  simplest honest rule wins). Applies to the dashboard streak + heatmap display. The Arcade's
  per-course streak is unaffected. Acceptance: unit tests on the boundary cases (week
  rollover, missed week); setting persists; live-verified.
- [ ] **5. "App-ification": PWA install + Tailscale HTTPS** [Werner request 2026-07-19
  ("can we make it a .exe in some way?") — the right-sized answer]
  (a) On the Pi: `tailscale serve` (or `tailscale cert` + waitress TLS) to give the app a
  real HTTPS origin on its MagicDNS name — this also unlocks secure-context browser APIs
  (crypto.randomUUID etc., a known limitation). Plain-HTTP LAN/IP access must keep working.
  (b) Web app manifest (name, icons, standalone display, theme colors) + minimal service
  worker (cache the static shell only — NEVER cache /api responses; offline sync already has
  its own localStorage design). (c) Result: installable to Mac Dock / Windows / phone home
  screen as a windowed app. Document the install steps per device in README or docs/.
  Acceptance: Chrome shows the install prompt on the HTTPS origin; installed app opens
  standalone and works end-to-end; plain LAN HTTP still works; live-verified from at least
  one device.

## Tier 2 — needs Werner's go/no-go BEFORE building (present, don't assume)

- [ ] **6. FSRS scheduler to replace SM-2** [R: expanding-interval assumption empirically
  unsupported (g=0.034, CI incl. 0); FSRS is the modern standard (Anki opt-in, OpenTutor
  FSRS-only). Caveat: single-learner-scale benefit unproven]
  Changes when Werner's reviews come due — his call. If approved: implement FSRS scheduling
  derived from the same event log (state stays derivable, migration = re-derivation), keep
  SM-2 code deletable in one commit, A/B nothing (single user).
- [ ] **7. Misconception profile via structured teach-back rubric** [R: Studyield's
  Feynman-rubric JSON (accuracy/clarity/completeness/understanding + misconceptions) is a
  ready blueprint; validation vs. human judgment unproven — use for feedback, NOT mastery
  gating. Parked by Werner earlier ("decide later") — the blueprint may change his answer]
  If approved: teach-back/explain-it-back graders return the structured rubric; misconception
  strings accumulate into a per-course, learner-visible AND learner-editable profile page
  (transparency pattern from DeepTutor [R]); profile feeds lesson-generation context. Never
  gates mastery.
- [ ] **8. Exercise-answer persistence** [Werner feedback #4 part 2 — explicitly deferred to
  a scope discussion that hasn't happened. Do not build without it]
  Open questions for that discussion: persist where (workspace file has room), restore on
  revisit or show as history, does a restored answer affect grading/mastery (recommend: no).
- [ ] **9. Chat-question analysis** [Werner feedback #6 — same pending scope discussion;
  overlaps item 7's profile surface]
- [ ] **10. Token streaming for lesson generation** [Parked since 2026-06-24; biggest
  perceived-latency lever for the 30-90s generation wait. Real work: SSE plumbing through
  generation + sanitize-on-complete. Werner's call on priority]
- [ ] **11. Viva mode** [Parked by Werner "decide later" — unchanged; item 7's rubric would
  be its grading engine if both are approved]
- [ ] **12. houston memory contention** [Infra, Werner-only: cap/relocate houston, add swap,
  or accept that CU generation can fail when houston is busy. Open since 2026-06-24]

## Tier 3 — hygiene batch (approved; fold into one small branch when convenient)

- [ ] **13. Backup restore-check** [S]: monthly (cron or documented manual step) restore of
  the newest content backup to a temp dir + integrity check (course.json parses, lesson count
  matches manifest). The 2026-07-15 data-loss incident created the backups; nothing yet
  proves they restore.
- [ ] **14. events.py non-dict crash guard** [S, pre-existing ticket]: a malformed item in
  the events list 500s list endpoints; skip-don't-crash like every other ledger read.
- [ ] **15. Shared generate-adapter** [S, verified 13 verbatim copies]: one helper for the
  `lambda prompt, validate: claude_client.run_structured(...)` shim in app.py (+ twins in
  images.py/spine.py `__main__`s). Zero behavior change; tests stay green untouched.
- [ ] **16. courses.js fetch-error helper** [S, verified 17+ copies]: one
  `parseErrorBody(resp, fallback)` used by all fetchers. Tests assert on the returned shape
  only, so this is drop-in.
- [ ] **17. checks/remediation renderer dedup + verdict-card helper** [S, both verified
  verbatim-duplicated]: shared check-item renderer parameterized on attribute names; shared
  `verdictCardHTML`. lesson.js's own comment already wished for this.
- [ ] **18. Small test gaps** [S]: quiz.py `_quiz_round_events` forged-row tests (mirror
  test_exams' existing pattern); direct unit tests for `valid_question_chat_payload`;
  content assertions for `build_chat_prompt`; fix the conditional-assertion exam test
  (`test_grade_exam_exactly_eighty_percent_passes`) so it can't silently no-op.
- [ ] **19. Start-session routes through due reviews** [S sweep suggestion; small]: when
  reviewsDue > 0, "Start session" runs the review queue first (plumbing exists in
  `advanceAfterLesson`), then the new lesson. Honors the design brief's warm-up promise.
- [ ] **20. Notes/highlights resurfacing — "My notes" view** [S sweep: notes are currently
  write-only]. A read-only per-course aggregate (grouped by lesson) + a notes indicator on
  curriculum rows. Keep scope to display; no AI processing (that's items 7/9 territory).

## Done

- 2026-07-19: Audit quick-wins batch (arcade streak counting, missed-lesson result chips,
  cache-first lesson open) — merged `d36e442`, deployed, live-verified, ledgered. [S]
- 2026-07-19: Tier 1 item 1 — lesson-chat guardrails audit + hardening. `LESSON_CHAT_SYSTEM`
  no longer hands over the exercise answer after a second ask; `ANALOGY_SYSTEM` guarded
  against the same pivot. Socratic/teach/quiz-question-chat already compliant. Merged
  `99d90cf`, deployed, live-verified on Pi with real Claude calls (declines + hints while
  unrevealed, discusses freely once revealed), ledgered in `.superpowers/sdd/progress.md`.
- 2026-07-19: Tier 1 item 2 — study heatmap on the dashboard. `stats.heatmap()` aggregates
  past study-day counts (all courses) + a 30-day SM-2 due-forecast; new `/api/stats.heatmap`
  field; `heatmap.js` GitHub-style calendar (purple=studied, blue=forecast) alongside the
  streak stat. Merged `0b4aa64`, deployed, live-verified in a real browser (desktop + phone
  width, real Pi data matched a hand-computed sample); caught and fixed a desktop grid-area
  collision with the session card during that verification.
- 2026-07-19: Tier 1 item 3 — highlight → review item. Tapping a highlight now opens a
  Remove / Make review item menu; the latter is a one-shot Claude call that turns the
  passage into a check item, persisted as `userItems` in `review_items.py`'s per-lesson
  file (survives regeneration and the source highlight's later removal). `GET
  review-items` folds `userItems` into the served list — zero changes needed to the
  review-consumption path. Merged `307cec8`, deployed, live-verified end-to-end in a real
  browser + real Claude calls (created a real grounded MCQ from a real highlighted
  passage on ML l1; confirmed it survived highlight removal; confirmed it appears
  alongside 2 fresh AI items in the actual review-items response); caught and fixed a
  reviewCount-sentinel bug (0 collided with a legitimate never-reviewed lesson) before
  it shipped, via the route-level tests. Test artifacts cleaned from the Pi.

## Handoff notes

- Session norms: spec → plan → subagent build → per-task review → final whole-branch review
  → merge → deploy ([docs/DEPLOY.md](../docs/DEPLOY.md) — read the hard rules) → live-verify
  on the Pi → clean up test data → update this file + the ledger.
- The Pi is production AND the only copy of content/data. When in doubt, don't.
