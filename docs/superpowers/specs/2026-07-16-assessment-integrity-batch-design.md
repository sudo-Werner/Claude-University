# Assessment-integrity batch — design

**Date:** 2026-07-16. **Approved by Werner** (morning interview, all recommended options chosen).
Five items that complete the assessment story sub-project D started. Sequencing decision:
this batch ships before the Claude-in-lessons wave.

## Why

Sub-project D built the mastery loop (exams, gap reviews, SRS weak spots, transcript). The
standards audits left five approved gaps: create-level work is never assessed, retakes skip
the corrective step Bloom's loop requires, the prerequisite graph is compiled but consumed by
nothing, gap-review practice never rises above recall/recognition, and the transcript hides
the attempt journey on passed exams.

## Item A: Graded capstone

Today `GET /api/courses/<cid>/capstone/<scope>` generates and caches a read-only exploration
brief (`content/courses/<cid>/capstones/<scope>.json`: intro + 2-6 items of
title/detail/source). There is no submission or grading. This item adds both.

**Rubric.** New module `backend/capstone.py`. `ensure_rubric(content_dir, course_id, scope,
capstone, manifest, *, generate)` stamps a `rubric` field into the existing capstone JSON on
first need (read-time upgrade, same pattern as `_with_refreshed_source_types` — legacy cached
capstones on the Pi are never regenerated, only extended). Rubric shape:
`"rubric": [{"criterion": "<one assessable sentence>"}, ...]` — 4 to 6 criteria, generated
from the capstone's items plus the scope's objectives (module objectives for a module scope,
course outcomes for `"course"`). Validator `valid_rubric(obj)`: list of 4-6 dicts, each with
non-empty str `criterion`. Sanitize criterion as plain text (`html.escape`) — rendered
client-side raw inside the rubric list.

**Submission.** `POST /api/courses/<cid>/capstone/<scope>/submit` with `{"work": "<str>"}`
(non-empty, else 400). The route: load capstone (404 if absent), `ensure_rubric` under
`generation._gen_lock(("capstone", course_id, scope))`, build the grading prompt, one
`run_structured` call, record the result, return it. 502/503 semantics identical to the
exam-grade route.

**Grading.** `capstone_grade_prompt(*, capstone, rubric, work, scope_label)` demands ONLY
JSON: `{"perCriterion": [{"index": <int>, "met": "met"|"partial"|"unmet", "note": "<str>",
"evidence": "<verbatim quote from the submission, empty if none>"}, ...], "summary": "<str>"}`
— one entry per criterion, in order, evidence-quoting mandatory (same discipline as the exam
grader: an unmet criterion with no evidence field is invalid). Validator
`valid_capstone_grade(obj, rubric)`: exactly `len(rubric)` entries, indices 0..n-1 each
exactly once, `met` in the trio, `note` non-empty str, `evidence` a str (empty allowed),
`summary` non-empty str.

**Scoring.** `score = (met*1.0 + partial*0.5) / len(rubric)`; `passed = score >= 0.7`.
Rationale: project rubrics conventionally pass around 70% coverage with partial credit;
exams keep their 0.8 recall bar — different instruments, different bars. Constant
`CAPSTONE_PASS = 0.7` in `backend/capstone.py`.

**Recording.** Server-side event `capstone_result` (mirror of `exams.record_result`):
`record_result(conn, course_id, scope, result)` counts prior `capstone_result` events for
(course, topic_id=scope), stamps `attempt`, inserts with `session_id="server"`. Stored
payload: `{scope, score, passed, perCriterion, summary, attempt}` — perCriterion entries keep
met/note but drop `evidence` (never stored, same rule as exam grading). The API response
returns the full graded result including evidence and sanitized notes/summary
(`sanitize_html`), plus the rubric so the client can render criterion text beside verdicts.

**Not in scope:** capstone results do NOT feed the mastery accuracy pool (mastery is
per-lesson evidence; a capstone is holistic) and do NOT affect `course_passed` (courses on
the Pi must not retroactively lock). Transcript-only credit (Item E). No gating on
submitting; unlimited attempts.

