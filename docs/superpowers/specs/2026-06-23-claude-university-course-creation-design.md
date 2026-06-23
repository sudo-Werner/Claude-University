# Claude University — Conversational Course Creation & JIT Lessons (Slice 2)

**Date:** 2026-06-23
**Status:** Design — awaiting review
**Builds on:** Slice 1 (multi-course foundation) — stored JSON courses, per-course progress from events, home → course → lesson navigation.

## For Werner (plain-language summary)

Slice 1 made the platform multi-course but courses had to be hand-authored. This slice
makes the **"Add a course" button come alive**: you open a chat, tell Claude what you want
to learn and how intensively, and when it has enough it proposes a curriculum you approve.
The course then appears in your grid. Lessons aren't all written up front — each lesson is
**generated the moment you reach it**, shaped by how you learn (your diagnostic profile) and
what the course is for.

Claude runs on the Pi through your **Max subscription** (via the Claude Code already
installed and logged in there) — **no API key, no per-use bill**. The only cost is your
normal Max usage limits.

**The one big risk:** I've confirmed Claude Code and your subscription login exist on the
Pi, but I have *not* yet confirmed that a background service can drive Claude
non-interactively with that login. So the very first task is a **spike** to prove it. If it
fails, we stop and rethink before building anything on top — better to find out first.

**What you'll verify when it's done:** click "Add a course", chat with Claude, approve a
proposed curriculum, see the new course in your grid, open it, and get a generated first
lesson — all on the Pi, on your subscription.

## Goal

