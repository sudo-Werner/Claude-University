# Quiz Arcade — random-format quiz game over completed lessons — design

**Date:** 2026-07-17. **Status:** approved direction (Werner 15:54 "Sounds good, lets do it";
interview answers: random format each time / course subjects only / hybrid play start / full
stats). Origin: parked idea from 2026-06-30 ("name a subject, get a random quiz game"),
narrowed during brainstorming to enrolled-course material.

## Goal

A playful **Arcade** beside the formal courses: press Play on a course and instantly get a
surprise-format quiz round built from lessons you have **completed** — retrieval practice
wearing a costume. Rounds grade entirely in the browser (no API calls during play), results
land in the events ledger, misses pull the source lesson forward in spaced repetition, and a
per-course stats panel (history, streaks, per-format bests) gives replay value.

**Cost shape:** one `run_structured` call (DEFAULT_MODEL, currently `claude-sonnet-4-6`) per
round generated — triggered by bank restocks, not by play. Steady state ≈ one small call per
round actually played plus one per completed lesson. Zero calls during play.

## Decisions

1. **New `backend/quiz.py` module** owns the whole feature: round prompt + validation, bank
   management + restock, results handling, stats queries. Routes in `app.py` stay thin,
   mirroring feedback/images.
2. **Round artifact.** One JSON file per round at
   `content/courses/<course_id>/quiz-rounds/<round_id>.json` (per-course artifact dir
   precedent: exams/, remediation/, review-items/, images/). `round_id` =
   `round-<uuid4.hex[:12]>`, filename validated `^round-[a-f0-9]{12}\.json$`. Written via
   `write_text_atomic`. Round shape:
   `{"round_id", "course_id", "format", "title", "host_intro", "questions": [...],
   "created_at"}` — every string **plain text, no HTML** (esc()'d at render; there is no
   sanitize/markup surface in the Arcade at all).
3. **Question pool = completed lessons only**, via the existing
   `courses.completed_lesson_ids(conn, course_id)` (`lesson_completed` / `lesson_reviewed`
   events), intersected with lessons that have a cached lesson file (grounding source).
   Empty pool → the API returns a `locked` status and the UI shows "finish your first
   lesson to unlock". No spoilers of unseen material, ever.
