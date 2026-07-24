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
- [x] **4. Flexible streak** [R: rigid daily streaks are the top documented gamification
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
  **STATUS 2026-07-19: (b)+(c) SHIPPED (commit fc58133, deployed, live-verified —
  manifest.json/sw.js/icons all serve correctly, zero console errors, plain HTTP
  unaffected). (a) BLOCKED on Werner: `tailscale cert` on the Pi returns "your
  Tailscale account does not support getting TLS certs" — HTTPS Certificates need
  enabling at https://login.tailscale.com/admin/dns first (account-level, one click),
  then the two commands in docs/INSTALL.md finish it. Install prompt can't be
  live-verified until then — item stays open.**

## Tier 2 — needs Werner's go/no-go BEFORE building (present, don't assume)

- [ ] **6. FSRS scheduler to replace SM-2** [R: expanding-interval assumption empirically
  unsupported (g=0.034, CI incl. 0); FSRS is the modern standard (Anki opt-in, OpenTutor
  FSRS-only). Caveat: single-learner-scale benefit unproven]
  Changes when Werner's reviews come due — his call. If approved: implement FSRS scheduling
  derived from the same event log (state stays derivable, migration = re-derivation), keep
  SM-2 code deletable in one commit, A/B nothing (single user).
- [x] **7. Misconception profile via structured teach-back rubric** [R: Studyield's
  Feynman-rubric JSON (accuracy/clarity/completeness/understanding + misconceptions) is a
  ready blueprint; validation vs. human judgment unproven — use for feedback, NOT mastery
  gating. Parked by Werner earlier ("decide later") — the blueprint may change his answer]
  If approved: teach-back/explain-it-back graders return the structured rubric; misconception
  strings accumulate into a per-course, learner-visible AND learner-editable profile page
  (transparency pattern from DeepTutor [R]); profile feeds lesson-generation context. Never
  gates mastery.

  **STATUS 2026-07-20: SHIPPED, deployed, live-verified.** Design brainstormed with Werner,
  Fable-reviewed (caught a validation-fragility bug that would have made grading LESS
  reliable, an accountability/excerpt gap, and an `/explain` plumbing correction — all three
  confirmed present in the shipped code by two independent reviewers). Scope decision from
  the brainstorm: **delete-only editing**, not full edit (Werner's explicit choice over the
  original "learner-editable" framing above). Built subagent-driven, 7 tasks, TDD throughout,
  each task individually reviewed (spec + quality, all Approved) plus a final whole-branch
  review that found and fixed 2 Important issues before deploy: an unguarded `e["text"]`
  read that could 500 lesson generation on a malformed `misconceptions.json` (permanent,
  never-pruned learner state — hardened to a single choke-point filter in `load_profile`),
  and a missing cross-task integration test proving the persist→inject round trip (added,
  passed against existing code — confirmed a coverage gap, not a bug). 909 backend / 358
  frontend tests, all green.
  Live-verified on the Pi with real data: sent a real wrong explanation through `/explain`
  on a real ML-course lesson, Claude's grader flagged 3 genuine misconceptions, confirmed
  the HTTP response carried only the legacy `{verdict, note, followUp}` keys (no rubric
  leak), confirmed `GET .../misconceptions` listed all 3. Triggered a real (uncached) next-
  lesson generation and captured the literal prompt sent to Claude — it contained the
  injection block with the exact 3 misconceptions, verbatim, framed as "address only where
  relevant." Verified delete end-to-end in a real browser (Playwright, Tailscale): all 3
  entries removed via the UI, page correctly fell back to the empty state. All test
  data cleaned up (misconceptions.json entries removed via the app's own delete endpoint;
  zero telemetry events were created by this verification, so nothing else needed cleanup).
  Tier 2 items 6, 8, 9, 10, 11, 12 remain unbuilt — deliberately not selected by Werner
  when this item was presented.
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

## Tier 2 (persona batch) — added 2026-07-22, go/no-go per item before building

From the persona brainstorm ([docs/research/2026-07-22-persona-brainstorm.md](../docs/research/2026-07-22-persona-brainstorm.md)),
triaged with Werner 2026-07-22. **[P]** = that sheet. Only the ideas judged worth building are
here; killed/parked/redesign-owned ideas are listed at the end so they aren't re-proposed. Cost
tags are rough (LOW/MED/HIGH). These need a per-item go/no-go, then their own brainstorm→spec→plan.

- [ ] **21. Life-grounded assignments** [P #13 — top pick]. Generate exercises from Werner's own
  artifacts on the same Pi (trading_system, home_assistant, Involo repos; trading data): refactor
  your own code, reason about your own data. Deletes the transfer gap — the one thing only a
  university-of-one can do. Evidence is honest: this is a *structural* bet (situated/authentic
  practice), not a measured effect size. Cost: HIGH — needs a read-only, Werner-pointed ingest of
  chosen repos/data (never leaves the Pi), a generator that builds a real task from a code/data
  slice, and grading. Depends on: strongest after the objective backbone (assignments bind to
  objectives); reuses the lesson-gen background-job + grading. Risk: shallow = gimmick; scope the
  ingest tightly. Decision: its own multi-session brainstorm+spec, not a quick win.
- [ ] **22. Questions become the university** [P #19 — top pick]. One-tap capture of mid-lesson
  tangent questions as first-class objects; later the curriculum grows an objective/lesson from a
  captured question, your question quoted at the top. A captured question = a proto-objective, so
  this rides directly on the objective-centric model. Evidence: interest-driven learning +
  elaborative interrogation. Cost: MED-HIGH. Depends on: the objective-id backbone (Phase 0, in
  progress). Decision: park until Phase 0 lands, then brainstorm.
- [ ] **23. Grade your past self** [P #15 — top pick]. Resurface the learner's own months-old
  explain-back verbatim and have them critique it: spaced retrieval + calibration + visceral
  progress, from data already in the event log. Evidence: retrieval practice (g≈0.5–0.7 vs
  restudy) + self-explanation. Cost: LOW (assembly + one grading prompt). Depends on: months of
  history to bite (Werner ~1mo in — build the capture now, the "grade your past self" reveal
  matures in Q3). Decision: cheap; go/no-go.
- [ ] **24. Interleaved review across courses** [P #10]. Shuffle due items across all
  courses/modules into one mixed queue (today reviews are per-course). Evidence: interleaving
  g≈0.42 for discriminable item types — and Werner runs several courses at once, so it genuinely
  applies. Distinct from item 19 (reviews-before-lesson, single course). Cost: LOW-MED (SRS queue
  exists; add a cross-course mixed mode). Decision: cheap engine win; go/no-go.
- [ ] **25. Spot-the-flaw / reviewer-2 on your own work** [P #14 + PhD #3]. Two modes: (a) Claude
  writes a subtly wrong explanation, learner finds the error; (b) Claude adversarially reviews the
  learner's OWN explanation/answer/code, attacking method/logic/claims. Trains calibrated distrust
  of AI — valuable for a heavy AI user. Evidence: erroneous-examples / refutation-text. Cost: MED.
  Risk: mode (a) must ALWAYS reveal+verify afterward so a missed flaw never teaches the error.
  Decision: go/no-go; strong fit for a skeptical engineer.
- [ ] **26. Examined external readings** [P #12]. Occasionally assign a real chapter/paper from the
  Library's accredited sources and have Claude examine the learner on it — keeps "materials teach,
  AI verifies" literally true. Cost: MED (reuses Library + the viva/grading engine). Overlaps item
  11 (viva) as the exam engine; sequence after it. Decision: go/no-go.
- [ ] **27. Citation audit** [P: PhD #7, stolen into student use]. Verify that every source Claude
  cites in a lesson/answer actually says what it's claimed to say (fetch + check). Cheap,
  mechanical; hardens the Library grounding and catches the ~11% hallucination class Werner already
  worries about. Cost: LOW-MED (reuses the sources/fetch engine). Decision: strong honesty win;
  go/no-go.
- [ ] **28. Night-shift pre-warm of due reviews** [P #17, safe half only]. A nightly idle-hours job
  pre-generates the KNOWN due-review items for the next day so the wait is zero and paid calls
  batch into one predictable window. Explicitly NOT the "pre-generate the likely next lesson" half
  (speculative — wastes tokens on content that may never open). Reuses the lesson-gen background-job
  infra (feat/lesson-gen-progress). Cost: MED. Interacts with item 12 (houston contention).
  Decision: go/no-go.
- [ ] **29. Advisor / anti-isolation layer** [P #23 — recurs in every persona]. An in-app advisor
  that, when the learner returns, reviews the event log, says one true hard thing, asks what pulled
  at them, proposes next term's shape, and grants permission to drop dead courses. Addresses the
  real failure mode of self-study (dropout, not bad pedagogy) — the sheet's own cross-persona note
  calls this the universal missing piece. HARD CONSTRAINT: honors the redesign §4A no-outbound rule
  — it waits for the learner to walk in; it NEVER notifies, nags, or schedules a ping. Evidence is
  honest: advising/retention value is real but this specific in-app pattern is unproven — build
  lean and instrument. Cost: MED. Decision: the most interesting gap; worth its own brainstorm, but
  only within the no-outbound rule.

### Persona batch — cross-references & decisions (do not re-propose)

- **Owned by the objective-centric redesign — cross-ref, not duplicated here:**
  **Confidence calibration on checks** [P #11] → redesign §4A places the confidence tap on
  *delayed/spaced* reviews (not immediate checks — an immediate tap measures the fluency illusion,
  not knowledge) + Phase 4. Could be pulled forward as a cheap standalone if wanted before the
  redesign lands. **The atlas / knowledge map** [P #22-viz] → the visual form of the redesign's
  rich open-learner-model (§4A); honest caveat: OLM→self-regulation evidence is mixed, build lean.
  **Viva mode** [P #7] → already item 11. **Token streaming** [P #6] → already item 10.
- **Killed:** **Knowledge-rot detection** [P #16] — speculative + token-expensive; fundamentals
  don't rot fast enough at this level to justify an idle-hours re-search job. Revisit only if
  narrowed to named fast-moving domains.
- **Recommend decline (needs Werner's explicit reconciliation):** **FSRS full adoption**
  [P #8 / item 6 above]. At n=1 you can't fit FSRS's parameters, so you'd get its complexity with
  none of its payoff; keep only the *graded* recall signal (latency + hint + retry) feeding the
  existing scheduler. NOTE: this CONTRADICTS the objective-centric redesign spec, which currently
  says "adopt FSRS" — item 6 and the spec must be reconciled to one decision. Left untouched
  pending Werner's ruling.
- **Parked (not added as items):** learner-authored textbook [P #18] — nice someday-capstone, low
  urgency; taken-to-the-edge [P #20] and seminar mode [P #21] — fold into viva (11) +
  examined-readings (26), not separate builds.
- **Personas 2 & 3 (PhD, lecturer):** inspiration, not roadmap — they only become a roadmap if CU
  stops being a university-of-one. Open question for Werner. Citation audit (27) and reviewer-2
  (25b) are the only PhD ideas pulled into the student track.

## Tier 3 — hygiene batch (approved; fold into one small branch when convenient)

- [x] **13. Backup restore-check** [S]: monthly (cron or documented manual step) restore of
  the newest content backup to a temp dir + integrity check (course.json parses, lesson count
  matches manifest). The 2026-07-15 data-loss incident created the backups; nothing yet
  proves they restore.
- [x] **14. events.py non-dict crash guard** [S, pre-existing ticket]: a malformed item in
  the events list 500s list endpoints; skip-don't-crash like every other ledger read.
- [x] **15. Shared generate-adapter** [S, verified 13 verbatim copies]: one helper for the
  `lambda prompt, validate: claude_client.run_structured(...)` shim in app.py (+ twins in
  images.py/spine.py `__main__`s). Zero behavior change; tests stay green untouched.
- [x] **16. courses.js fetch-error helper** [S, verified 17+ copies]: one
  `parseErrorBody(resp, fallback)` used by all fetchers. Tests assert on the returned shape
  only, so this is drop-in.
- [x] **17. checks/remediation renderer dedup + verdict-card helper** [S, both verified
  verbatim-duplicated]: shared check-item renderer parameterized on attribute names; shared
  `verdictCardHTML`. lesson.js's own comment already wished for this.
- [x] **18. Small test gaps** [S]: quiz.py `_quiz_round_events` forged-row tests (mirror
  test_exams' existing pattern); direct unit tests for `valid_question_chat_payload`;
  content assertions for `build_chat_prompt`; fix the conditional-assertion exam test
  (`test_grade_exam_exactly_eighty_percent_passes`) so it can't silently no-op.
- [x] **19. Start-session routes through due reviews** [S sweep suggestion; small]: when
  reviewsDue > 0, "Start session" runs the review queue first (plumbing exists in
  `advanceAfterLesson`), then the new lesson. Honors the design brief's warm-up promise.
- [x] **20. Notes/highlights resurfacing — "My notes" view** [S sweep: notes are currently
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
- 2026-07-19: Tier 1 item 4 — flexible streak. New `streakCadence` profile setting
  (daily default / weekly, simplest N=1 rule) read server-side by `GET /api/stats`;
  `stats.weekly_streak_weeks()` shares a new `_study_days()` helper with `streak_days`
  (Monday-anchored weeks, same one-unit tolerance). Dashboard STREAK tile gets a
  "Switch to weekly/daily" toggle that POSTs the full merged profile (never just the
  one key). Arcade's own per-course streak untouched. Merged `8fc752f`, deployed,
  live-verified: toggled live on the real Pi, label+number flipped correctly, then
  restored to daily — confirmed the merge preserved every real onboarding-diagnostic
  answer already on Werner's profile.
- 2026-07-19: Tier 1 item 5 (partial) — app-ification. (b)+(c) shipped: web app
  manifest + icons (generated to match the existing topbar badge exactly) + a
  shell-only service worker (never caches `/api/*`) + docs/INSTALL.md. Merged
  `fc58133`, deployed, live-verified (manifest/sw/icons all serve, zero console
  errors, plain HTTP unaffected). (a) Tailscale HTTPS BLOCKED on Werner — see the
  item's own STATUS note above; needs one admin-console click before it can finish.
- 2026-07-19: Tier 3 items 14–19 (hygiene batch). **14** events.insert_events now
  rejects a non-dict event item the same way as a missing field (400, not 500) —
  commit `ac668d0`, live-verified. **15** the 16 verbatim
  `lambda prompt, validate: claude_client.run_x(...)` shims across app.py/images.py/
  spine.py replaced with two named functions, `claude_client.structured_generate`/
  `sourced_generate` — commit `8efd4b0`. **16** courses.js's 18 duplicated
  fetch-error blocks now share one `parseErrorBody(resp, fallback)` helper —
  commit `582146c`. **17** checks.js/remediation.js's duplicated check-item
  renderer unified into `views/checkItem.js::checkItemHTML` (prequiz.js kept
  separate — genuinely different shape); the grade-verdict card (4x) and
  exam-banner card (2x) unified into `views/verdictCard.js` — commit `9eaf76d`,
  deployed, live-verified (real Claude grading call rendered through the
  refactored gradeCardHTML; real check-answer rendered through checkItemHTML,
  exact `data-check`/`data-choice` attributes confirmed preserved). **18** closed
  4 test gaps (valid_question_chat_payload direct tests, _quiz_round_events
  forged-row test, build_chat_prompt content tests, fixed
  test_grade_exam_exactly_eighty_percent_passes' conditional-assertion bug) —
  bundled in `ac668d0`. **19** "Start session" now runs due reviews first, then
  auto-continues into the new lesson — commit `6aa58d4`, live-verified end-to-end
  on the real Pi with 2 real due reviews (test events cleaned up afterward).
  All items: 867 backend / 343 frontend tests green throughout, zero behavior
  change proven by the untouched suite for 15/16/17.
- 2026-07-19: Tier 3 item 13 — monthly backup restore-check. `backend/restore_check.py`
  extracts the newest backup to a throwaway temp dir and proves it restores: every
  course.json parses through the app's own courses.py code path, DB snapshot passes
  SQLite's integrity_check. Not wired into the Pi's shared, multi-project crontab
  (too risky to script an edit there) — docs/DEPLOY.md has the cron line for Werner
  to add himself. Merged `265c91d`, LIVE-VERIFIED for real against the Pi's actual
  latest backup: all 4 real courses + DB integrity confirmed restorable. Caught and
  fixed two real bugs first (wrong scan root — content/ vs content/courses/ — and
  an unhandled crash on a corrupt gzip) by deliberately testing a broken synthetic
  backup before trusting the real one.
- 2026-07-19: Tier 3 item 20 — "My notes" view. `notes.course_notes_summary()`
  aggregates every lesson's notes/highlights in curriculum order (skips
  unannotated lessons); new `GET /api/courses/<id>/notes`; `views/mynotes.js`
  read-only render + dashboard entry point + a background-loaded "Notes"
  indicator badge on curriculum rows. Merged `245b43e`, deployed, live-verified:
  wrote a real note in the browser, confirmed it surfaced correctly in the
  aggregate, the My notes view, and the curriculum badge; test note deleted
  afterward. **Tier 3 hygiene batch (13–20) now fully complete.**

## Handoff notes

- 2026-07-23 08:34: **Phase 0 objective-id backbone CODE-COMPLETE.** Branch
  `feat/phase0-objective-id-backbone`, HEAD `e3db3c7`. All 9 tasks implemented, each
  task-reviewed and approved; final whole-branch review (verdict: ready to merge) plus a
  4-item fix batch (wire-shaped both POST course responses, guarded the legacy
  `migrate_courses.py` against v3 stores, registry shared-reference docstrings, stale
  comment). Backend 966 / frontend 371 green (baselines 942/369). Full trail:
  `.superpowers/sdd/progress.md`. **MERGED to main 2026-07-23 08:49** (fast-forward
  c10ac6a→e3db3c7, carried `feat/lesson-gen-progress` too since Phase 0 was stacked on it;
  backend 966 green on main; NOT pushed — origin/main is 86 behind, Werner's call).
  **DEPLOYED + LIVE-VERIFIED 2026-07-23 09:12 — Phase 0 SHIPPED.** Pi was offline (expired
  Tailscale node key — fixed with `sudo tailscale up --advertise-routes=192.168.2.0/24`, the
  Pi is a subnet router; disable key expiry to prevent recurrence). Deploy: rsync (content/
  and data/ excluded) → restart → live migration (4 courses v2→v3, 0 errors, 90/74/90/66).
  Verified on the Pi: API serves all 4 at schemaVersion 3 with embedded objectives on every
  lesson; disk v3 + `course.json.pre-objid-*` sidecars hold the v2 originals; end-to-end
  lossless; exam blueprints resolve live; frontend `>= 2` gate served. restore_check + a
  dry-run on a copy of the real content preceded it. **Open follow-ups:** (a) revise
  round-trip not live-fired (avoids LLM spend / prod state — covered by tests); worth a manual
  browser smoke-test when convenient. (b) sidecars retained until Werner confirms healthy,
  then removable. (c) service-worker cache-first: hard-refresh the browser once. (d) Phase-4
  precondition in memory: seed the objective-id counter from the on-disk registry max before
  any objective-id-keyed persistence lands.
- Session norms: spec → plan → subagent build → per-task review → final whole-branch review
  → merge → deploy ([docs/DEPLOY.md](../docs/DEPLOY.md) — read the hard rules) → live-verify
  on the Pi → clean up test data → update this file + the ledger.
- The Pi is production AND the only copy of content/data. When in doubt, don't.
