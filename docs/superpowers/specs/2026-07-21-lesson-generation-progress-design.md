# Live Lesson-Generation Progress — Design

**Date:** 2026-07-21
**Status:** Approved by Werner (brainstorm 2026-07-21)

## Problem

Generating a new lesson takes ~9 minutes and runs synchronously inside the browser's
HTTP GET. The learner stares at a skeleton with a *fake* cycling status line
(`views/loading.js` stages) that has no connection to what the model is actually doing.
Worse, the synchronous design has real failure modes, all observed in production:

- The 540s stream watchdog killed a heavy lesson generation → 502 (2026-07-21 incident;
  Sonnet 5 cleared the same lesson at 556.8s — a 43s margin, not a fix).
- A browser disconnect (tab close, phone lock, refresh) kills the generation via
  `GeneratorExit` — nine minutes of work lost.
- A mid-wait refresh spawns a *second* concurrent generation of the same lesson.

## Decisions (made with Werner, 2026-07-21)

1. **Display:** a live activity feed — real events in plain language (searches with
   their actual queries, pages being read, the model's own narration/thinking
   sentences, pipeline stage markers). The raw JSON the model emits is filtered out.
2. **Robustness:** generation runs as a **background job on the Pi**. Disconnects
   lose nothing; reattaching resumes the feed; duplicate starts join the existing job.
3. **Navigation:** free roam. A chip in the topbar shows "Generating lesson… m:ss"
   anywhere in the app and flips to "Lesson ready — open" (clickable) when done.
4. **Transport: polling.** The job keeps a numbered event log; the client asks
   "anything since event N?" every 2s. Chosen over SSE because waitress on the Pi
   runs the default 4-thread pool — a 9-minute held-open SSE stream pins a thread,
   while polling survives phone locks by design and the chip needs polling anyway.

## Architecture

```
openLesson (uncached)
  └─ POST /api/courses/<c>/lessons/<l>/generate      -- start or join job (202)
       └─ jobs.start() spawns a daemon thread
            └─ generation.ensure_lesson(...)          -- unchanged
                 ├─ run_sourced(on_event=...)         -- NEW: forwards each parsed
                 │    stream-json event to the job    --      event to a callback
                 └─ verify wrapper emits stage marks  -- audit / revise / saved
  └─ GET /api/courses/<c>/lessons/<l>/generate?since=N   -- poll every 2s
       └─ {status, error, elapsed, events[N:], next}
  └─ on status "done": existing loadLesson() → instant cache hit → lesson renders
```

### Backend

- **`backend/jobs.py` (new).** In-memory registry keyed `(course_id, lesson_id)`.
  One `Job` holds status (`running | done | error`), a numbered event log
  (`{"n", "kind", "text"}`), start/finish times, and the worker thread. `start()`
  joins an already-running job instead of duplicating. Finished jobs linger 10
  minutes so a briefly-disconnected client can still read the outcome, then are
  pruned lazily. In-memory is deliberate: a service restart kills the generation
  process anyway, so persisting job rows would only let us say "interrupted" with
  more ceremony — the `none` status (below) says it honestly for free.
