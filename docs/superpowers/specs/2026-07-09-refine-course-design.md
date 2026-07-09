# Refine This Course — Design Spec

**Date:** 2026-07-09
**Status:** Approved in principle (Werner: "Syllabus edits, approve first"). Autonomous build under the charter.
**Closes:** Werner's post-migration request — "add a button where I can initiate a further discussion on the course and have Claude change the course based on the discussion."

## The goal (one paragraph)

From a course's dashboard, Werner can open a discussion with Claude about how the course
should change ("add a module on X", "this is too basic, go deeper", "drop the last two
lessons", "reorder so Y comes first"), and Claude proposes a **revised syllabus** — modules
and lessons added, removed, renamed, reordered — which Werner **reviews and approves before
anything is written**. Lessons that survive the revision keep their identity: their id, their
already-generated lesson body, and all their progress/mastery/review history. New lessons are
minted fresh and generate just-in-time on first open, exactly like any lesson. Removed lessons
drop out of the course.

## Why this is a third path (not a reuse of the existing two)

The compiler already has two entry points, and neither fits:

- `compile_course` (new-course intake): builds everything fresh, all ids minted new. No
  existing identity to preserve.
- `enrich_course` (migration): preserves every id but **freezes the structure** — the enrich
  prompt explicitly says "do NOT add, remove, reorder, or rename any module or lesson." That is
  the opposite of what refine needs.

Refine is the missing middle: **structure changes, retained identity survives.** This requires
a new compiler function `revise_course` and a new persistence function `apply_revision`, plus a
route pair and a frontend flow that parallels the existing intake → syllabus → create flow.

## How identity is preserved across a structural change

The hard problem: after Claude rewrites the syllabus, which proposed lesson corresponds to
which existing lesson (so we keep its id, body, and progress)? We put that judgment where it
belongs — on the model, which understands "this is the same lesson, retitled" versus "this is
brand new."

The grounded revise call returns a revised outline in which **every lesson carries an optional
`keepId`**:

- `keepId` = an existing lesson id → this proposed lesson *continues* that existing lesson
  (kept as-is, or renamed, or moved to another module). It keeps that id, its cached body file,
  and its progress.
- `keepId` absent/null → a **brand-new** lesson. It gets a freshly minted id
  (`<course_id>-l<N>`, N continuing past the highest existing lesson number so it never
  collides with a retained id) and no cached body — it generates on first open.
- An existing id that no proposed lesson references by `keepId` is a **removed** lesson.

`revise_course` enforces the rules the model can get wrong: each `keepId` must be a real
existing id, used **at most once** (a duplicate or unknown `keepId` is treated as "new" — the
lesson gets a fresh id rather than hijacking or colliding). The proposed course it returns
already has its **final ids**, so the review screen shows exactly what will be written.

## Objectives, prereqs, and the accuracy sweep

The revised outline runs the **existing per-module objectives stage** (`_objectives_and_graph`,
already timeout-safe via per-module batching) so new lessons get objectives and the **prereq
graph is recomputed for the new structure/order**. Then we **overlay**: any retained lesson
(one with a `keepId`) keeps its **existing objectives** (its previously approved wording is
authoritative — we don't churn content Werner didn't ask to change), while its **prereqs use
the freshly computed graph** (because order/structure moved). New lessons keep their fresh
objectives and prereqs.

The **accuracy sweep is skipped** on revision. The sweep is a slow (~10 min, web-grounded)
whole-course content audit whose corrections we already had to guard against structural drift
during migration. Retained content was already swept when it was first built; new lessons get
the audit-first self-consistency verification at generation time (`ensure_lesson`). Skipping it
keeps revise fast and Pi-light and avoids re-introducing the structure-drift risk.

## Data flow (parallels intake → syllabus → create)

```
Course dashboard
  └─ "Refine this course" button
       └─ Refine chat  (seeded: "You're refining <title>. What should change?")
            └─ "Propose changes"  → POST /api/courses/<id>/revise   { messages }
                 → revise_course(manifest, messages)  [grounded outline + objectives, NO sweep, NOT persisted]
                 → returns { course: <proposed, final ids>, changeSummary: [...], progressAtRisk: [...] }
            └─ Review screen  (syllabusHTML(proposed) + "What's changing" + progress-at-risk warning)
                 ├─ "Keep discussing" → back to Refine chat
                 └─ "Apply changes"  → POST /api/courses/<id>/apply-revision  { course }
                      → apply_revision(content_dir, id, course)  [validate, back up, in-place write]
                      → reload course, return to dashboard
```

Mirrors the existing `compile` (non-persisting, returns proposal) / `create` (persists) split,
so the two review gates behave the same way and share `syllabusHTML`.

## Backend

### `compiler.revise_course(existing_manifest, messages, *, generate_sourced, verify)`

1. `_revise_outline_prompt(existing_manifest, messages)` → grounded call (`generate_sourced`,
   web) → a revised outline: `title`/`subtitle`/`level` (may change), `modules` each with
   `lessons` carrying `title`, optional `keepId`, `estMinutes`; plus `changeSummary`
   (list of short human-readable strings) and `groundingSources`.
2. Resolve ids: build the id-bearing outline — retained lessons take their `keepId`; new
   lessons get `<id>-l<N>` (N past the current max). Enforce keepId validity + single-use.
3. Run `_objectives_and_graph` on the resolved outline (per-module, timeout-safe); merge with
   `_merge_objectives`; **overlay** existing objectives onto retained lessons.
4. Assemble the contract (reuse `_assemble_contract`), set `id = existing_manifest["id"]`,
   carry `changeSummary` and a `progressAtRisk` list (removed lesson ids/titles that have any
   completion in the event log — computed in the route, which has the DB; compiler stays
   DB-free).
5. Return the proposed course. **Not persisted.**

### `courses.apply_revision(content_dir, course_id, revised)`

- Strictly validate: `revised["id"] == course_id`; `generation.valid_compiled_course(revised)`;
  every lesson id is either an existing id or matches `^<course_id>-l\d+$`; no duplicate ids.
  Reject (return None / raise) otherwise — the client is not trusted to write arbitrary JSON.
- **Back up** the current `course.json` → `course.json.pre-revise-<UTC-stamp>` (same safety net
  migration used).
- Atomic in-place write of the revised manifest to the existing `course.json` (temp file +
  `os.replace`), preserving the course dir and every retained lesson's cached body under
  `lessons/`.
- **Removed lessons:** dropped from the manifest only. Their cached body files are **left in
  place** (harmless, tens of KB) so restoring the pre-revise backup fully reverts the revision.
  Their progress events remain in the log but no longer surface, since course progress derives
  from the manifest's lesson set.
- Return the written manifest.

### Routes (in `create_app`)

- `POST /api/courses/<course_id>/revise` — `{messages: [...]}`. Loads the manifest (404 if
  missing / bad id), runs `revise_course` with the same `generate_sourced`/`verify` lambdas the
  compile route uses, computes `progressAtRisk` from the DB, validates the result
  (`valid_compiled_course`), returns `{course, changeSummary, progressAtRisk}`. Same
  `ClaudeAuthError`→503 / `ClaudeError`→502 handling as the other generation routes.
- `POST /api/courses/<course_id>/apply-revision` — `{course: <approved proposal>}`. Calls
  `apply_revision`; 400 on validation failure, 404 if the course is gone, returns
  `{course: <written manifest>}` on success.

## Frontend

- **dashboard.js:** a "Refine this course" secondary button (near "View all lessons"),
  `data-action="refine"`.
- **app.js:** `startRefine()` → refine chat screen; `proposeRevision()` → POST `/revise`,
  show review; `applyRevision()` → POST `/apply-revision`, reload course → dashboard. New
  `ui.screen` values `"refine"` and `"revision"`; a `"revising"` loading state reusing the
  existing shimmer.
- **courses.js:** `reviseCourse({fetch, courseId, messages})` and
  `applyRevision({fetch, courseId, course})`.
- **Review screen:** `syllabusHTML(proposed)` (reused as-is) + a "What's changing" list
  (`changeSummary`, each `esc()`-escaped) + a progress-at-risk callout when `progressAtRisk` is
  non-empty ("Progress on N lesson(s) will no longer count: …"). Buttons: **Apply changes** /
  **Keep discussing**. All model-authored text `esc()`-escaped, per the app's rule.

## Safety / guarantees

- **Approve-first:** nothing is written until Werner clicks Apply on the review screen.
- **Reversible:** a `course.json.pre-revise-<stamp>` backup is written before every apply, and
  removed lessons' bodies are retained — restoring the backup fully reverts.
- **Progress preserved:** retained lessons keep id + body + all events. Progress that *would* be
  lost (removed lessons with history) is surfaced before Apply, never silently dropped.
- **Trust boundary:** apply re-validates the submitted course server-side (id set, schema,
  patterns) — the round-tripped proposal is not written blindly.
- **Pi-light:** reuses the timeout-safe per-module objectives stage; skips the heavy sweep.

## Explicitly NOT in scope (YAGNI)

- Regenerating retained lessons' bodies (Werner can already "Explain it more deeply" per
  lesson). Refine changes the *syllabus*, not existing lesson prose.
- Editing individual lesson bodies through this flow.
- Undo UI (the pre-revise backup on disk is the recovery path; restoring it is a manual/CLI
  step, acceptable for a single-user app).
- Diffing objectives text on the review screen (the "What's changing" summary + the syllabus
  render are enough).

## Testing

- `revise_course`: retained `keepId` lessons keep ids + existing objectives; new lessons get
  fresh non-colliding ids + generated objectives; duplicate/unknown `keepId` demoted to new;
  removed id absent from result; prereqs recomputed and valid; result passes
  `valid_compiled_course`; sweep NOT invoked (monkeypatched to explode if called).
- `apply_revision`: in-place write to the same dir; backup created; retained body files
  untouched; id-set/schema validation rejects a tampered course (foreign id, bad pattern,
  duplicate); atomic (no partial file on failure).
- Routes: `/revise` returns course+changeSummary+progressAtRisk and does not persist;
  `progressAtRisk` reflects real completion events; `/apply-revision` writes and 400s a bad
  payload; auth/error mapping.
- Frontend: dashboard renders the Refine button; review renders changeSummary + progress-at-risk
  (escaped); `reviseCourse`/`applyRevision` call the right endpoints; XSS test on changeSummary.
