# Claude University — Curriculum & Lesson-Player UX (Slice 7)

**Date:** 2026-06-24
**Status:** Design — self-approved under the build charter (see [CHARTER.md](../../CHARTER.md))
**Builds on:** Slices 1–6. Closes roadmap done-item 6 + the UX half of 4–5.

## For Werner (plain-language summary)

Right now you can only move through a course one lesson at a time — "Start session" always opens the
*next* unfinished lesson, and there's no way to see the whole course or jump to a specific lesson.
This slice adds a **curriculum view**: an expandable list of modules and lessons with a checkmark on
the ones you've finished, the mastery badge you earned, and per-module progress — tap any lesson to
open it. And it adds a **player nav bar** in the lesson itself (Curriculum · Prev · Next · "Lesson X
of Y") so moving around feels like a real course player. This is the structure-and-navigation layer
Udemy/Coursera have; it's the visible payoff of the mastery work from the last slice.

## Decisions made (self-approved under charter)

- **Adapt the "two-panel player" to the narrow layout.** The app is a deliberate ~448px warm-glass
  column (phone-first). A desktop side-by-side content+sidebar player doesn't fit, so the curriculum
  becomes a **dedicated screen (accordion)** you jump to, and the lesson gains a compact **player nav
  bar**. Same information architecture, right-sized for the column. (A wide desktop redesign is a
  separate, larger decision — not in scope.)
- **No backend change.** Slice 6's `mastery` map already contains exactly the *completed* lessons
  (mastery is computed only for completed lessons), so: lesson **done** ⇔ `lessonId in mastery`, and
  its **badge** = `mastery[lessonId]`. The manifest gives module/lesson structure; the lesson JSON's
  `step`/`totalSteps` already give "X of Y". This stays a pure frontend slice — Pi-light.
- **Jump to any lesson.** Tapping a lesson in the curriculum opens *that* lesson (generating it
  just-in-time on first open, exactly as today). Generalize the current next-only `startLesson` into
  `openLesson(lessonId)`.
- **Player nav = Curriculum · Prev · Next.** Prev/Next move to adjacent lessons in course order;
  Curriculum jumps to the accordion. "Lesson X of Y" already renders (lesson `step/totalSteps`).
- **"Continue Learning" already exists** — the course dashboard's "Today's session" card is
  continue-where-you-left-off, and home cards say "Continue →". No new hero needed (YAGNI).
- **Generated metadata (objectives[] / difficulty) deferred.** It would touch course generation and
  is separable from the navigation gap; revisit only if it earns its place. Keeps this slice tight.

## Navigation (after this slice)

```
home (grid) ──▶ course (dashboard: today's session, progress, reviews, mastery)
                   │  "View all lessons" ──▶ curriculum (accordion)
                   │  "Start session" ─────▶ lesson (next incomplete)
                                              ▲   curriculum tap (any lesson) ─┘
   lesson nav bar: Curriculum · Prev · Next  ─┘   (+ Back → course)
```

## Components

1. **`frontend/src/views/curriculum.js` (new, pure).**
   - `curriculumHTML(manifest, mastery, currentId) -> string` — renders the accordion:
     - For each module: a header with its title and per-module progress ("2/3"), then its lessons.
     - Each lesson row: a status marker (✓ if `mastery[lessonId]` exists; a "current" dot if it
       equals `currentId` and isn't done; otherwise a neutral dot), the lesson title, and — when
       completed — a small mastery badge (`attempted/familiar/proficient/mastered`). The row is a
       `<button data-lesson="<id>">` so app.js can open it.
     - "Lesson N of M" / overall progress header at the top.
   - Helpers: `lessonStatus(lessonId, mastery, currentId)`; `moduleProgress(module, mastery)`.
     Reuses the four mastery level strings from Slice 6 (lowercase keys, labels Title-cased).

2. **App wiring (`frontend/src/app.js`).**
   - New screen `ui.screen = "curriculum"`; `showCurriculum()` / `paintCurriculum()` render
     `curriculumHTML(ui.manifest, ui.manifest.mastery || {}, currentLessonId())` and bind each
     `[data-lesson]` to `openLesson(id)`. Reached from the dashboard's "View all lessons" button and
     the lesson nav's "Curriculum" button. Back → course.
   - Generalize `startLesson` → `openLesson(lessonId)` (loads that lesson, sets lesson state, logs
     `lesson_view`, starts the timer, shows the lesson). `startLesson` becomes
     `openLesson(nextLesson.id)`.
   - `currentLessonId()` = the open lesson's id if in/most-recently a lesson, else the dashboard's
     next-incomplete lesson id.
   - Prev/Next compute adjacent ids from the flattened manifest order and call `openLesson`.

3. **Dashboard (`frontend/src/views/dashboard.js`).** Add a **"View all lessons"** (curriculum)
   button to the session card area, wired in `paintCourse`.

4. **Lesson player nav (`frontend/src/views/lesson.js`).** Add a compact nav row with
   **Curriculum**, **Prev**, **Next** controls (data-action hooks), alongside the existing Back. Prev
   disabled on the first lesson, Next disabled on the last (pass `hasPrev`/`hasNext` into
   `lessonHTML`, derived in app.js from manifest order). "Lesson X of Y" already shows via
   `step/totalSteps`.

5. **Styles (`frontend/styles.css`).** Accordion (module headers, lesson rows, status markers,
   mastery badges) + the lesson nav controls, in the warm-glass theme (reuse `--glass-*`, the
   existing `.stat`/`.eyebrow`/badge patterns, and the Slice-6 `.mastery` chip styling).

## Data flow

```
GET /api/courses/<id>  ─▶  manifest {modules[], mastery{lessonId:level}}  (already exists)
   manifest.modules ──────▶ accordion structure
   manifest.mastery ──────▶ per-lesson ✓ (key present) + badge (value)
   flattened order ───────▶ Prev/Next + "lesson N of M"
tap a lesson ──▶ openLesson(id) ──▶ loadLesson (JIT-generate on first open) ──▶ lesson screen
```

## Testing

- **Frontend (pure):** `curriculumHTML` renders a module header with progress, a lesson row per
  lesson, a ✓/badge for a completed lesson (in the mastery map), a "current" marker for the
  `currentId`, and `data-lesson` hooks; `lessonStatus`/`moduleProgress` return the right values for
  done / current / not-started and for partial module completion. `lessonHTML` renders the
  Curriculum/Prev/Next nav and disables Prev on first / Next on last (via `hasPrev`/`hasNext`).
- **App wiring** is browser-verified (consistent with the existing pattern — app.js isn't unit
  tested).
- **Real-browser + Pi:** create a multi-module course; open the curriculum; confirm structure,
  completion ✓ + mastery badge after finishing a lesson, and per-module progress; tap a non-next
  lesson and confirm it opens (generating if needed); use Prev/Next/Curriculum in the player.

## Out of scope (deferred)

- Generated course metadata (`objectives[]`, `difficulty`) and a "what you'll learn" panel — touches
  generation; revisit if it earns its place.
- A wide/desktop two-panel (side-by-side content+sidebar) layout — would mean leaving the phone-first
  column; a separate, larger decision.
- A dedicated home "Continue Learning" hero — the dashboard session card + grid "Continue →" already
  cover it.
- Mark-complete buttons — lessons complete via the end-of-lesson recall rating; a separate control
  would be redundant.

## Self-review notes

- **Pure frontend, no schema/API change** — reuses the Slice-6 course payload (manifest + mastery);
  completion is read straight from the mastery map's keys. Pi footprint unchanged.
- **Right-sized to the layout** — accordion + nav bar instead of a side panel that wouldn't fit.
- **Surfaces existing value** — finally shows the mastery the platform already computes, per lesson.
- **Lean** — no new endpoints, no generated metadata, no redundant mark-complete; navigation only.
