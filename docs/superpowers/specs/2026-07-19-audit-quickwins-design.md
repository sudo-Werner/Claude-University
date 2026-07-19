# Audit quick-wins batch — Arcade streak, missed-lessons list, cache-first lesson open

**Date:** 2026-07-19. **Status:** approved (Werner 2026-07-19 15:04 "we can go with your
sequencing" — the three highest feel-per-effort items from the 2026-07-18/19 project sweep).

## 1. Arcade play counts toward the dashboard streak and Recent Activity

**Problem (sweep finding, verified):** `backend/stats.py` STUDY_EVENTS and ACTIVITY_EVENTS
omit `quiz_round`, so a day of pure Arcade practice breaks the dashboard streak and never
appears in the study log — while a second, different per-course streak shows inside the
Arcade tab. Reads as a bug ("I studied yesterday, why did my streak break?").

**Design:**
- Add `"quiz_round"` to both STUDY_EVENTS and ACTIVITY_EVENTS in `backend/stats.py`.
- `recent_activity()`: for `quiz_round` rows, surface `score`/`total`/`format` from the
  payload (defensively — the events ledger is client-writable, so missing/malformed values
  must render safely, same posture as `quiz.py`'s own `_quiz_round_events`). `topic_id` for
  quiz_round is a round id, not a lesson id, so `lessonTitle` naturally stays `None`.
- `frontend/src/views/activity.js`: a `quiz_round` branch in `entryHTML` — "**Arcade
  round** 8/12 · <course>". If score/total are absent or non-numeric, omit the score part
  rather than rendering "undefined/undefined".
- The Arcade tab's own per-course streak (`_quiz_streak_days`) stays: it is per-course and
  the dashboard streak is global — different facts, both now consistent (an Arcade-only
  day extends both).

## 2. Arcade round results show which lessons the misses came from

**Problem (sweep finding, verified):** `app.js` tracks per-lesson miss counts all round
(`st.missed`) and submits them (they feed spaced repetition), but `arcadeResultHTML` shows
only a bare percentage. The exam result screen already has the exact pattern to copy
("Focus next on" clickable weak-spot chips).

**Design (frontend only — no backend change):**
- `arcadeResultHTML(playState, lessonTitles)` gains a "Review what you missed" section
  when `playState.missed` is non-empty: one tappable chip per lesson —
  `<button class="weak-lesson" data-lesson="...">Title — missed N×</button>` — reusing the
  exam screen's `.weak-spot`/`.weak-lesson` visual idiom. Sorted by miss count descending.
- **Titles:** the Arcade is a global tab, so no course manifest is loaded. When the round
  reaches the result phase with misses, app.js fetches the course manifest once via the
  existing `loadCourse({fetch, courseId: ui.arcadeCourseId})`, builds `{lessonId: title}`,
  stores it on `ui.quizPlay`, and repaints. Fallback: if the fetch fails or a lesson id is
  unknown (deleted lesson), the chip shows the raw lesson id — degraded but functional,
  never blocks the score display (which renders immediately, before titles arrive).
- **Tap-through:** chip tap sets `ui.courseId = ui.arcadeCourseId`, awaits the existing
  `refreshSummary()` (loads manifest), guards `ui.manifest` (fall back to `showHome()` on
  failure, same as `openCourse`), then calls `openLesson(lessonId)` — the lesson opens in
  proper course context so Prev/Next/curriculum all work.
- A perfect round (no misses) renders exactly as today.

## 3. Cache-first lesson open — no skeleton flash for already-generated lessons

**Problem (sweep finding, verified):** `openLesson` (app.js:1215) paints the loading
skeleton immediately on every open, then awaits a status round-trip plus the lesson GET —
even though nearly every open is a cached lesson that resolves in ~100-300ms. The most
frequent daily action always flashes a skeleton.

**Design:** delay the skeleton, not the state machine.
- `ui.screen = "lesson-loading"` and the `seq` guard stay exactly as they are (every
  existing mid-flight navigation guard keys off them).
- The `startLoading(view, ...)` paint moves behind a ~200ms `setTimeout` whose callback
  re-checks `ui.screen === "lesson-loading" && ui.loadSeq === seq` before painting (so a
  fast open, or navigation elsewhere, never shows it). Fast path: previous screen stays
  visible ~100-300ms, then the lesson paints directly — no flash. Slow path (ungenerated
  lesson → generation, or a slow Pi): skeleton appears after 200ms exactly as today.
- The activate card's `continueToLesson` keeps its immediate skeleton (it always leads to
  a 30-90s generation — delay would be wrong there).
- No timer bookkeeping beyond the seq/screen re-check — a stale callback self-noops.

## Testing

- **Backend (unit):** `streak_days` counts a quiz_round-only day; `recent_activity`
  includes quiz_round entries with score/total/format and tolerates malformed payloads;
  regression — existing event types unchanged.
- **Frontend (unit, node --test):** activity view renders the Arcade entry (and omits the
  score on malformed data); `arcadeResultHTML` renders miss chips sorted, with title
  fallback to lesson id, and renders identically to today when missed is empty.
- **app.js wiring (no DOM tests in this repo):** import-resolution check + live Pi
  verification: cached lesson opens with no skeleton flash; ungenerated/slow path still
  shows skeleton; Arcade result shows tappable chips that land in the right lesson with
  course context; dashboard streak and Activity reflect an Arcade round.

## Out of scope

- Removing the Arcade tab's per-course streak.
- Backend echo of missed-lesson titles in the round payload (banked rounds wouldn't have
  them; the manifest fetch covers all rounds).
- "Start session routes through due reviews" and the other sweep suggestions — separate
  decisions, not in this batch.
