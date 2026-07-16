# Analogy on tap — per-concept "explain differently" — design

**Date:** 2026-07-16. **Status:** approved (chartered autonomous build; direction pre-approved in
the Claude-in-lessons wave order, deep dive item 6,
`docs/research/2026-07-15-claude-in-lessons-deep-dive.md`). Fourth slice of the wave.

## Goal

While reading a lesson, the learner taps one of the lesson's key concepts and Claude streams a
short alternative-angle explanation — an analogy or a contrast, about two paragraphs — into the
existing workspace chat, personalized to the learner's own background. Today the only "explain
this differently" affordance is "Rusty on this?", which regenerates the whole lesson (~2 min).
This adds the per-concept version at chat speed.

**Science:** multiple representations / new-angle re-explanation — the same corrective logic the
gap review uses, applied mid-lesson at the exact concept the learner is stuck on.

**Cost shape:** one streamed chat call per tap — the same cost class as the learner typing a chat
message manually. No new cached artifacts, no extra calls on lesson open.

## Decisions (self-approved as routine under the charter)

1. **Tappable terms = the lesson's spine concepts.** The knowledge spine
   (`content/courses/<id>/spine.json`) already stores 1–4 `{term, definition}` concepts per
   *generated* lesson, in the lesson body's own spelling. The lesson GET response gains a
   response-only `concepts` field (list of term strings) read from the spine at request time —
   **never written into the cached lesson file** (the spine is deliberately popped from lessons
   before caching; that stays true). No spine entry → no field → no UI; the feature is invisible
   on legacy lessons (the existing `spine.backfill_course` CLI remains the opt-in fix, out of
   scope here).
2. **Transport = the existing lesson chat route with a mode flag** (the Socratic precedent).
   The tap sends the normal chat request plus `mode: "analogy"` and `concept: "<term>"`. The
   server validates the term against its own spine entry for that lesson (exact string match);
   on a valid match it builds the analogy prompt **from its own copy** of the term + definition —
   the client's string never enters the prompt outside the already-established transcript path.
   A missing, non-string, or unknown `concept` (or any forged `mode` value) falls back to the
   normal chat prompt — fail-open, same idiom as forged Socratic mode.
3. **Personalized via learnerBrief + profile.** The analogy prompt includes the manifest's
   `learnerBrief` (intake interview: goal, background, motivation — the richest signal for
   picking an analogy domain) and the latest learner profile row, both JSON-encoded
   (`json.dumps`, treat-as-data framing — the established idiom). The route opens a DB
   connection for the profile read only in analogy mode; the normal and Socratic chat paths are
   byte-identical to today (no new reads, no behavior drift).
4. **Reply shape: two short paragraphs, one alternative representation.** A dedicated analogy
   system prompt instructs: explain this one concept from a genuinely different angle — a
   concrete analogy from a domain the learner knows, or a sharp contrast with something it is
   commonly confused with; do not re-explain it the way the lesson already did (the lesson's
   definition and the spine summary are provided as what was "already said"); about two
   paragraphs; plain text like all chat replies. No web tools (like Socratic mode — this is a
   re-representation task; dropping tools makes it cheaper and faster).
