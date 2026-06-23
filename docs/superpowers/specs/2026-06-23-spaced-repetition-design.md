# Claude University — Spaced Repetition (Slice 4)

**Date:** 2026-06-23
**Status:** Design — self-approved under the build charter (see [CHARTER.md](../../CHARTER.md))
**Builds on:** Slices 1–3. Closes roadmap done-item 1.

## For Werner (plain-language summary)

Right now the platform teaches a lesson once and never brings it back. This slice adds the
missing pillar: **spaced repetition.** When you finish a lesson's exercise you give a one-tap
**"how well did you recall this?"** rating (Again / Hard / Good / Easy), and the system schedules
when to show it to you again — soon if you struggled, much later if it was easy. The dashboard's
**"reviews due"** count becomes real, and a **Review** button walks you through the lessons that
are due, re-presenting their exercises. It's the Anki/SuperMemo model, built for one learner.

## Decisions made (self-approved under charter)

- **Self-rated recall (Anki-style)**, not auto-grading — unblocks SR now; objective checks come in Slice 5 and will sharpen it.
- **Algorithm: SM-2** (simple, four cheap fields, well-understood) over FSRS — right-sized for a personal tool.
- **Schedule is derived from the event log**, consistent with how all progress works — no new tables.
- **Finishing a lesson and reviewing it are the same flow**: attempt → reveal solution → rate. "Start session" picks the next un-studied lesson; "Review" picks due lessons. Both end in a rating.

## Architecture

One new pure backend module plus small wiring; no schema change.

1. **`backend/srs.py` (new) — the scheduler.** Pure functions over a lesson's review history:
   - `QUALITY` mapping the 4 ratings to SM-2 grades: `again→1, hard→3, good→4, easy→5`.
   - `sm2(reviews) -> {repetitions, interval_days, ease_factor, last_reviewed, next_review}` where
     `reviews` is a chronologically-ordered list of `{quality, date}`. Standard SM-2: grade `<3`
     resets repetitions and makes the item **due again today**; `>=3` advances (interval 1 → 6 →
     round(prev·EF)); EF updated and floored at 1.3.
   - `due_lesson_ids(conn, content_dir, course_id, today) -> [lesson_id]` — lessons with ≥1 review
     whose `next_review <= today`, in manifest order.
   - `reviews_due_count(conn, content_dir, course_id, today) -> int`.
2. **Events.** A new event type `lesson_reviewed` carrying `course_id`, `topic_id` (lesson id), and
   `payload = {"quality": "again|hard|good|easy"}`. No schema change — the events table already
   stores arbitrary `event_type` + `course_id` + `topic_id` + `payload`. The scheduler replays a
   lesson's `lesson_reviewed` events to compute its SM-2 state.
3. **Progress.** `courses.completed_lesson_ids` counts `event_type IN ('lesson_completed','lesson_reviewed')`
   so a reviewed lesson is "done" (back-compatible with existing data/tests). `list_courses`
   replaces the hardcoded `reviewsDue: 0` with `srs.reviews_due_count(...)`.
4. **API.** `GET /api/courses/<id>/reviews` → `{ "due": [lesson_id, …] }` (manifest order). The
   lesson content itself is served by the existing lesson endpoint (already cached).

## Data flow

```
finish lesson / review  ──▶ POST /api/events  lesson_reviewed{course_id, topic_id, quality}
dashboard "reviews due"  ◀── GET /api/courses (reviewsDue = srs.reviews_due_count, per course)
"Review" button          ──▶ GET /api/courses/<id>/reviews → due[]  → present each due lesson
                              (same lesson screen) → rate → lesson_reviewed → next due → done
```

## Frontend

- **Lesson finish becomes a rating.** After the solution is revealed, the Continue control is
  replaced by **"How well did you recall this?"** with four buttons (Again / Hard / Good / Easy).
  Tapping one logs `lesson_reviewed{quality}`, flushes, and returns to the course screen. This
  applies to both first-study and review (same screen).
- **Dashboard.** "Reviews due" shows the real per-course count. The existing **Review** button
  starts a review session: fetch `due[]`, present each due lesson through the lesson screen, rate,
  advance to the next due lesson; when none remain, return to the course with a brief "all caught
  up" state.
- **Pure view bits stay testable**; the review-session orchestration lives in `app.js` (browser
  wiring, verified end-to-end), matching the existing pattern.

## Testing

- **`srs.py` (pure):** SM-2 progression (1→6→interval·EF), EF update + 1.3 floor, `again` resets +
  due-today, `due_lesson_ids`/`reviews_due_count` against a fixture course + injected `today` and
  synthetic `lesson_reviewed` events. The bulk of the test value is here.
- **Backend wiring:** `list_courses` reflects a real `reviewsDue`; `GET …/reviews` returns due ids;
  `completed_lesson_ids` counts both event types.
- **Frontend:** the lesson view renders the rating control once the solution is revealed (with the
  four `data-quality` buttons); existing view tests stay green.
- **Real-browser + Pi:** finish a lesson → rate → it schedules; advance the clock or rate `again`
  → it shows as due → Review flow re-presents it. Deploy + verify on the Pi.

## Out of scope (deferred)

- Objective auto-grading of answers (Slice 5) — the rating is self-assessed for now.
- Mastery levels / adaptivity (Slice 6).
- A global cross-course review queue (consider with the home UX, Slice 7).
- FSRS, review-load caps, "bury/suspend," per-deck options — SM-2 only; YAGNI.

## Self-review notes

- **Single source of truth preserved:** schedule derived from `lesson_reviewed` events, not stored
  state — same principle as Slice 1 progress.
- **Unify study & review:** one lesson screen + one rating finish serves both, avoiding a parallel
  review UI.
- **Back-compatible:** counting both completion event types keeps existing progress/tests intact.
- **YAGNI:** SM-2 not FSRS; per-course not global; no suspend/bury/options.