**Frontend** (`frontend/src/views/capstone.js`, `frontend/src/app.js`, `courses.js`):
below the item list, a "Submit your work" card: textarea (`data-field="cap-work"`, input
handler mutates state without repaint — same pattern as explain), submit button
(`data-action="cap-submit"`), busy state while grading. After grading: per-criterion rows
(criterion text, met/partial/unmet badge, note, evidence quote when non-empty), summary
line, score + passed/failed, and a "Submit again" affordance (same textarea stays).
Sanitization boundary: notes/summary/criterion arrive server-sanitized → render raw;
evidence is a verbatim quote of learner text → `esc()` client-side. Client logs no event
(the server records `capstone_result`). Result state lives in the capstone screen state
only (re-opening re-fetches nothing; latest result visible on the transcript).

## Item B: Retake gating (corrective-then-reassess)

**Rule.** A retake of exam `key` is blocked until the Fix-the-gaps session for the latest
failed attempt is completed — but only while the exam is not yet passed. Precisely, in
`start_exam` after the existing final-lock guard: let `status = exams.exam_status(...)`,
`latest = remediation.latest_failed_result(conn, course_id, exam_key)`. If
`status.get(exam_key, {}).get("passed")` → allow. Else if `latest` is not None and
`not remediation.session_completed(conn, course_id, exam_key)` → 409
`{"error": "Complete the gap review before retaking — that's the corrective step."}`.
First attempts (no prior result) always allowed. Applies to module exams and the final.

**Completion detector.** `remediation.session_completed(conn, course_id, exam_key)`:
load the stored session; if absent → False (the gap review hasn't even been generated).
Expected work = every practice item index (flat, matching the frontend's `flatPractice`
ordering) plus one apply item per gap (Item C). Answered work = distinct `payload.index`
values from `lesson_check` events with `payload.source == "remediation"`,
`payload.examKey == exam_key`, `payload.attempt == session["attempt"]`, plus distinct
`payload.index` from `lesson_explained` events with the same source/examKey/attempt markers.
Completed when both sets cover their expected counts. Guarded payload parsing throughout
(events are client-forgeable; malformed → skip row).

**Frontend event enrichment** (required by the detector): `answerPractice` adds
`examKey: st.examKey, attempt: st.session.attempt` to the `lesson_check` payload; the apply
submission (Item C) logs the same markers.

**Frontend UX.** Exam-result screen after a fail: replace "Retake with fresh questions" with
the existing "Fix the gaps" primary action plus a line "Retake unlocks after the gap review."
Remediation screen: the retake button renders disabled until every item in the session is
answered (client state knows), with text "Answer everything above to unlock the retake";
backend 409 remains authoritative (surface its error message if it fires anyway).

**Legacy note (one-time shift):** existing failed exams on the Pi will require the gap
review before retake immediately — that is the intended behaviour. Remediation answers
logged before this ships lack `examKey`/`attempt` markers and will not count; the learner
redoes the (re-served, free) session. Acceptable: single-learner platform, correct-by-Bloom.

**Accepted risk:** if remediation generation persistently 502s, the retake stays blocked
until a retry succeeds. The retry path exists; no override valve (YAGNI).

## Item C: Free-response apply practice in gap reviews

Each gap gains exactly one apply-level free-response item alongside its 2-3 checks.

**Generation** (`backend/remediation.py`): `remediation_prompt` additionally demands, per
gap, `"apply": {"prompt": "<a novel scenario requiring the objective — not recall>",
"modelAnswer": "<what a correct answer covers>"}` (novel-scenario clause verbatim from the
exam prompt). `valid_remediation`: each gap must carry `apply` with non-empty str
`prompt`/`modelAnswer`. `finalize_session` sanitizes both and stores
`gap["apply"] = {"prompt": ..., "modelAnswer": ...}`. Legacy sessions on disk lack `apply`
— all consumers must treat it as optional (detector counts it only when present; UI renders
it only when present). A newer failed attempt regenerates with apply items as usual.

**Grading route.** `POST /api/courses/<cid>/exams/<exam_key>/remediation/grade` with
`{"gapIndex": <int>, "answer": "<str>"}`. Load session (404 if absent), bounds-check
gapIndex and require the gap to have `apply` (400 otherwise), non-empty answer (400).
Build `generation.grade_prompt(prompt_html=apply.prompt, solution_ans=apply.modelAnswer,
solution_note="", explanation=answer)` — reuse the existing exercise grader verbatim
(verdict trio + note, validated by `valid_grade`). Return `{"verdict", "note"(sanitized),
"modelAnswer"}` — the model answer is revealed only after grading, like a solution reveal.
No new prompt builder unless `grade_prompt`'s signature genuinely cannot express it — check
first; if a remediation-specific builder is needed it must keep the verdict trio and
`valid_grade`.

**Events + mastery.** On success the frontend logs `lesson_explained` with
`{verdict, source: "remediation", examKey, attempt, index}` and `topicId` = the gap's
lessonId. `mastery._accuracy_pool` already folds `lesson_explained` verdicts at
correct=1/close=0.5/incorrect=0 — apply answers feed mastery with partial credit for free.
Verify the pool's payload handling tolerates the extra keys (it reads only `verdict`).

**Frontend** (`views/remediation.js`, `app.js`): after each gap's practice items, an
"Apply it" block: prompt (server-sanitized → raw), textarea, submit
(`data-action="rem-apply"` with `data-gap`), busy state, then verdict badge + note (raw,
sanitized) + model answer (raw, sanitized). One submission per gap per session (button
disables after a verdict; state keeps `applyResults[gapIndex]`). The retake-unlock logic
(Item B) counts apply items answered when present.

## Item D: Prerequisite graph consumers (no new Claude calls)

The compiled per-lesson `prereqs` arrays (earlier-lesson ids, validated DAG) finally get
consumers. Pure frontend; the data ships in every manifest already.

1. **Syllabus** (`frontend/src/views/syllabus.js`): under each lesson's objectives, when
   `lesson.prereqs` is non-empty: `Builds on: <title>, <title>` — titles resolved from the
   manifest (id → title map built once per render), `esc()`'d, plain text (no links in the
   syllabus review screen; it renders pre-enrolment).
