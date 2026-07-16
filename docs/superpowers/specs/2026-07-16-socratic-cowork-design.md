# Socratic co-work on the exercise — design

**Date:** 2026-07-16. **Status:** approved (Werner interview 2026-07-16). First slice of the
Claude-in-lessons wave (deep dive item 1, `docs/research/2026-07-15-claude-in-lessons-deep-dive.md`).

## Goal

An optional "Work through it with Claude" mode on the lesson exercise: the learner commits to
a step in chat, Claude responds to *that step* — confirms, asks the one next Socratic
question, or surfaces the misconception — until the learner reaches the solution themselves
and types their final answer through the normal grade-and-reveal flow. Process-level feedback
(Hattie & Timperley); the tutoring interaction Bloom's 2-sigma benchmark points at.

## Decisions (Werner, 2026-07-16)

1. **Formative only.** No new events, no mastery, stats, streak, or transcript impact. The
   final answer the learner types still goes through the normal exercise grading path; that
   path already carries the mastery signal, and a co-worked answer is not independent
   evidence — counting it would double-dip.
2. **Never reveals.** In this mode Claude never states the final answer or full approach, no
   matter how the learner asks. The exercise's existing Reveal-solution button is the honest
   escape hatch, so there is no dead end. (The general side-chat keeps its existing
   give-in-when-asked-twice behavior — this mode is the committed alternative, not a
   replacement.)

## Approach

A **mode flag on the existing lesson side-chat** — not a new route, screen, or store. The
side-chat already streams SSE, already carries the exercise + reference answer + worked
example in its prompt (`generation.lesson_chat_prompt`), already persists its transcript in
the per-lesson workspace, and already has escaping and stale-screen guards. The mode swaps
the system prompt and drops web-search tools; everything else is inherited.

Rejected alternatives: a dedicated route + screen (like the gap-review session) — new
persistence and UI surface with no benefit at this scope (YAGNI); a client-injected hidden
instruction message through the unchanged route — pollutes the persisted transcript and puts
tutoring rules in forgeable message content instead of the server-side prompt.

## Learner experience

1. On the exercise, while the solution is **not** revealed, a button appears:
   **"Work through it with Claude"**.
2. Clicking it opens the workspace panel on the Chat tab, shows a mode banner —
   *"Working through the exercise — Claude will guide with questions, not answers."* with an
   **Exit** control — and appends a canned opener from Claude:
   *"Let's work through this together — I'll ask questions, you do the thinking. What do you
   think the first step is?"* The opener is client-side: instant, zero cost; Claude's value
   starts when it responds to the learner's first committed step.
3. Each learner message now streams through the same chat endpoint with `mode: "socratic"`.
   Claude responds to the latest step only: brief confirm + the one next question, or a
   question/tiny counterexample that exposes the misconception. One question per turn, short
   turns, lesson vocabulary.
4. If the learner asks for the answer or gives up, Claude declines in one sentence, points at
   the Reveal-solution button, and offers a smaller step.
5. When the learner has stated the complete solution in their own words, Claude says so
   plainly and tells them to type their final answer in the exercise answer box — the normal
   grade → reveal → checks → explain flow finishes the lesson, untouched.
6. The mode ends when the learner clicks Exit or reveals the solution (banner disappears,
   chat reverts to the normal side-chat over the same transcript). The mode flag is
   ephemeral UI state: a page reload drops the mode but keeps the transcript; the button
   re-enters it.

## Backend design

All in `backend/generation.py` and `backend/app.py`.

### New system prompt (`generation.py`, next to `LESSON_CHAT_SYSTEM`)

`SOCRATIC_COWORK_SYSTEM` — full text (plan may polish wording, not rules):

> You are working through the lesson's MAIN EXERCISE with a learner who wants to reach the
> solution themselves. You have the reference answer below — NEVER state it, never lay out
> the full approach, and never confirm a bare guess as correct until the learner has
> explained the reasoning behind it. If they ask you directly for the answer or say they
> give up, warmly decline in one sentence, remind them the Reveal solution button is there
> if they want out, then offer a smaller step by breaking the current question into an
> easier one. Otherwise respond to the learner's LATEST step only: if it is right, confirm
> it in a few words and ask the ONE question that moves them a single step forward; if it is
> wrong or rests on a misconception, do not correct it outright — ask a short question or
> give a tiny concrete example that lets them see the problem themselves. One question per
> turn. Keep every turn under 80 words. Mirror the lesson's OWN vocabulary: use the exact
> terms, labels, and step names that appear in the lesson text below. When the learner has
> stated the complete solution in their own words, tell them plainly they have it and to
> type their final answer into the exercise answer box to check it.

### Prompt builder and SSE generator

- `lesson_chat_prompt(lesson, messages, solution_revealed=False, socratic=False)` — when
  `socratic` is true, use `SOCRATIC_COWORK_SYSTEM` instead of `LESSON_CHAT_SYSTEM`; the
  lesson-context block, revealed line, and history rendering are unchanged (single builder,
  no duplication).
