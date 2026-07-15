# Aligned Summative Assessment — Design

**Date:** 2026-07-15. **Sub-project C** of the Claude University roadmap.

**Decided with Werner:** module exams AND a comprehensive course final; mixed question format matched to Bloom level; pass = 80% (mastery bar); on failure a per-objective weak-spot report + unlimited fresh retakes. No gating or enforced remediation — sub-project D consumes these results later. No credential (charter): this verifies learning, it does not certify it.

## Why

Every lesson has Bloom-tagged objectives and every module has outcomes, but nothing ever tests across a module or the course, and "done" currently means "viewed all lessons". Constructive alignment demands a summative instrument built from those same objectives, with a defined pass standard.

## Exam blueprint

An exam is generated from the manifest's objectives, never free-styled:

- **Module exam** (`examKey = <module_id>`): exactly 10 questions covering that module. Every lesson in the module contributes at least one question. Question format follows the tested objective's Bloom level: `remember`/`understand` → MCQ; `apply` and above → short free-response.
- **Course final** (`examKey = final`): exactly 18 questions sampling the whole course, at least one per module, at least half from `apply`-or-higher objectives. The validator enforces the counts and coverage rules, so exam size is deterministic.
- Every question carries the objective it tests (`objectiveText`, `bloom`) and the `lessonId` that teaches it — this tagging powers the per-objective report and later sub-project D.
- The generation prompt receives: module/course outcomes, the lessons' objectives, and the knowledge-spine entries (exact term = definition pairs) so exam vocabulary matches what the lessons taught. Uses the existing generation path (Claude call, JSON validation, bounded retries → 502; sanitize_html on learner-visible fields).

**Question shape** (validated by `valid_exam`): `{type: "mcq"|"free", prompt, objectiveText, bloom, lessonId}` plus for mcq `choices` (3–5) + `answerIndex`, for free `modelAnswer` + `graderNotes`. `prompt`/`choices` are sanitized server-side and render raw client-side (same boundary as lesson fields). `answerIndex`, `modelAnswer`, `graderNotes` NEVER leave the server.

## Attempt lifecycle

1. **Start** — `POST /api/courses/<cid>/exams/<examKey>` generates a fresh exam (blocking call with a client loading state, exactly like lesson generation). The full exam (with key) is written atomically to `content/courses/<cid>/exams/<examKey>.json` (same learner-state-in-content precedent as `notes/`; covered by deploy excludes and the daily backup). Starting again overwrites — one pending attempt per examKey. The response/stream delivers only the key-stripped questions.
2. **Sit** — new exam screen: all questions on one page, answered at any pace, one submit. Client state is in-memory only; abandoning costs nothing (no attempt recorded until graded).
3. **Submit** — `POST /api/courses/<cid>/exams/<examKey>/submit` with `{answers: [...]}` (index-aligned; mcq = choice index, free = text). 400 if the answer count does not match the pending exam, an mcq index is out of range, or a free answer exceeds 5,000 characters; 404 if no pending exam exists. Server grades:
   - MCQ against `answerIndex` locally.
   - All free-response answers in ONE batched LLM grading call reusing the grade-verdict scale: `correct` = 1, `close` = 0.5, `incorrect` = 0 points (MCQ = 1/0). Validator requires a verdict + short feedback note per free question.
   - Score = points / total. **Pass = score >= 0.8.**
4. **Record** — the server itself inserts an `exam_result` event (synthesized client_event_id/session_id; `topic_id = examKey`) with payload: score, passed, attempt number, per-question results (verdict, points, objectiveText, lessonId; free-response feedback notes sanitized), per-lesson point aggregation. The pending exam file is deleted after successful grading.
5. **Grading failure** — 502; the pending exam file (with key) survives, the client keeps the answers and can resubmit without re-sitting. Only successful grading consumes the attempt.

## Results, retakes, and course pass

- **Result view**: overall score, PASS/FAIL, per-question feedback (MCQ: right/wrong + correct choice; free: verdict + grader note), and the weak-spot report — lessons whose questions scored below 80%, each listing the missed objectives and linking to the lesson.
- **Syllabus**: each module gets an exam row after its lessons, plus a final row at the end: `Not taken` / `Passed — best 87%` / `Failed — best 64% (2 attempts)`. Status computed live from `exam_result` events (same live-from-events philosophy as mastery). A "Take exam" / "Retake" action starts a fresh attempt; available anytime, no gating.
- **Course passed** = every module exam passed AND the final passed. Shown on the dashboard course card and syllabus header.
- History detail beyond best score/attempt count is not surfaced in C (the events hold it for D).

## Not in scope

No gating, no enforced remediation, no certificates, no time limits, no proctoring theater, no exam revision when a course is refined (a stale pending exam file for a removed module is ignored by status computation; apply_revision additionally deletes pending exam files for dropped modules, mirroring spine prune). No changes to lesson checks, pre-quiz, grading, SRS, or the compiler.

## Risks / honest caveats

- An 80% bar with LLM-graded free-response makes grading quality decisive. Mitigations: per-question feedback exposes the reasoning, retakes are free, and MCQ (objectively scored) anchors part of every exam.
- Fresh generation per attempt costs a Claude call per sit — acceptable for one learner; it is what keeps retakes meaningful.

## Testing

Backend: blueprint selection (every lesson covered, format-per-Bloom, final sampling rules), `valid_exam` accept/reject, key stripping (no answerIndex/modelAnswer in client payload), MCQ scoring + point math + 0.8 threshold edge (exactly 80% passes), batched grade validation, per-lesson aggregation, route contracts (start/submit/status), server-side `exam_result` insertion, grading-failure keeps pending file, apply_revision prunes dropped-module exam files. Frontend: syllabus exam rows per status, exam screen render + submit payload, result + weak-spot render, guard patterns (stale screen after await). Plus the app.js import-resolution check and full suites.
