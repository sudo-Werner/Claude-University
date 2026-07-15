# Pedagogy Borrows: Guided-First Exercise Help + Metacognitive Follow-Up — Design

**Date:** 2026-07-15. **Decided with Werner:** adopt ideas 1+2 from the Claude for Teachers / Learning Mode research now; mid-lesson production checkpoints deferred to sub-project D.

## Scope correction (recorded honestly)

Idea 1 was pitched as an "escape hatch" for Socratic chat. Reading the code, the lesson side-chat is ALREADY direct-answer by default (`LESSON_CHAT_SYSTEM`: answers concisely, guards the solution only "unless they ask for it"). The genuinely borrowable Learning Mode behavior is the inverse: **guide first on the assessed exercise**, answer everything else directly, and keep the explicit direct-answer path friction-free.

## 1. Guided-first exercise help (lesson side-chat)

- The chat POST body gains optional `solutionRevealed` (bool, default false). `app.py` passes it through; `lesson_chat_prompt(lesson, messages, solution_revealed=False)` adds one context line: "The learner has NOT yet revealed the solution." / "The learner has already revealed the solution."
- `LESSON_CHAT_SYSTEM` gains: when the learner asks for help with the lesson's MAIN EXERCISE and the solution is not yet revealed, respond first with ONE short guiding question or targeted hint that moves them one step, instead of the full approach — but if they explicitly ask for the direct answer, say they are stuck, or ask again, give it plainly and without gatekeeping or lecturing. All other questions (concepts, tangents) keep today's direct concise answers. After the solution is revealed, discuss it directly.
- Frontend: `streamChat` call for the workspace chat includes `solutionRevealed: !!ui.lessonState.solutionRevealed` in the request body.

## 2. Metacognitive follow-up after explain-it-back

- `explain_prompt` also asks for `followUp`: ONE short reflective question addressed to the learner that targets the weakest point of their explanation (for a fully correct explanation: a transfer/connection question instead). New validator `valid_explain` requires `{verdict, note, followUp}` (verdict in the existing grade verdicts; note and followUp non-empty strings). The `/explain` route switches from `valid_grade` to `valid_explain`; `explain_answer` sanitizes `followUp` like `note`. `/grade` is untouched.
- Frontend: the explain result card renders the follow-up question under the note, with a button "Explore in side-chat". Clicking it opens the workspace panel on the chat tab (`ws.open = true`, `ws.tab = "chat"`), appends the follow-up as an assistant message to `ws.chat` (so the learner answers it in a real dialogue with the tutor, which now has the guided-first behavior), saves the workspace, and repaints. Seeding is idempotent per grading: the button disables after one click (state flag on `lessonState.explain`).
- `followUp` is server-sanitized (rendered raw client-side, matching `note`). The seeded chat message is learner-visible text already sanitized server-side; `chat` rendering already escapes/renders messages the same way as other assistant messages.

## Not in scope

No new endpoints. No event types. No changes to grade, pre-quiz, reviews, or lesson generation. Intake chat untouched.

## Testing

Backend: `valid_explain` accept/reject; `explain_prompt` mentions followUp; `explain_answer` returns sanitized followUp; route returns it (extend existing explain route tests); `lesson_chat_prompt` includes the revealed/not-revealed line both ways; `LESSON_CHAT_SYSTEM` contains the guided-first and escape-hatch phrases. Frontend: explain card renders followUp + button; button handler seeds ws.chat exactly once, opens chat tab, disables; solutionRevealed included in chat request body. Plus the app.js import-resolution check.