- **`backend/claude_client.py`.** `run_sourced` gains `on_event` (called with every
  parsed stream-json event; default `None` = today's behaviour) and `timeout`
  (overrides the 540s `_STREAM_TIMEOUT`; the job uses 1200s because there is no
  longer an HTTP channel to race). New pure function `progress_events(ev)`
  translates one raw event into 0..n feed lines: WebSearch tool_use → "Searching:
  <query>", WebFetch → "Reading: <host>", thinking blocks → clipped "think" lines,
  narration text → clipped "say" lines, JSON payload text (starts with `{` or
  ` ``` `) → dropped. Lives here because this module owns CLI event shapes.
- **`backend/app.py`.** Three routes:
  - `POST /api/courses/<c>/lessons/<l>/generate` — validates ids/manifest, returns
    `done` immediately if the lesson file exists, else builds the same generation
    inputs as `get_lesson` (extracted into a shared `_lesson_gen_inputs` helper)
    and starts/joins the job. Returns the job snapshot from event 0 (backfill), 202.
  - `GET /api/courses/<c>/lessons/<l>/generate?since=N` — job snapshot from N. No
    job in memory: `done` if the lesson file exists, else `none` (never started, or
    lost to a service restart — client shows "interrupted, retry").
  - `GET /api/generation-jobs` — running jobs only (`courseId`, `lessonId`,
    `elapsed`), for reattach after a page reload.
  - Error translation to honest user-facing messages: auth → re-auth instruction;
    timeout → "took too long"; invalid-after-retry → says so; unexpected → says so.
  - The existing synchronous generation path in `get_lesson` **stays** as a
    fallback (direct API use, status-check-failure edge); the frontend simply stops
    driving it for new lessons.
- **Untouched:** `generation.py` (stage markers come from wrapping the `generate` /
  `verify_generate` callables in the route layer), the lesson prompt, validation,
  spine handling, `stream()`/chat SSE.

### Frontend

- **`views/genfeed.js` (new).** Pure HTML builders: feed card (title, elapsed,
  event list, "you can leave" note), one feed line (kind → CSS class, text already
  human-ready from the backend), error card with Retry, topbar chip
  (running / ready / failed states).
- **`courses.js`.** `startLessonGeneration`, `getGenerationProgress`,
  `listGenerationJobs` — same fetch-wrapper idiom as the rest of the file.
- **`app.js`.** `ui.genJob` state + polling loop (2s `setTimeout` chain). The
  uncached-lesson path (activate card's continue) paints the feed and POSTs
  instead of calling the blocking load. Poll ticks append feed lines when the feed
  is on screen (DOM-presence check, same idiom as `startLoading`) and repaint the
  chip slot every tick. On `done`: if the learner is watching, hand off to
  `finishOpenLesson` (now a cache hit); if roaming, chip flips to "ready". On
  `error`/`none`: honest error + Retry in the feed, or a "failed — retry" chip.
  On boot, `listGenerationJobs` reattaches to a running job. Chip clicks ride the
  existing root click delegation (feedback-bar pattern); cross-course clicks call
  `openCourse` first.
- **`views/shell.js`.** One added `<span data-gen-chip></span>` slot in the topbar.
- **Cached lessons are untouched:** the 200ms-delayed skeleton and instant opens
  behave exactly as today.

### Failure handling

| Failure | What the learner sees |
|---|---|
| Auth expired on the Pi | Feed/chip error: re-auth instruction (same text as today's 503) |
| Generation exceeds 1200s | "Generation took too long and was stopped — try again." + Retry |
| Model returns invalid lesson twice | Says exactly that + Retry |
| Pi service restarts mid-job | Poll gets `none` → "interrupted on the server" + Retry |
| Network blip while polling | Poll silently retries next tick; nothing is lost server-side |

### Testing

- Backend TDD throughout: `tests/test_jobs.py` (registry, join/dedup, event log,
  error capture, linger/prune), `test_claude_client.py` additions (translator
  cases, `on_event` forwarding, `timeout` plumbing), `tests/test_generation_jobs.py`
  (routes with a monkeypatched generator — no real model calls).
- Frontend: `node --test 'tests/*.test.js'` additions for `courses.js` helpers and
  `genfeed.js`; `app.js` wiring is covered by the import-resolution check and E2E
  (no app.js unit-test harness exists, per repo convention).
- Final proof: deploy to the Pi (canonical rsync, **never** `--delete`, confirm
  with Werner first) and generate a genuinely new lesson end-to-end watching the
  real feed.

## Out of scope (deliberate)

- Course compile, "go deeper" regeneration, capstone, and exam generation keep
  their current blocking behaviour. The job wrapper is generic enough for them to
  adopt later; nothing here blocks that.
- No push notifications, no sounds, no browser Notification API.
- No persistence of job history.
