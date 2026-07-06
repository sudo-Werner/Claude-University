# Lesson Workspace (per-lesson Notes + side-Chat) — Design Spec

**Goal:** while studying a lesson, the learner can jot **notes** and hold a lesson-aware
**side-chat with Claude** about tangential thoughts; both persist per-lesson to the Pi and
appear on any device.

**Status:** brainstormed + approved 2026-07-06. Awaiting spec review, then writing-plans.

## Decisions (from brainstorming)
- **Per-lesson**, not per-course. **Saved to the Pi** (durable + cross-device), auto-save.
- Surface: a **collapsible "Notes/Workspace" panel below the lesson**, within the existing
  ~448px phone-first column (no new desktop two-column layout). Two **tabs: Notes | Chat**.
- **Notes:** plain text (line breaks preserved), no rich text.
- **Chat:** a real conversation WITH Claude, lesson as context, **no web search** (fast/cheap),
  transcript saved with the notes.
- One store per lesson holds both notes and chat.
- localStorage cache as an offline safety net; last-write-wins across devices (single user).

## Data model
One JSON file per lesson: `content/courses/<courseId>/notes/<lessonId>.json`
```json
{ "notes": "<plain text>", "chat": [ {"role":"user|assistant","content":"..."} ], "updatedAt": "<iso>" }
```
- Missing file → `{"notes":"", "chat":[], "updatedAt":null}`.
- **Size cap:** reject a PUT whose serialized `notes`+`chat` exceeds ~100 KB (guardrail against
  unbounded growth) with 413.
- `courseId`/`lessonId` validated by `_ID_RE` (prevents path traversal in the filename), same as
  every other content route.

## Backend

### `backend/notes.py` (new, small)
- `load_workspace(content_dir, course_id, lesson_id) -> dict` — reads the JSON file or returns the
  empty default. Tolerates a corrupt file (returns default).
- `save_workspace(content_dir, course_id, lesson_id, notes, chat) -> dict` — validates types
  (`notes` str, `chat` a list of `{role in {user,assistant}, content str}`), enforces the size cap
  (raises `ValueError` on oversize / bad shape), writes `{notes, chat, updatedAt}` with a fresh
  timestamp, returns the stored dict. Creates the `notes/` dir as needed.
- Notes/chat text is user data shown in a `<textarea>` value and (for chat) rendered — see XSS note.

### Routes (`backend/app.py`)
- `GET /api/courses/<cid>/lessons/<lid>/workspace` → `load_workspace(...)` as JSON. 404 on bad id.
- `PUT /api/courses/<cid>/lessons/<lid>/workspace` body `{notes, chat}` → `save_workspace(...)`. 400 on
  bad shape, 413 on oversize, 404 on bad id. Returns `{updatedAt}`.
- `POST /api/courses/<cid>/lessons/<lid>/chat` body `{messages:[{role,content}]}` → SSE stream of
  the lesson-aware reply. Loads the lesson from disk for context (404 if missing); streams via the
  existing `claude_client.stream` (NO web search). Mirrors `post_course_chat`'s SSE response.

### Generation (`backend/generation.py`)
- `lesson_chat_prompt(lesson, messages) -> str` — a "study companion for THIS lesson" system prompt
  + the lesson's `topic`/`promptHtml`/`solutionAns`/`solutionNote` as context + the conversation.
  Encourages concise, focused answers; it may go on tangents the learner raises but stays a tutor.
- `lesson_chat_sse(lesson, messages, *, stream_fn) -> generator` — like `chat_sse` but streams only
  `delta`/`done`/`error` (no `proposal` detection). Reuses `_sse` and the `ClaudeAuthError`/`ClaudeError`
  handling pattern.

## Frontend

### `frontend/src/notes.js` (new)
- `loadWorkspace({fetch, courseId, lessonId}) -> {notes, chat, updatedAt}` (GET; on failure returns
  the localStorage-cached copy or the empty default).
- `saveWorkspace({fetch, courseId, lessonId, notes, chat}) -> {ok, updatedAt|error}` (PUT; always
  writes the localStorage cache first so a failed/offline save doesn't lose data).
- localStorage key: `ws:<courseId>:<lessonId>`.

### `frontend/src/chat.js`
- Generalize `streamChat` to take an optional `endpoint` (default `/api/courses/chat`) and tolerate
  a missing `onProposal` (the lesson chat emits no proposal). Backwards compatible.

### `frontend/src/views/lesson.js`
- A `workspaceHTML(state)` panel appended after the lesson: a collapsible header (`▸/▾ Notes`),
  a tab row (Notes | Chat), the Notes `<textarea>` with a `saved/saving…/offline` indicator, and the
  Chat thread + input. Rendered from `state.ws` (`{open, tab, notes, chat, pending, saveStatus}`).
- **XSS:** notes render only as a `<textarea>` **value** (inert). Chat messages render as text via
  `esc()` (they are plain conversational text, not sanitized HTML) — never innerHTML raw.

### `frontend/src/app.js`
- On `openLesson`/review open: `loadWorkspace(...)` → seed `ui.lessonState.ws`.
- Notes edit → update `ws.notes` + localStorage immediately; **debounced ~1s** `saveWorkspace`.
- Chat send → append user msg, stream the reply via `streamChat({endpoint: .../chat})`, append the
  assistant msg on done, then `saveWorkspace` (persist the transcript). Errors show inline.
- Panel open/closed + active tab persisted (localStorage) so they stick.
- Navigation guard: like grade/deepen, discard a late chat/save result if the learner left the lesson
  (compare `ui.lessonState` identity).

### `frontend/styles.css`
- The workspace panel, tab row, notes textarea + save indicator, chat thread/bubbles/input. Reuse
  existing chat styles where possible.

## Testing
- **backend:** `notes.load_workspace`/`save_workspace` (default, round-trip, bad shape, size cap,
  corrupt file); routes GET/PUT (200/400/413/404, id validation); `lesson_chat_prompt` (includes
  lesson context); `lesson_chat_sse` (delta→done, auth-error path). 
- **frontend:** `loadWorkspace`/`saveWorkspace` (fetch shapes, localStorage cache fallback);
  `streamChat` endpoint override + no-proposal tolerance; `workspaceHTML` (tabs, notes value, chat
  rendering escaped, save indicator).

## Non-goals (YAGNI)
Rich-text notes, tags/search, export, a course-wide notebook, sharing, web-search in the side-chat,
editing/deleting individual past chat turns. Add later only if missed.

## Build order (for writing-plans)
1. Backend notes store + GET/PUT routes (+ tests).
2. Backend lesson-chat prompt + sse + route (+ tests).
3. Frontend notes.js + streamChat generalization (+ tests).
4. Frontend workspace panel in lesson.js + app.js wiring + CSS (+ tests).
5. Review → deploy → Pi-verify (throwaway course: notes persist across reload; side-chat answers
   with lesson context and the transcript reloads).
