# Claude University — Checkable Concept-Check Items (Slice 5)

**Date:** 2026-06-24
**Status:** Design — self-approved under the build charter (see [CHARTER.md](../../CHARTER.md))
**Builds on:** Slices 1–4. Closes roadmap done-item 3; advances 4.

## For Werner (plain-language summary)

Today a lesson has one open exercise whose answer you grade yourself. This slice adds a few
**auto-graded concept checks** to every lesson — multiple-choice and fill-in-the-blank questions
with real answers. When you answer, the platform tells you **right or wrong and why**, instead of
leaving it to self-assessment. It's the objective signal that later powers adaptivity (Slice 6),
and it makes lessons feel like real coursework.

## Decisions made (self-approved under charter)

- **Two check types: multiple-choice (one correct) and fill-in-the-blank** (normalized text match).
  YAGNI on others (ordering, multi-select, code-run).
- **Checks live in the lesson JSON**, generated alongside the exercise (1–3 per lesson), and are
  **required** — generation retries if Claude omits them.
- **Checks render after the solution, before the recall rating** — attempt the exercise, see the
  solution, do the quick checks, then rate recall. (Slice 7's player will restructure the screen;
  additive for now.)
- **Each answered check logs a `lesson_check` event** (`{index, type, correct}`) — the durable
  objective signal Slice 6 will consume. Recall rating (Slice 4) stays manual for now.

## Data model

A lesson gains a `checks` array; each item is one of:

```json
{"type": "mcq",  "prompt": "<html>", "choices": ["<html>", "..."], "answer": 1, "explanation": "<html>"}
{"type": "fill", "prompt": "<html>", "answer": "4", "explanation": "<html>"}
```

`answer` is the correct choice **index** for `mcq`, or the expected **string** for `fill`.
1–3 checks per lesson. HTML fields are sanitized with the existing default-deny allowlist.

## Architecture

1. **Backend generation (`backend/generation.py`).**
   - `lesson_prompt` gains an instruction to also produce a `checks` array (2–3 items, `mcq`/`fill`,
     each with `answer` + a one-sentence `explanation`).
   - `valid_check(item)` validates one item (type `mcq`|`fill`; `mcq` needs a `choices` list and an
     integer `answer` in range; `fill` needs a string `answer`; both need `prompt` + `explanation`).
   - `valid_lesson` additionally requires `checks` to be a list of 1–3 valid items.
   - `ensure_lesson` sanitizes each check's `prompt`, `explanation`, and `mcq` `choices` (via the
     existing `sanitize_html`) before validating/writing.
   - No new endpoint — checks ride inside the existing lesson JSON the lesson endpoint already serves.

2. **Frontend grading + view (`frontend/src/views/checks.js`).**
   - `gradeCheck(check, answer) -> { correct, explanation }` — pure: `mcq` compares the selected
     index to `answer`; `fill` compares `normalize(answer)` to `normalize(check.answer)` where
     `normalize = (s) => String(s).trim().toLowerCase()`.
   - `checksHTML(checks, state) -> string` — renders a "Check your understanding" section; each
     check shows its prompt and either choice buttons (`mcq`) or a text input + Check button
     (`fill`); once answered (`state.results[i]` present) it shows a correct/incorrect marker and
     the explanation. Escapes/uses the sanitized HTML the backend produced.

3. **Lesson wiring (`frontend/src/app.js`).** After the solution is revealed, render the checks
   section. Answering a check grades it (`gradeCheck`), records the result in `ui.lessonState`,
   logs `lesson_check {course_id, topic_id, payload:{index, type, correct}}`, and re-paints to
   show feedback. The recall rating remains as in Slice 4.

## Data flow

```
generate lesson  ──▶ lesson JSON includes checks[]  (validated + sanitized in ensure_lesson)
answer a check   ──▶ gradeCheck -> feedback shown   ──▶ POST /api/events lesson_check{index,type,correct}
```

## Frontend state

`ui.lessonState` gains `checkAnswers` (per-index entered value) and `checkResults` (per-index
`{correct}`), reset when a lesson loads. The lesson screen re-paints on each check answer to show
its marker + explanation; other checks remain independently answerable.

## Testing

- **Backend (pure):** `valid_check` accepts good `mcq`/`fill`, rejects malformed (bad type, out-of-range
  index, missing answer/explanation); `valid_lesson` requires 1–3 valid checks; `ensure_lesson`
  sanitizes check HTML and reconciles ids (extend the existing generation tests with a fake
  `generate` returning checks, incl. an unsafe HTML check that comes back escaped); `lesson_prompt`
  mentions checks.
- **Frontend (pure):** `gradeCheck` for `mcq` (right/wrong index) and `fill` (case/space-insensitive
  match, mismatch); `checksHTML` renders choice buttons for `mcq`, an input for `fill`, and the
  explanation + marker once a result is present.
- **Real-browser + Pi:** generate a real lesson, confirm it has checks, answer one right and one
  wrong, see correct/incorrect + explanation, and confirm a `lesson_check` event lands.

## Out of scope (deferred)

- Using check results to drive mastery/adaptivity or auto-suggest the recall rating (Slice 6).
- The two-panel lesson player / curriculum sidebar (Slice 7) — checks are added to the current
  single-column lesson for now.
- Additional check types (ordering, multi-select, code execution), per-choice feedback beyond the
  single explanation, retry limits — YAGNI.

## Self-review notes

- **Additive, no new endpoint:** checks ride in the existing lesson JSON; backend change is
  generation + validation + sanitize only.
- **Pure, testable units:** `valid_check`/`gradeCheck`/`checksHTML` are pure; app.js wiring is the
  only browser-verified part, matching the existing pattern.
- **Safety preserved:** check HTML goes through the same default-deny sanitizer as the rest of the
  lesson.
- **Feeds the next slice:** `lesson_check` events are the objective signal Slice 6 (adaptivity)
  will consume — designed now, used later.
- **YAGNI:** two check types, one explanation each, no retries/limits.