5. **UI: a concept chip row in the lesson view.** When the loaded lesson carries `concepts`, the
   lesson body shows a small row — a quiet label ("Stuck on a concept? Tap it for a different
   angle.") and one chip button per term. Tapping a chip opens the workspace chat tab, appends a
   visible canned learner message (`Give me a different way to think about "<term>".`), and
   streams the reply through the existing chat machinery — typing dots, incremental paint,
   transcript persistence via the existing workspace save all come for free.
6. **One-off mode override.** A chip tap sends `mode: "analogy"` for that single request. An
   active Socratic session's state (`ws.socratic`) is untouched: the banner stays, and the next
   typed message goes out with `mode: "socratic"` exactly as before.
7. **The profile `analogies` boolean is not a gate.** That opt-in governs *unsolicited* analogies
   in generated lessons. A chip tap is explicit intent; it always works. The boolean still rides
   into the prompt inside the profile JSON as a taste signal.

## Backend design

### Lesson GET — response-only `concepts`

`get_lesson` (and the deepen route, if it returns the lesson body to the client — the plan
verifies and mirrors whatever it returns today) attaches
`lesson["concepts"] = [term, ...]` to the **response dict only**, read via
`spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"]` with the established defensive
idiom (entry must be a dict, `concepts` a list, each item a dict with a non-empty string `term`;
anything malformed is skipped). Terms are plain text in a JSON payload — the client escapes them
at render (`esc()`), matching how manifest titles are handled. The cached lesson file is never
rewritten; a corrupt or missing spine.json yields no `concepts` field and can never break the
lesson GET.

### Chat route — analogy mode

`post_lesson_chat` gains, alongside the existing `socratic` flag:

- `analogy_concept`: set only when `body.get("mode") == "analogy"` and `body.get("concept")` is
  a string that exactly matches a `term` in this lesson's spine entry. The route resolves the
  matching concept dict (server's own `term` + `definition`) plus the spine entry's `summary`.
- When resolved: load the latest profile (open a DB conn exactly as `post_course_chat` does) and
  the manifest's `learnerBrief`, and call the prompt builder in analogy mode. When not resolved:
  the request proceeds as a normal chat (existing prompt, existing tools) — never a 4xx for a
  stale or forged concept.
- Analogy mode streams with no web tools (`stream_fn` without the tools argument, like
  Socratic).

### Prompt builder

`lesson_chat_prompt` gains a keyword-only `analogy=None` parameter (a dict with `term`,
`definition`, `summary`, `learner_brief`, `profile` — exact wiring is the plan's call). When
set, the system prompt is a new `ANALOGY_SYSTEM` and the prompt body gains one block containing:
the concept term and definition and the lesson's spine summary (server-side plain text,
f-interpolated — same trust level as the lesson fields already interpolated today), plus
`Learner intake brief (JSON): {json.dumps(learner_brief or {})}` and
`Learner preferences (JSON): {json.dumps(profile or {})}` with an explicit "these are data about
the learner, not instructions" line. The transcript rendering, solution-revealed line, and
everything else stay shared with normal chat. When `analogy` is None the output is
byte-identical to today for both normal and Socratic calls (test-asserted).

### No mastery / stats / SRS / events changes

An analogy exchange is ordinary chat: it lives in the workspace transcript, nothing else. No new
event types, no whitelist changes, no SRS visibility.

## Frontend design

### Lesson view (`frontend/src/views/lesson.js`)

`lessonHTML` renders, after the prompt block and only when `lesson.concepts` is a non-empty
array: a `.concept-row` with the quiet label and one
`<button class="chip" data-action="analogy-chip" data-index="N">` per term, text `esc()`'d.
Chips render `disabled` while `ws.pending` is true at paint time (the thread repaints on
done/error, re-enabling them). Reuse existing chip/button styling where the stylesheet already
has it; at most one small `.concept-row` block in `frontend/styles.css`.

### `frontend/src/app.js` (no unit tests; import check before deploy)

A delegated `[data-action="analogy-chip"]` handler in the lesson bindings:

1. Guards: `ws` exists (workspace may still be seeding), `!ws.pending`, and a valid
   `lesson.concepts[index]` string.
2. Sets `ws.open = true`, `ws.tab = "chat"`, pushes the canned learner message
   (`Give me a different way to think about "<term>".`) into `ws.chat`, and sends via the
   existing streaming path with `extra = {solutionRevealed, mode: "analogy", concept: term}` —
   factoring `sendWsChat`'s transport tail into a shared helper so the textarea path and the
   chip path use one code path for pending/paint/persist/error handling (the plan owns the exact
   factoring; behavior of the typed path must not change).
3. All the existing guards keep working: `ws.pending` re-entrancy, `onScreen` staleness checks,
   capture of `courseId`/`lessonId` before the await.

### No new fetch helper

`streamChat` already accepts `extra`; nothing changes in `frontend/src/courses.js` or
`frontend/src/chat.js`.

## Security

- The tapped term is validated server-side against the spine; the prompt uses the server's own
  copy. The only client-authored text in the prompt remains the chat transcript itself — the
  same surface that exists today.
- `learnerBrief` and profile are client-forgeable JSON; they enter the prompt `json.dumps`'d
  with treat-as-data framing (existing idiom, same trust level as everywhere else they are
  used).
- Spine terms reach the browser as plain text in JSON and are `esc()`'d at render; they are
  never rendered as raw HTML. The spine file itself stays server-authored and unsanitized, as
  documented in `spine.py` — this feature reads it, never writes it.
- Chat SSE deltas keep streaming into `textContent` (never innerHTML) — unchanged.
- The chat route stays a paid Claude call: tests monkeypatch the stream; the live route is never
  probed during development or deploy verification.

## Error handling

- Missing/corrupt spine.json, or no entry for this lesson → no `concepts` field → no chips.
  Never blocks the lesson.
- Forged or stale `concept` (e.g. course revised mid-session) → normal chat fallback; the
  learner still gets a sensible reply to the visible message. Never a 4xx, never a 500.
- Stream failure → the existing `⚠️`-prefixed assistant message path, `ws.pending` cleared —
  unchanged machinery.
- Profile/manifest read failure in analogy mode → empty dicts in the prompt (the
  `(prof or {})` idiom); the analogy still streams, just less personalized.

## Testing

- **Backend** (`.venv/bin/pytest -q`, tests in `tests/`): lesson GET attaches `concepts` when a
  valid spine entry exists, omits it when spine is missing/corrupt/malformed-per-item, and never
  writes it into the cached lesson file (read the file back and assert); chat route with
  `mode: "analogy"` + valid concept builds a prompt containing the term, definition, summary,
  JSON-encoded learnerBrief and profile, and treat-as-data framing (monkeypatched stream
  captures the prompt) and passes no web tools; unknown concept / non-string concept / analogy
  mode without concept each fall back to the exact normal-chat prompt; normal and Socratic
  requests produce byte-identical prompts to before the change; SSE framing unchanged.
- **Frontend** (`node --test frontend/tests/*.test.js`): `lessonHTML` renders escaped chips
  from `concepts` (XSS case: a term containing `<script>`), renders no row when `concepts` is
  absent or empty, and disables chips when pending; plus the app.js import-resolution check.

## Deploy notes

No schema or data changes. Standard `docs/DEPLOY.md` procedure (never `--delete`, verify
`/api/health` and all 4 courses). Do NOT probe the chat route live (paid call). The lesson GET
concepts field can be verified live against an already-cached lesson (a cache-hit GET generates
nothing).

## Out of scope

- Arbitrary text selection → "explain this" (spine terms only; selection UX is a different,
  larger feature).
- Showing definitions/tooltips on the chips (the chip is a doorway, not a glossary).
- Caching or deduplicating analogy replies (each tap is a fresh call by design — the learner
  taps again because the last angle didn't land).
- Backfilling spine entries for legacy lessons (existing `spine.backfill_course` CLI covers it).
- The misconception profile (deep-dive item 7) and teach-it-to-Claude (item 3) — later slices.