4. **Format catalog v1 — five formats, all deterministically gradable client-side.** Each
   question carries `lesson_id` (must be in the pool — validated, so a hallucinated id can
   never reach the SRS), plus a one-line `reveal` shown after answering:
   - `rapid_fire`: 8–12 × `{lesson_id, prompt, choices: [3–5 str], answer: <index>,
     reveal}`; client shows a 15 s per-question countdown, timeout counts as a miss.
   - `true_false`: 10–14 × `{lesson_id, statement, answer: <bool>, reveal}`. (An in-round
     streak counter was considered here; v1 shipped without it — revisit on demand.)
   - `odd_one_out`: 6–8 × `{lesson_id, items: [4 str], answer: <index>, reveal}` (reveal
     explains why it doesn't belong).
   - `spot_the_lie`: 6–8 × `{lesson_id, statements: [3 str], answer: <index of the lie>,
     reveal}`.
   - `match_up`: 2–3 boards × `{lesson_id, pairs: [5 × {left, right}], reveal}`; client
     shuffles the right column; score = correctly matched pairs.
   `valid_round` is default-deny: known format, format-specific shape and count ranges,
   string caps (prompt/statement/reveal ≤ 300 chars, choice/item/pair-side ≤ 120, title ≤
   80, host_intro ≤ 200), answer indexes in range, every `lesson_id` in the pool. Anything
   off → round rejected (run_structured's built-in retry covers one bad emission).
5. **Format picked server-side with weighted randomness** at generation time: weight
   `1 / (1 + times format appears in the course's last 10 quiz_round events)` — recently
   played formats get rarer, all formats stay possible. History injected as a parameter so
   tests are deterministic.
6. **Bank + hybrid restock.** Floor: 3 unplayed rounds per course.
   - `GET /api/courses/<course_id>/quiz/round` → serve the oldest banked round; if the bank
     is below floor afterwards, kick a background restock. Empty bank → respond
     `{"status": "generating"}` and kick restock; the client polls every ~3 s with a themed
     loading screen (mirrors the lesson-status pattern). Empty pool → `{"status": "locked"}`.
   - Restock runs in a `threading.Thread(daemon=True)` guarded by a per-course lock
     registry (same pattern as `generation._GEN_LOCKS`): at most one restock per course at
     a time; a second trigger while one is running is a no-op. Each restock generates
     rounds until the floor is met (cap 3 per run).
   - **Lesson-completion top-up:** the events route, after inserting a `lesson_completed`
     event, nudges the course's restock (fail-open, non-blocking) so new material enters
     the rotation.
7. **Results: one dedicated route**, `POST /api/courses/<course_id>/quiz/results` with
   `{client_event_id, session_id, round_id, format, score, total,
   missed: {lesson_id: <miss count>}}`. The backend inserts a `quiz_round` event via the
   existing `events.insert_events` (idempotent on `client_event_id` — replays are safe),
   deletes the round file (the event is the durable record; a missing file is fine), and
   kicks restock. No new tables anywhere in this feature.
8. **Stats are queries over events, not stored aggregates.**
   `GET /api/courses/<course_id>/quiz/stats` computes from `quiz_round` events: rounds
   played, best score (as a percentage — totals vary by format), per-format plays + best
   percentage, last-10 history (date, format, score/total), and play streak = consecutive
   calendar days ending today (or yesterday) with ≥1 round in this course. Single source
   of truth, same pattern as stats.py.
9. **SRS feed: misses act like the exam-weakness signal.** `srs.py` gains a quiz-miss
   check mirroring `_weak_since_review`: a lesson with ≥1 missed quiz question since its
   last review is flagged weak and pulled forward for review. Deliberately NOT recorded as
   `lesson_reviewed` — playing a game is not a review session, and faking one would corrupt
   the SM-2 history.
10. **Frontend.** New nav entry **Arcade** + `frontend/src/views/arcade.js`: course cards
    (stats panel + Play / locked state), the play screen (host intro → questions one at a
    time with immediate reveal feedback → end-of-round score), one renderer per format.
    `app.js` wires state, the rapid-fire countdown, match-up pair-tapping, polling, and the
    results POST; `courses.js` gains `getQuizRound` / `postQuizResults` / `getQuizStats`.
    All content rendered through `esc()`; answers never leave the client except as counts
    in the results payload.
11. **No learner text enters any prompt.** Round generation consumes only cached lesson
    content, spine entries, and the manifest ("pick a course" replaced "name a subject",
    so the feature has no free-text input at all).

## Error handling

- Generation/validation failure during restock → bank unchanged, stderr log, thread exits;
  the client's poll keeps its loading screen and after ~90 s offers "try again" (which
  re-kicks via the GET). Play never errors because a restock failed silently.
- Round file missing at serve time (hand-deleted) → skip it, serve the next, restock.
- Results replay (double-tap, reconnect) → duplicate event ignored, file-delete no-op.
- Countdown/timer only affects scoring client-side; a stalled tab never corrupts state.

## Security

- Plain-text-only content + esc() at render = no XSS surface; no sanitizer needed, no HTML
  ever parsed from quiz data.
- Routes: `_ID_RE` on course_id; round filenames regex-locked; `send`-free (rounds are
  returned as JSON, never via file serving).
- `lesson_id` allowlist in `valid_round` keeps hallucinated ids out of the SRS signal. The
  results route does NOT re-verify miss counts against the round file (it may already be
  consumed): miss counts are clamped to non-negative ints and only influence review
  scheduling, never content — same client-asserted trust model as `lesson_completed` in
  this single-user app.
- Round generation writes only into the course's quiz-rounds/ dir via atomic writes.

## Testing

- **Backend:** `valid_round` accept + reject per format (bad counts, out-of-range answer,
  oversize strings, unknown format, foreign lesson_id); format weighting math with injected
  history; bank serve/consume ordering; restock floor + single-flight lock (injected fake
  generator, no live calls); results route (event inserted, idempotent replay, file gone,
  restock kicked); stats queries against seeded events (streak edges: today, yesterday,
  gap); SRS quiz-weakness pull-forward (mirrors exam-weakness tests); locked/empty pool.
- **Frontend:** one render + grade test per format (incl. esc() XSS string in a prompt);
  countdown timeout = miss; match-up pairing and scoring; results payload shape; stats
  panel rendering; locked state; import-resolution checks.

## Deploy notes

Standard DEPLOY.md (never `--delete`; content/ excluded — banked rounds live only on the Pi,
covered by the daily backup tar). No new pip dependencies (stdlib threading/uuid only).
After deploy: health + `/api/courses`, open Arcade over the Pi origin, play one live round
end-to-end (first play exercises the empty-bank → generating → play path), then confirm the
bank restocked to floor afterwards.

## Out of scope

- Arbitrary non-course subjects (the original "name any subject" — revisit once the
  course-grounded version has been lived with).
- Typed free-text answer formats (would need grading calls; kills instant play).
- Multiplayer, leaderboards, badges, sounds; anything beyond light CSS polish.
- New DB tables or stored aggregates; viva mode; misconception profile.
- Quiz questions feeding mastery *scores* (misses only influence review scheduling).
