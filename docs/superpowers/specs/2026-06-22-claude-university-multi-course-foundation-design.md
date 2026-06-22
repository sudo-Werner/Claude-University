# Claude University — Multi-Course Foundation (Slice 1)

**Date:** 2026-06-22
**Status:** Design — awaiting review

## For Werner (plain-language summary)

Today the app is hard-wired to a single Machine Learning course: the screens read
their content from one hardcoded file. This slice turns the app into an actual
**personal university** — a place that holds *many* courses, where ML is simply the
first one. You open it to a grid of your courses, each showing its progress, and one
click drops you back into where you left off.

This slice does **not** build the "talk to Claude to create a course" feature — that's
Slice 2. Here we build the foundation underneath it: how a course is stored, how the
home screen lists your courses, and how picking a course feeds the lesson screens you've
already styled. The "Add course" button appears but does nothing yet (on purpose).

**What you'll be able to verify when it's done:** open the app, see a grid with your ML
course and its real progress; click it, land on that course's session screen; start a
lesson; come back later and "continue" returns you to the next unfinished lesson.

## Goal

Convert the platform from a single hardcoded course into a multi-course system with a
stored content model, a university-home course grid, per-course progress derived from
events, and a navigation hierarchy (home → course → lesson). Migrate the existing ML
content into the new model as the first stored course.

## Scope

**In scope**
- A file-based content store on the Pi: course manifests + per-lesson files.
- Migration of the current `seed.js` ML content into that store as the first course.
- A `course_id` field on events so progress is per-course.
- Backend read endpoints: list courses (with derived progress + next lesson), fetch a
  course manifest, fetch a single lesson.
- Frontend: university-home view (equal course grid), repurposing the current dashboard
  as the per-course session screen, lesson flow fed by stored content, navigation
  hierarchy replacing the two global tabs, and an inert "Add course" button.
- "Continue where you left off" derived from progress.

**Out of scope (deferred)**
- Slice 2: the conversational course-creation flow, the Claude/Agent-SDK integration,
  outline generation, and just-in-time lesson generation with look-ahead. The "Add
  course" button is a placeholder seam for this.
- The spaced-repetition scheduling engine (FSRS). "Reviews due" is displayed as a count
  where data exists, but the scheduling engine remains deferred as in earlier plans.
- Multi-user. Still single-user (Werner).

## Decisions made during brainstorming

- **Course authoring model (Slice 2):** a conversation with Claude — Werner describes
  what and how intensively he wants to learn; Claude generates and adds the curriculum.
- **Where:** inside the web app, kicked off by an "Add course" button.
- **Generation timing (Slice 2):** outline up front, lessons just-in-time, with a small
  look-ahead buffer (pre-generate the next lesson) so a session never waits on the model.
- **Home layout:** equal course grid (all courses as equal cards), not a hero. Scales
  cleanly as the university grows. Global streak in the header; the 90-minute session
  timer lives inside a course session, not on the home.