- `lesson_chat_sse(lesson, messages, *, stream_fn, solution_revealed=False, socratic=False)`
  threads the flag through. Error handling unchanged (SSE `error` events for
  `ClaudeAuthError` / `ClaudeError`).

### Route (`app.py` `post_lesson_chat`, currently 513-527)

- **Forged-body guard** (same idiom as the assessment-integrity routes):
  `body = request.get_json(silent=True); body = body if isinstance(body, dict) else {}` —
  today a non-dict JSON body (`[1,2]`, `"str"`, `5`) reaches `body.get` and 500s.
- **Messages shape guard**: `messages = body.get("messages", [])`; if not a list, use `[]`;
  drop non-dict entries. Today a forged shape raises inside the SSE generator after the 200
  has started streaming. In scope because this change adds a field to this route's contract.
- **Mode**: `socratic = body.get("mode") == "socratic"` — any other/forged value falls back
  to the normal chat. The flag is client-supplied by design: it only selects between two
  system prompts, and the reference answer is in model context in both modes today, so
  forging it grants nothing.
- **Tools**: socratic mode drops `WebSearch`/`WebFetch` (`stream_fn` without tools). The
  exercise is self-contained with the solution in context; no tools means faster turns. The
  normal mode keeps its tools.

## Frontend design

### `frontend/src/views/lesson.js`

- Exercise card: render the **"Work through it with Claude"** button
  (`data-action="socratic-start"`) only when `!state.solutionRevealed`. Plan pins exact
  placement next to the existing answer controls.
- Workspace chat tab: when `ws.socratic` is truthy, render the mode banner above the thread
  — static text *"Working through the exercise — Claude will guide with questions, not
  answers."* plus an Exit button (`data-action="socratic-exit"`). No banner otherwise;
  non-socratic rendering byte-identical to today.

### `frontend/src/app.js` (not unit-tested, per repo convention)

- `socratic-start` handler: on the current `ui.lessonState`, set `ws.socratic = true`, open
  the workspace on the Chat tab, push the canned opener as an assistant message onto
  `ws.chat` (only on entry, so repeated clicks don't duplicate it), repaint, best-effort
  `saveWorkspace`.
- `sendWsChat`: when the captured lesson-state's `ws.socratic` is truthy, include
  `mode: "socratic"` in the `extra` object alongside the existing `solutionRevealed`. The
  existing capture-then-`onScreen()` guard pattern is untouched; the mode flag is read from
  the captured `ls`, not live `ui` state.
- `socratic-exit` handler: clear `ws.socratic`, repaint.
- Reveal-solution handler: additionally clear `ws.socratic` (mode ends on reveal).
- `ws.socratic` is **not** persisted: the workspace PUT body stays `{notes, chat}`
  (`notes.py` shape unchanged); `seedWorkspace` leaves the flag undefined on load.

## Security

- Chat rendering paths unchanged: `esc()` on full repaints, `.textContent` for live deltas.
  The opener and banner are static app-authored strings.
- No new persistence shape, no new event type, no new read path over forgeable data.
- New route guards above remove an existing pre-stream 500 on forged bodies.
- `mode` forgery is a no-op security-wise (prompt selection only, see Route).

## Error handling

- Mode entry is fully client-side — it cannot fail on Pi/Claude outages.
- A failed socratic send surfaces the existing SSE error bubble; the mode stays active and
  the learner can retry, exit, or reveal.

## Testing

- **Backend** (`.venv/bin/pytest -q`, follow existing chat-route test idiom with a
  monkeypatched `stream_fn` / `claude_client.stream`):
  - `lesson_chat_prompt(..., socratic=True)` contains the Socratic system text and not the
    default one; still contains topic/prompt/reference answer and the revealed line;
    `socratic=False` output unchanged from today.
  - Route passes `socratic=True` only for `mode == "socratic"` (absent, `"chat"`, `5`,
    `true` all fall back).
  - Socratic requests call the Claude client without WebSearch/WebFetch; normal requests
    keep them.
  - Forged bodies (`[1,2]`, `"str"`, `5`, `{"messages": "x"}`, `{"messages": [1, {}]}`)
    return a normal SSE stream without a 500.
- **Frontend** (`node --test frontend/tests/*.test.js`): button renders only when
  unrevealed; banner + Exit render only when `ws.socratic`; non-socratic workspace markup
  unchanged. `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`.

## Deploy notes

No schema, content, or data changes. Standard `docs/DEPLOY.md` procedure (no `--delete`,
verify `/api/health` and all 4 courses in `/api/courses`).

## Out of scope

- The rest of the Claude-in-lessons wave (fresh review items, prior-knowledge activation,
  analogy on tap, teach-it-to-Claude) — each gets its own cycle.
- Turn caps / history compaction for long chats (the existing side-chat has none either;
  the 100KB workspace cap and 540s stream timeout are the current ceilings — watch item).
- Persisting the mode across reloads; grading or logging anything from the co-work
  transcript.
