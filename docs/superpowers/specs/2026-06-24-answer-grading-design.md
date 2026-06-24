# Answer Grading Design (Post-Roadmap Feature: #4) — AS BUILT

## Vision
The learner types an answer to the exercise prompt, then clicks **Check my answer**
to have Claude grade it (correct / close / incorrect + a short encouraging note).
This is decoupled from "Reveal solution": you can check your attempt, revise, and
re-check *before* giving up and seeing the model's answer — preserving the
attempt-first principle. It fixes review item #4 ("is anything actually grading my
input?").

## Scope & decisions
- **One extra Claude call per check** (model grading, not a heuristic). `claude-sonnet-4-6`,
  ~1-2s on the Pi. Werner accepted this cost when choosing Option B.
- **Decoupled from reveal.** A dedicated "Check my answer" button (becomes "Check again"
  after a verdict). Reveal stays exactly as before.
- **Transient — not logged.** Grading is UX feedback; only the recall self-rating
  (Again/Hard/Good/Easy → `lesson_reviewed`) is an event. (Deviation from the original
  draft's "/api/grade": none on this point.)
- **Available in review sessions too** (minor deviation from the original draft, which
  excluded them). The lesson screen is shared and grading is opt-in per click, so the
  cost stays bounded; no review-mode flag was worth threading.
- **Verdicts:** `correct` / `close` / `incorrect` (the note is always non-empty).

## The flow
1. Lesson open, exercise visible. Answer box + **Check my answer** (disabled until non-empty).
2. Type an answer → button enables.
3. Click → loading state ("Checking your answer…") → verdict banner (verdict + note),
   coloured green/amber/pink. Solution stays hidden. Button becomes **Check again**.
4. Revise + re-check freely, or **Reveal solution**, then rate recall as before.
5. On a grading failure (auth/timeout/network): a soft "Couldn't check your answer right
   now." line; the lesson flow is unaffected.

## Backend (in existing modules — no new file)
`backend/generation.py`:
- `valid_grade(obj)` — verdict ∈ {correct, close, incorrect}, non-blank note.
- `grade_prompt(*, prompt_html, solution_ans, solution_note, answer)` — builds the grader prompt.
- `grade_answer(content_dir, course_id, lesson_id, answer, *, generate)` — loads the cached
  lesson server-side (so the client never ships prompt/solution), grades, **sanitizes the
  note through `sanitize_html`** (default-deny — the note is rendered as innerHTML), returns
  `{verdict, note}`. Returns `None` if the lesson does not exist.

`backend/app.py`:
- `POST /api/courses/<course_id>/lessons/<lesson_id>/grade` body `{answer}`. Validates ids
  (404), requires a non-empty answer (400), grades via `claude_client.run_structured(..., validate=valid_grade)`.
  `ClaudeAuthError → 503 {code:"reauth"}`, `ClaudeError → 502`, missing lesson → 404.
  (RESTful path that reuses the existing lesson endpoint shape — chosen over the draft's
  flat `/api/grade` that required the client to send prompt/context.)

## Frontend
- `frontend/src/courses.js`: `gradeAnswer({fetch, courseId, lessonId, answer})` → `{verdict, note}`
  or `{error}`.
- `frontend/src/views/lesson.js`: `gradeBlock(state)` renders the loading / verdict / soft-error
  states; the error string is run through `esc()` (defense in depth). "Check my answer" /
  "Check again" button gated on a non-empty answer and not-currently-grading.
- `frontend/src/app.js`: a `check-answer` handler grades on demand; captures `ui.lessonState`
  identity **and** `ui.screen === "lesson"` so a late result after navigation is discarded
  rather than painted over a different screen.
- `frontend/styles.css`: `.check-answer` (purple) + `.grade-*` banner palette + spinner.

## Test coverage (shipped)
- `tests/test_generation.py`: valid_grade, grade_prompt, grade_answer (incl. note sanitization,
  missing-lesson None).
- `tests/test_courses_api.py`: verdict happy path, empty-answer 400, missing-lesson 404,
  reauth 503.
- `frontend/tests/courses.test.js`: gradeAnswer POST shape + error shape.
- `frontend/tests/views.test.js`: button enable/disable, grading-independent-of-reveal,
  verdict banner, error escaping, no-banner-before-check.

## Verified
Pi e2e (Tailscale, throwaway course): "Correct" (green, warm note) and "Not quite" (pink,
specific note) both rendered; re-check worked; solution stayed hidden during grading.