- **Content storage:** JSON files on the Pi, not database rows — writable by the backend
  (so Slice 2's generator just drops files in), inspectable, and git-friendly. The
  database stays for telemetry/progress.

## Architecture overview

Three conceptual levels, mirroring the navigation:

1. **University home** (new) — a grid of course cards. Each card: title, subtitle,
   progress bar, reviews-due count (where available), and a Continue button. Plus an
   inert "Add course" card.
2. **Course session screen** — the *current* dashboard screen, repurposed. Instead of
   reading `DASHBOARD_SEED`, it renders the selected course's next topic, progress,
   the 90-minute session timer, and reviews due.
3. **Lesson flow** — the current lesson screen, fed by the selected course's stored
   lesson content instead of `SAMPLE_LESSON`.

Content is read-only in this slice and served by the Pi from JSON files. Progress is
*derived* from the event log (no separate progress table), keeping events as the single
source of truth.

## Content model (file-based, on the Pi)

```
content/courses/
  machine-learning/
    course.json                 # the manifest: identity + curriculum structure
    lessons/
      ml-m3-l2.json             # one file per lesson (the rich content)
      ...
```

**`course.json` (manifest):**
```json
{
  "id": "machine-learning",
  "title": "Machine Learning",
  "subtitle": "From fundamentals to neural networks",
  "modules": [
    {
      "id": "m3",
      "title": "Neural Networks",
      "lessons": [
        { "id": "ml-m3-l2", "title": "Backpropagation, intuitively" }
      ]
    }
  ]
}
```

The manifest holds *identity and ordering only* — module/lesson titles and the sequence.
It is the map. Lesson bodies live in their own files so they can be generated/fetched
independently (and, in Slice 2, written just-in-time).

**Lesson file (`lessons/<lessonId>.json`):** the shape the styled lesson screen already
consumes, lifted from `SAMPLE_LESSON`:
```json
{
  "id": "ml-m3-l2",
  "courseId": "machine-learning",
  "topic": "Backpropagation",
  "step": 4,
  "totalSteps": 5,
  "eyebrow": "EXERCISE",
  "promptHtml": "...",
  "hintHtml": "...",
  "solutionAns": "...",
  "solutionNote": "..."
}
```

**Migration:** the existing `DASHBOARD_SEED`/`SAMPLE_LESSON` content in
[seed.js](../../../frontend/src/seed.js) is moved into one `machine-learning` course
(manifest + at least the one existing lesson). `seed.js` is removed once nothing imports
it. Hand-authored JSON here is exactly the shape Slice 2's generator will later produce.

## Progress model (derived from events)

- Add a nullable `course_id` column to the `events` table (additive migration; existing
  rows keep `NULL`).
- Lesson/session events carry `course_id` (and a lesson identifier in `payload` or
  `topic_id`).
- A course's progress is computed on read: **lessons completed** = count of distinct
  lessons in the manifest that have a completion event for that course; **total** =
  count of lessons in the manifest. `pct = done / total`.
- **Next lesson / "continue where you left off"** = the first lesson in manifest order
  (module order, then lesson order) without a completion event. If all complete, the
  course is done; Continue points at the last lesson or a "course complete" state.

An explicit `lesson_completed` event type is introduced (carrying `course_id` and the
lesson id), emitted when the learner finishes the final step of a lesson. Completion is
counted from these events, not inferred from `lesson_view`/`lesson_continue`, so the
"done" count is unambiguous. The manifest's ordering is authoritative for "next".

## Backend (Flask) — read endpoints

All under the existing app, serving from the `content/courses/` directory.

- `GET /api/courses` → list of course summaries:
  `[{ id, title, subtitle, progress: { done, total, pct }, nextLessonId, reviewsDue }]`.
  Progress and nextLessonId are derived by joining each manifest against the event log.
- `GET /api/courses/<courseId>` → the full manifest (modules + lessons).
- `GET /api/courses/<courseId>/lessons/<lessonId>` → the lesson file's content.

Behaviour: unknown course/lesson → 404. Manifests and lesson files are read from disk per
request (single user, small content — no caching needed; measure before optimising).

## Frontend — views and navigation

**Navigation model** replaces the two global tabs with a hierarchy held in UI state
(`ui.screen`: `"home" | "course" | "lesson"`, plus `ui.courseId`, `ui.lessonId`):

- App opens → diagnostic if no profile (unchanged) → **home**.
- Home: render the course grid from `GET /api/courses`. Tapping a course sets
  `ui.courseId`, loads its manifest, and goes to **course**. "Add course" is inert
  (logs an event, shows a "coming soon" affordance).
- Course session screen (repurposed dashboard): fed by the selected course's manifest +
  derived progress + next lesson. "Start session" / "Continue" loads the next lesson and
  goes to **lesson**. A back affordance returns to **home**.
- Lesson flow: fed by `GET /api/courses/<id>/lessons/<lessonId>`. Back returns to the
  **course** screen.

**Files**
- New: `frontend/src/views/home.js` — `homeHTML(courses)` renders the equal course grid
  (course cards + "Add course" card). Pure function, unit-tested like the other views.
- New: `frontend/src/courses.js` — client helpers `listCourses({fetch})`,
  `loadCourse({fetch, courseId})`, `loadLesson({fetch, courseId, lessonId})`. Injected
  `fetch`, unit-tested with a fake.
- Modify: `frontend/src/views/shell.js` — header adapts to context (home title vs. a
  back-to-home affordance in a course); the `Dashboard`/`Lesson` `<button data-tab>`
  controls are removed in favour of the hierarchy.
- Modify: `frontend/src/views/dashboard.js` — accept a course object instead of
  `DASHBOARD_SEED`; otherwise the styled layout is unchanged.
- Modify: `frontend/src/views/lesson.js` — already takes a `lesson` arg; now fed from the
  fetched lesson file rather than `SAMPLE_LESSON`. Layout unchanged.
- Modify: `frontend/src/app.js` — replace `tab` state and `switchTab` with the
  screen-hierarchy state machine above; wire the course-list/manifest/lesson fetches;
  keep the existing event logging (now stamped with `course_id`).
- Remove: `frontend/src/seed.js` once unreferenced (content now lives on the Pi).

The styled CSS (phone-first + the new desktop media query) is reused. The course grid
gets its own responsive treatment in `styles.css` (cards stack on phone, grid on
desktop), consistent with the existing tokens.

## Testing

- **Backend (pytest):** `GET /api/courses` returns the seeded ML course with correct
  derived progress given a set of events; `GET /api/courses/<id>` returns the manifest;
  lesson endpoint returns a lesson and 404s on unknown ids; progress/next-lesson
  derivation is correct for none/partial/all-complete event sets.
- **Frontend (node --test):** `homeHTML` renders a card per course with its progress and
  a Continue control; `courses.js` helpers call the right endpoints and parse responses
  (fake `fetch`); next-lesson derivation if it lives client-side. Existing view tests
  updated for the dashboard/lesson signature changes.
- **Real-browser (Playwright):** open from the Pi → home shows the ML course grid → click
  it → course screen → start a lesson → return and confirm "continue" resolves to the
  next unfinished lesson; confirm a `course_id`-stamped event reaches the Pi DB.

## Self-review notes

- **Single source of truth:** progress is derived from events, not duplicated in a table.
- **One job per unit:** manifest = structure; lesson files = content; `courses.js` =
  fetching; `home.js` = rendering. Each is independently testable.
- **YAGNI:** no content caching, no SR engine, no generation, no multi-user — all
  deferred until there's an actual need (Slice 2 or later).
- **Slice boundary:** nothing here depends on Claude/the Agent SDK; Slice 1 is fully
  buildable and verifiable in the current Flask + SQLite + ES-module stack.