Turn the inert "Add a course" seam into a working conversational course-creation flow backed
by Claude (via the Pi's Max-subscription Claude Code), and generate lesson content
just-in-time when a learner reaches a lesson that hasn't been written yet.

## Decisions made during brainstorming

- **Interaction:** open multi-turn chat. Claude asks follow-ups; when ready it proposes a
  curriculum with a "Create this course" button; nothing is saved until the learner confirms.
- **Chat replies stream** token-by-token (SSE). The structured pieces — the curriculum
  proposal and each generated lesson — are request/response with a loading state, not streamed.
- **Generation timing:** outline up front, lessons just-in-time. **Look-ahead pre-generation
  is deferred** (a learner waits a few seconds with a "preparing your lesson" state).
- **Generated lessons conform to the existing lesson schema** (`promptHtml`/`hintHtml`/
  `solutionAns`/`solutionNote`, etc.) so the Slice 1 lesson screen renders them unchanged.
- **Claude runs via the Pi's Max-subscription Claude Code**, not the metered Messages API.
- **The creation chat is ephemeral** — only the confirmed outline and a generation-context
  summary persist.

## Architecture overview

Four units, each independently testable:

1. **`claude_client` (backend):** the single boundary to Claude. Wraps invoking the Pi's
   Claude Code CLI (`claude -p`) under the existing subscription auth. Two entry points: a
   **streaming** call (for chat) and a **structured** call (prompt → validated JSON, with
   one retry on invalid JSON). Everything else depends on this and nothing else knows how
   Claude is invoked.
2. **Course-creation chat (backend + frontend):** a chat endpoint that relays the learner's
   messages + history to `claude_client` (streaming the reply as SSE), a system prompt that
   makes Claude act as a curriculum designer and emit a curriculum proposal when ready, and
   a "create course" endpoint that writes the manifest + generation-context on confirm.
3. **JIT lesson generation (backend):** when a lesson file is requested but doesn't exist,
   generate it via `claude_client` (structured), validate against the lesson schema, write
   it to the content store, and return it.
4. **Hardening (frontend + backend):** HTML-escape generated course title/subtitle in the
   home view; validate `course_id`/`lesson_id` route params against a safe pattern.

```
Browser chat ──SSE──▶ /api/courses/chat ──▶ claude_client.stream ──▶ claude -p (stream-json)
Browser "Create" ────▶ /api/courses (POST) ─▶ writes content/courses/<id>/course.json
Open lesson (Slice 1) ▶ GET …/lessons/<id> ─▶ if missing: claude_client.structured ─▶ write + serve
```

## How Claude is invoked (the boundary)

The Pi already has Claude Code (`~/.local/bin/claude`, v2.1.x) authenticated with Werner's
Max subscription (`~/.claude/.credentials.json` → `claudeAiOauth`). The backend shells out
to it:

- **Structured (outline, lessons):** `claude -p "<prompt>" --output-format json` — capture
  the result text, extract JSON, validate against the target schema; on invalid/missing JSON,
  retry once with a corrective prompt; on second failure, surface a clear error.
- **Streaming (chat):** `claude -p "<prompt>" --output-format stream-json --verbose` — read
  the line-delimited JSON events from stdout and relay assistant text deltas to the browser
  as SSE; accumulate the full turn for history.
- **Auth/env:** the service runs as `werner`; the invocation sets `HOME=/home/werner` and a
  `PATH` including `~/.local/bin` so the CLI and its credentials resolve. Concurrency: one
  Claude invocation at a time is acceptable (single user); calls run in a worker so a long
  generation doesn't wedge the Flask request thread beyond its own request.
- **Model:** selectable via `--model`; **default Sonnet 4.6** to conserve Max usage limits,
  with the option to raise to Opus for higher-quality generation. (This is a usage-limit
  tradeoff, not a per-token bill — surfaced for Werner's choice.)

**This boundary is exactly what the spike (below) must prove works headless.**

## The conversation → course flow

- **System prompt** frames Claude as a curriculum designer for *one* learner: it should ask
  about goal, depth, prior knowledge, and intensity/pace, keep turns short, and when it has
  enough, output a curriculum proposal. The learner's stored diagnostic profile (`/api/profile`)
  is included so the conversation is already personalized.
- **Proposal contract:** Claude signals a finished proposal by emitting a fenced
  ```course block containing JSON: `{ title, subtitle, brief, modules: [{ title, lessons:
  [{ title }] }] }` where `brief` is the generation-context summary (audience level, depth,
  pace, goals). The backend detects this block in the stream, parses it, and the frontend
  renders it as a proposal card with a **"Create this course"** button. Conversational text
  before the block streams normally.
- **Create:** `POST /api/courses` takes the approved proposal, allocates a course id (slug of
  the title, de-duplicated), writes `course.json` (the Slice 1 manifest shape **plus** a
  `brief` field and stable `id`s for modules/lessons), and returns the new course summary.
  The chat transcript is discarded.
- **Manifest extension:** `course.json` gains a top-level `brief` string (the saved
  generation context). Slice 1's read endpoints ignore unknown fields, so this is additive.

## JIT lesson generation

- Slice 1's `GET /api/courses/<id>/lessons/<lessonId>` returns the lesson file if present.
  This slice: **if the file is absent**, generate it before responding.
- The generation prompt is built from: the course `brief`, the learner profile, the lesson's
  title + its module title, and the lesson's position in the course (for continuity). It asks
  for a single lesson object matching the existing lesson schema.
- The result is validated (required fields present, correct types); on success it's written
  to `content/courses/<id>/lessons/<lessonId>.json` (so it's generated once, then cached as a
  normal stored lesson) and returned. On failure: one retry, then a clear error the UI shows
  as "couldn't prepare this lesson — try again".
- The frontend shows a "preparing your lesson…" state while this runs (it can take seconds).

## Frontend

- **Chat surface:** the "Add a course" button opens a chat view (new `views/chat.js` +
  `chat.js` client helper). Messages render incrementally from the SSE stream; a proposal
  block renders as a card with the "Create this course" button; confirming calls
  `POST /api/courses` and navigates to the new course (Slice 1's course screen).
- **Lesson loading:** the existing lesson open path gains a loading state for the JIT wait.
- **Hardening:** `home.js` escapes course `title`/`subtitle` before interpolation (generated
  text is now untrusted-ish); the course/lesson API routes reject ids not matching
  `^[a-z0-9-]+$` with a 404.

## Error handling

- Claude Code not runnable / not authenticated → the chat and generation endpoints return a
  clear error; the UI surfaces "Claude isn't available right now" rather than hanging.
- Malformed JSON from a structured call → one corrective retry, then a surfaced error.
- Generation timeout → bounded wait; surfaced error, learner can retry. No partial lesson is
  written.
- A failed JIT generation never corrupts progress (no `lesson_completed` is involved).

## Testing

- **`claude_client`:** unit-test the JSON extraction/validation/retry logic with a **fake
  invoker** (inject the subprocess runner) — no real Claude calls in unit tests. The streaming
  parser is tested against recorded `stream-json` lines.
- **Chat endpoint:** test proposal-block detection and the SSE relay shape with a fake
  `claude_client`.
- **Create endpoint:** test slug allocation, manifest writing (incl. `brief`), and that the
  new course appears via `GET /api/courses`.
- **JIT generation:** test that a missing lesson triggers generation (fake client), the result
  is validated, written, and served; that a present lesson is served without generating; that
  invalid generation surfaces an error and writes nothing.
- **Hardening:** `home.js` escaping test; route-param rejection tests.
- **Real-Claude checks are gated to the spike + the final end-to-end run**, not the unit suite.

## Plan shape (for the implementation plan)

0. **Spike:** prove the Pi service can run `claude -p` headless under the Max subscription and
   get back both a structured JSON result and a streamed result. **Gate** — if this fails,
   stop and report.
1. `claude_client` boundary (structured + streaming, with the fake-invoker tests).
2. Course-creation chat endpoint + system prompt + proposal-block detection.
3. Chat frontend (SSE rendering + proposal card + create).
4. `POST /api/courses` create endpoint (slug, manifest + brief).
5. JIT lesson generation in the lesson endpoint.
6. Hardening (escaping + route validation).
7. End-to-end verification on the Pi + deploy.

## Out of scope (deferred)

- **Look-ahead pre-generation** of the next lesson (optimization).
- **Editing a course outline** after creation (rename/reorder/remove modules) — create-then-use
  only for now.
- **Regenerating** an existing lesson, or adapting already-written lessons to recent performance.
- **The spaced-repetition (FSRS) engine** — still deferred; `reviewsDue` stays 0.
- **Streaming the structured artifacts** (outline/lesson) — they use a loading state.
- **Multi-user.** Single user (Werner).

## Self-review notes

- **Single boundary to Claude** (`claude_client`) keeps the subscription/CLI detail in one
  place; every other unit is testable with a fake. Matches Slice 1's injected-dependency style.
- **Additive to Slice 1:** `brief` on the manifest and JIT-on-miss in the lesson endpoint
  don't change Slice 1's read contracts; generated lessons reuse the existing lesson schema and
  screen.
- **Risk surfaced first:** the headless-subscription unknown is task 0 with an explicit gate.
- **YAGNI:** look-ahead, outline editing, regeneration, FSRS all deferred until needed.
