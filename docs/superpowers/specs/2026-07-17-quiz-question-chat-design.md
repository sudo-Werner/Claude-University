# Quiz question chat — ask about a question after answering — design

**Date:** 2026-07-17. **Status:** approved (Werner feedback id 2, triaged 21:25: "add a
chat box during quizzes incase questions arise"; shape agreed 21:26 "please do both" —
chat opens AFTER answering, so retrieval practice is never spoiled).

## Goal

During an Arcade round, once a question is answered (reveal phase) — or a match-up board
is completed — an "Ask about this question" affordance opens an inline chat grounded in
that question and its source lesson. The learner asks "why?", Claude explains, streamed.

## Decisions

1. **Post-answer only.** The affordance renders ONLY in the reveal/feedback phase (and
   after a completed match-up board). Nothing chat-related exists while a question is
   open; the rapid-fire countdown is already stopped by then. Advancing to the next
   question or leaving the screen discards the thread.
2. **Ephemeral, stateless, unlogged.** The thread lives on `ui.quizPlay` only — cleared
   by advance/`resetArcadePlay`. No persistence (workspace files untouched), no events,
   no stats. Zero DB surface.
3. **New thin streaming route** `POST /api/courses/<course_id>/quiz/question-chat`
   (mirrors the lesson chat route shape): body
   `{lesson_id, question, answerGiven, messages}` where `question` is the client's view
   of the answered question (format, prompt/statement/items/pairs, choices, the correct
   answer, reveal — all already known client-side post-answer, so nothing is leaked).
   Server-side: `_ID_RE` on course_id; `lesson_id` must exist in the course manifest
   (404 otherwise); `messages` list capped (<= 20 turns, each <= 4000 chars, role in
   {user, assistant}); non-dict/malformed bodies -> 400.
4. **Prompt** (`quiz_question_chat_prompt` in `backend/quiz.py`): a QUIZ_CHAT_SYSTEM
   block (explain clearly, ground answers in the lesson's teaching, plain text only, do
   not invent facts beyond the lesson + established knowledge) + the cached lesson's
   content as grounding (via `load_lesson`; if the lesson file is missing, proceed
   without it — fail-open) + the question object and learner's answer as `json.dumps`
   data with treat-as-data framing + the chat messages `json.dumps`'d per turn (learner
   text NEVER raw-interpolated — house rule). Streamed via `claude_client.stream` with
   NO web tools. Each message is one paid chat-class call (accepted by Werner).
5. **Frontend:** in the reveal block, "Ask about this question" button -> inline chat
   area (input + esc()'d bubbles) inside the arcade play screen, streamed with the
   existing SSE-parsing helpers (`parseSSELines` / streamChat-style reader with an
   endpoint override), stale-screen guards per house pattern (a late chunk after
   advance/exit paints nothing). Thread state: `ui.quizPlay.qchat = {open, messages,
   streaming}`; `resetArcadePlay` and question-advance clear it.
6. **Copy:** button "Ask about this question"; placeholder "Ask why the answer is what
   it is..."; no emojis.

## Error handling

- Stream failure / non-200 -> inline plain-text error line in the chat area + input
  re-enabled; round flow never blocked.
- Malformed request -> 400 JSON error shape (sibling-route style); unknown lesson -> 404.
- Late SSE chunks after advance/exit -> dropped by the stale guard.

## Security

- Learner text and the client-supplied question object enter the prompt only
  `json.dumps`'d with treat-as-data framing (same trust boundary as lesson chat, which
  already accepts arbitrary learner messages). The correct answer is included only
  because the client already holds it post-reveal — nothing new is disclosed.
- All rendered chat content goes through `esc()`; plain text only, no HTML parsing.
- No web tools on the stream; route adds no filesystem or DB writes.

## Testing

- Backend: route validation (bad course id 404, unknown lesson 404, non-dict body 400,
  oversize/overlong messages 400); prompt content (system block present, lesson
  grounding included when cached and skipped when missing, learner text json-encoded —
  a hostile string round-trips as data); no-web-tools assertion; SSE plumbing via the
  existing chat-route test idiom (monkeypatched spawn).
- Frontend: reveal block renders the button post-answer only (absent while open);
  qchat state cleared on advance and reset; esc() XSS case on a bubble; import check.

## Out of scope

- Persisting threads; logging events; mastery/stats signals; chat during an open
  question; workspace integration; round-summary chat.
