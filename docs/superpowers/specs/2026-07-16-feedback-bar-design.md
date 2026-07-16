# Feedback bar — in-app feedback channel — design

**Date:** 2026-07-16. **Status:** approved (Werner-requested 2026-07-16 22:12: "a feedback bar
where I can quickly type in some feedback for improvements"). Small slice, built same evening.

## Goal

From any screen, Werner taps a Feedback affordance in the topbar, types a quick note, sends it,
and gets an instant "Thanks — noted." The note lands in a `feedback` table in the Pi's
learning.db with the screen/course/lesson context attached automatically. The autonomous build
loop reads unprocessed rows each cycle (via SSH + sqlite3) and triages them into build work —
feedback becomes a durable input channel to the charter loop instead of chat-only relay.

**Cost shape:** zero Claude calls. One tiny synchronous POST per note.

## Decisions (routine, self-approved; direction Werner-given)

1. **Dedicated table + route, not the events pipeline.** Feedback must be delivered
   synchronously (instant confirmation, no 15s flush, no poison-pill batch coupling) and be
   trivially queryable by the loop. New `feedback` table in `backend/schema.sql`
   (`CREATE TABLE IF NOT EXISTS` — the established idempotent-migration idiom; no ALTERs
   needed): `id INTEGER PK AUTOINCREMENT, created_at TEXT NOT NULL, screen TEXT,
   course_id TEXT, lesson_id TEXT, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new'`.
   `status` is the loop's triage marker (`new` → `seen`); the app itself only ever inserts
   with the default.
2. **Route: `POST /api/feedback`**, body `{"text": str, "screen"?: str, "courseId"?: str,
   "lessonId"?: str}`. Behavior: coerce body with the established `isinstance` idioms;
   `text` must be a non-empty string after `.strip()` else 400 `{"error": "feedback text is
   required"}`; truncate stored text at 4000 chars (generous; protects the DB from an
   accidental paste bomb); context fields stored only if they are strings matching `_ID_RE`
   for ids / a short (<=40 chars) string for screen, else NULL (client-forgeable — defensive
   reads, never a 500); server stamps `created_at` (UTC ISO, matching events.received_at
   idiom). 200 `{"ok": true}`. No GET route — the loop reads via SSH
   (`sqlite3 ~/claude_university/backend/data/learning.db "SELECT ... WHERE status='new'"`);
   YAGNI on an API reader until something in-app needs one.
3. **New module `backend/feedback.py`** (single responsibility, mirrors notes.py's size):
   `insert_feedback(conn, *, text, screen=None, course_id=None, lesson_id=None)` doing the
   validation/truncation above and returning nothing. The route stays thin in app.py.
4. **UI: a topbar button + collapsible one-line composer.** `shellHTML` (frontend/src/views/
   shell.js) gains a small right-aligned **"Feedback"** button in the existing `.topbar`
   (`data-action="feedback-toggle"`). Tapping it toggles a compact `.feedback-bar` row
   rendered directly under the topbar: a single-line `<input>` (placeholder exactly
   `Ideas, annoyances, requests — straight to the build loop.`), a **Send** button
   (`data-action="feedback-send"`), disabled while the input is empty or a send is in flight.
   Enter in the input sends. On success: the bar swaps to `Thanks — noted.` for ~2.5s, then
   collapses and clears. On failure: inline `Couldn't send — try again.` stays visible, text
   preserved (never lose the note). The composer state lives in a module-level ui field
   (`ui.feedback = {open, sending, text}` or equivalent — the plan owns the exact shape);
   the input's value must update state WITHOUT triggering a repaint (the established
   focus-steal rule).
5. **Context captured automatically, silently:** the send handler snapshots
   `ui.screen`, `ui.courseId`, and `ui.lesson?.id` (whatever names app.js actually uses — the
   plan verifies) at send time. No user-visible context UI.
6. **Fetch helper** `sendFeedback(payload)` in frontend/src/courses.js following the
   established non-throwing idiom (non-ok / network failure → `{error}` object).
7. **Loop integration is procedural, not code:** the hourly self-audit gains a step — query
   `status='new'` rows on the Pi, triage each into (build now / ticket / ask Werner), then
   `UPDATE feedback SET status='seen' WHERE id IN (...)`. Recorded in the progress ledger;
   no cron or backend reader ships in this slice.

## Error handling

- Malformed body / non-string fields → 400 only for missing text; bad context fields are
  dropped to NULL, the note still lands (the note is the payload — never reject it over
  metadata).
- DB write failure → 500 is acceptable here (single-user app, no learner-work-loss surface,
  the client keeps the text and shows the retry message). No silent success.
- The bar renders on every screen via the shell; it must never block or break screen paints —
  a missing `ui.feedback` state renders the collapsed default.

## Security

- Feedback text is stored raw in SQLite and only ever read by the loop over SSH; it is never
  rendered back into the app's DOM and never enters a Claude prompt in this slice. (If a
  future slice renders it, esc()/json.dumps at that boundary — noted here so the constraint
  travels.)
- Input rendered with value esc()'d on repaint; no innerHTML surface added.
- Context ids validated against `_ID_RE` server-side.

## Testing

- **Backend** (`.venv/bin/pytest -q`): insert_feedback validation (strip, empty reject,
  4000-char truncation, bad context → NULL, `_ID_RE` enforcement); route happy path writes a
  row with server-stamped created_at + status='new'; 400 on missing/blank text; adversarial
  bodies (non-dict, arrays, numeric fields) never 500; schema idempotency (init_db twice).
- **Frontend** (`node --test frontend/tests/*.test.js`): shell renders the Feedback button;
  composer row renders open/closed from state; Send disabled when empty/sending; XSS case
  (typed text containing `<script>` re-rendered esc()'d); success and failure states render
  the exact copy strings. Plus the app.js import-resolution check.

## Deploy notes

Standard docs/DEPLOY.md. `schema.sql` change applies itself at service start (init_db runs in
create_app). **Werner is actively using the app tonight** — before restart, run the pgrep
check and restart only when no generation is in flight; warn him of the ~3s blip.

## Out of scope

- Reading/dashboarding feedback in-app; GET routes; auth; feedback on feedback.
- Any Claude-powered triage of the notes (the loop's judgment does that).