2. **Gap reviews** (`frontend/src/views/remediation.js`): each gap card whose lesson has
   prereqs in the manifest gets `Builds on:` followed by lesson-chip buttons
   (`data-lesson="<id>"`) that open the upstream lesson — the "trace the weakness to its
   root" affordance. `remediationHTML` gains the manifest (or a prebuilt id→title map) as a
   parameter; `paintRemediation` wires `[data-lesson]` clicks to `openLesson`.
   Unknown ids (revised-away lessons) are skipped silently.

Not building: curriculum-row chips (clutter), visual course map, adaptive ordering (both
"bigger consumer later" material).

## Item E: Transcript attempts on passed rows

`frontend/src/views/transcript.js` `examRow` passed branch adds the attempt count:
`87% · 2026-07-14 · 3 attempts` (singular "1 attempt"). Data is already in the payload.

**Capstone rows** (completes Item A): `backend/transcript.py` `course_record` gains
`"capstones": [...]` — one row per scope with at least one `capstone_result` event:
`{scope, title, attempts, bestScore, passed, passedOn}` where title is the module title or
"Course capstone", passed = any attempt passed, passedOn = date of first passing attempt
(same `_first_pass_dates` approach, reused or mirrored for `capstone_result`). Frontend
renders capstone rows after the final-exam row, labelled `Capstone: <module title>` /
`Course capstone`, same status treatment as exam rows (including attempts). Courses with no
capstone submissions show nothing new.

## Security

Established boundary holds everywhere: server-sanitized HTML fields render raw client-side;
learner-derived text (`evidence` quotes, typed answers) is `esc()`'d client-side; plain-text
fields stamped server-side from client-forgeable event payloads are `html.escape`'d at
stamp time. All new event reads guard against malformed payloads (forged-event rule from the
robustness audit).

## Testing

Backend: pytest per module — rubric ensure/validate (including legacy file upgrade), grade
validation (duplicate indices, missing evidence, wrong count), scoring/threshold edges,
record_result attempt stamping, submit-route statuses (400/404/409/502), retake-gate matrix
(no prior result / latest failed + incomplete / latest failed + complete / already passed /
legacy events without markers), session_completed with and without apply items,
remediation grade route statuses, transcript capstone rows. Frontend: `node --test
frontend/tests/*.test.js` — capstone submission card states, transcript passed-row attempts
+ capstone rows, remediation apply block + retake-unlock rendering, syllabus builds-on
lines. After touching app.js: the import-resolution check.

## Deploy notes

Standard DEPLOY.md flow. Legacy data on the Pi: cached capstones lack `rubric` (upgraded at
first submission), remediation sessions lack `apply` (optional everywhere), old remediation
events lack markers (one-time redo, see Item B). No DB schema change — new event type
`capstone_result` needs whitelisting in `stats.py` STUDY_EVENTS/ACTIVITY_EVENTS (with an
activity label like exam entries) so capstone work counts toward streaks and the activity
feed.
