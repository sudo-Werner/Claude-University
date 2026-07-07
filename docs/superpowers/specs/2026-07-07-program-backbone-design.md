# Sub-Project A — Program Backbone: Intake → Grounded Curriculum → Objectives

**Date:** 2026-07-07
**Status:** Design — awaiting Werner's review before implementation planning.
**Part of:** the "real education" program (A→E). See research: [2026-07-07-real-education-design.md](../../research/2026-07-07-real-education-design.md).

## Goal

Turn course creation from "a short chat proposes a list of titles" into a rigorous, evidence-based
**program-design** flow that produces a real syllabus: a curriculum **grounded in canonical sources**,
with **measurable, Bloom-tagged learning objectives**, a **prerequisite graph**, a **declared depth
level**, and a **workload estimate** — and retrofit the four existing courses to the same structure.
This is the foundation every later sub-project (B–E) aligns to and gates on.

## Why (evidence)

From the research synthesis: rigorous curricula are built by **backward design** (outcomes →
assessment → teaching) with **constructive alignment** (the objective's verb must be activated in the
activity and verified in the assessment); grounded in the discipline's **canonical body of knowledge**
rather than free-associated; structured as a **prerequisite graph** (enabling upstream remediation);
and expressed as **measurable objectives** (action verbs; "understand/know" are not assessable).
"University-level" is a measurable target (credit-hour / ECTS workload ≈125–150h per course; declared
level via qualification frameworks; outcomes constructively aligned and assessed). A delivers the
structural half of that; assessment/mastery (specs 9–10, 12–13) come in C/D.

## Scope decisions (settled with Werner)

1. **Applies to new courses AND retrofits all four existing courses** (migration included).
2. **Placement is folded into the intake conversation** — no separate quiz; the intake dialogue probes
   prior knowledge and Claude uses it to set starting depth / mark familiar material.
3. **Rigor signals: level prominent + hours as a one-time scope estimate** — no daily-time tracking
   (preserves the self-paced, time-neutral feel decoupled earlier).
4. **A includes a syllabus-level accuracy sweep** (outline + objectives fact-checked against sources).
5. **Lesson-content factual-rigor is deferred to sub-project B** (it operates on lesson bodies,
   alongside cross-lesson coherence). B's scope grows to include it.

## Non-goals (A)

- Regenerating existing lesson **bodies** (migration enriches structure only; bodies get accuracy +
  coherence alignment in B, or when regenerated/deepened).
- Full redesign of an existing course's outline (enrichment layers rigor onto the current structure;
  a structural redesign that resets progress is a separate opt-in action, not A).
- Assessment, mastery gating, remediation, transcript, spaced-review engine (C/D).
- Audio/podcast (E).
- Concept-level knowledge graph (A uses **lesson-level** prerequisites; a finer concept graph is a
  possible future refinement).

## The flow

1. **Intake conversation** (interactive; reuses the existing course-creation chat surface). Claude
   interviews the learner to build a structured **learner brief**: the goal/transfer wanted, background,
   prior knowledge (probed conversationally = placement), motivation, and desired depth. Ends when it has
   enough. On readiness it emits a fenced `learnerBrief` JSON block (replacing today's `course` block).
2. **Compile** (staged backend pipeline, behind a "building your program" loading screen). Turns the
   brief into a proposed syllabus. Not yet saved.
3. **Syllabus review** (new screen). The learner sees the proposed program before committing: outline
   (modules → lessons), per-lesson objectives, declared level, ~hours, skills, and the **grounding
   sources**. Accept → the course is written and lessons generate lazily as today. Or request changes →
   recompile.

## Data model

A compiled course extends the current `course.json` (additive; legacy courses without these fields
still load). `schemaVersion: 2` marks a compiled course.

```json
{
  "id": "…", "title": "…", "subtitle": "…",
  "schemaVersion": 2,
  "brief": "one-paragraph generation context (kept, derived from the learner brief)",
  "learnerBrief": {
    "goal": "what the learner wants to be able to DO (the transfer)",
    "background": "prior experience in their words",
    "priorKnowledge": ["topics judged already-known from the intake conversation"],
    "motivation": "why",
    "desiredDepth": "their stated depth preference"
  },
  "level": { "code": "bachelor-y2", "label": "Bachelor Year 2-equivalent" },
  "targetHours": 130,
  "skills": ["…", "…"],
  "outcomes": [ { "text": "measurable course outcome", "bloom": "analyze", "knowledge": "conceptual" } ],
  "groundingSources": [ { "title": "…", "url": "https://…", "type": "university" } ],
  "modules": [
    {
      "id": "m1", "title": "…",
      "outcomes": [ { "text": "…", "bloom": "apply", "knowledge": "procedural" } ],
      "lessons": [
        {
          "id": "…-l1", "title": "…",
          "objectives": [ { "text": "Calculate X using Y", "bloom": "apply", "knowledge": "procedural" } ],
          "prereqs": ["…-l0"],
          "estMinutes": 90
        }
      ]
    }
  ]
}
```

- **Objective** = `{ text, bloom, knowledge }`. `bloom` ∈ {remember, understand, apply, analyze,
  evaluate, create}. `knowledge` ∈ {factual, conceptual, procedural, metacognitive}. The `text` must
  begin with / center on an action verb and must **not** rely on banned non-observable verbs
  (understand, know, learn, appreciate, grasp, "be aware/familiar with").
- **level.code** ∈ a small enum {foundation, bachelor-y1, bachelor-y2, bachelor-y3, master}, each with
  a friendly `label`. Derived by the compiler from the learner brief; confirmable in review.
- **prereqs** = list of earlier lesson IDs this lesson builds on (the prerequisite-graph edges). Must
  reference lessons that appear earlier in the flat order; the graph must be acyclic.
- **estMinutes** per lesson feeds `targetHours` (Σ estMinutes / 60).

### Workload realism (honest note)

125–150h is *total* learning effort (reading + practice + assessment + review), not lesson-text reading
time. Today's lessons are thin, and assessment/review (C/D) don't exist yet. So in A, `targetHours` is a
**declared scope target that sizes the outline** — the compiler produces enough modules/lessons/depth
(grounded in what a real course at that level covers) to *plausibly* fill the band once B/C/D add depth,
practice, and assessment. A does not claim the hours are already realized. This also fixes a current
weakness: the old default (3–6 thin modules) under-scopes; outline granularity now scales to level+hours.

## Components

### Backend (`backend/`)

- **`generation.py`**
  - Rewritten `COURSE_SYSTEM_PROMPT` — conducts the richer intake interview (goal/transfer, background,
    conversational placement, motivation, desired depth); emits a fenced `learnerBrief` block when ready.
  - `detect_brief(text)` — parse the `learnerBrief` fenced block (mirrors `detect_proposal`).
  - Objective/graph validators: `valid_objective`, `valid_outcomes`, `valid_prereq_graph` (acyclic +
    edges reference earlier lessons), `valid_compiled_course` (whole-schema).
  - `BANNED_OBJECTIVE_VERBS` + a lint used by `valid_objective`.
  - The compiler prompts + stage functions (below), or a new module if `generation.py` grows unwieldy
    (see "File organization").
- **`compiler.py`** (NEW — keeps `generation.py` from ballooning). The staged course compiler:
  - `compile_course(learner_brief, *, generate_sourced, verify) -> compiled_course_dict`
  - Stage functions: `_grounded_outline`, `_objectives_and_graph`, `_accuracy_sweep`, `_assemble_contract`.
  - `enrich_course(existing_manifest, *, generate_sourced, verify) -> compiled_course_dict` — the
    migration path: preserves module/lesson IDs and order, adds the rigor layer.
- **`courses.py`** — `write_course` extended to persist the compiled shape; `load_manifest` tolerant of
  both schema versions.
- **`app.py`** — new/extended routes:
  - `POST /api/courses/compile` — body `{learnerBrief}` → runs `compile_course` → returns the proposed
    compiled course (NOT saved). Uses `run_sourced` for the grounded stages (outline, accuracy sweep)
    and `run_structured` for the structured stages (objectives/graph, contract) — same wiring pattern as
    lessons.
  - `POST /api/courses` — accepts the reviewed compiled course and writes it.
  - Auth/error handling identical to existing generation routes (reauth 503, ClaudeError 502).

### Frontend (`frontend/src/`)

- **`views/chat.js` / `chat.js`** — reuse the intake chat; detect the `learnerBrief` block (instead of
  `course`) and transition to compile.
- **`views/syllabus.js`** (NEW) — the syllabus-review screen: modules→lessons with objectives, the level
  badge, ~hours, skills, and grounding sources; Accept / Request-changes actions.
- **`views/course.js` / dashboard** — course-page contract display: level badge (prominent), ~hours (as
  scope), course outcomes, skills, grounding sources. Legacy courses (no compiled fields) render as today.
- **`app.js`** — wire the flow: intake → `POST /compile` (staged loading screen) → syllabus review →
  `POST /courses` on accept.

### Migration (one-off)

- A script (pattern: the consistency maintenance pass) that runs `enrich_course` over the four existing
  courses, atomic-writes the enriched `course.json`, preserves lesson IDs + progress, and reports per
  course what was added. Coordinated (don't clobber active study; check no in-flight generation).

## The compiler stages (detail)

The **outline** and **accuracy** stages are web-grounded (`run_sourced` + the `_resolve_sources` trust
guarantee — only real retrieved sources are kept). The **objectives/graph** and **contract** stages are
structured (non-web), since they operate on the already-grounded outline. The accuracy sweep is therefore
web-grounded *and* structured audit-first: a cheap `{ok, issues}` audit against the sources, then correct
only the flagged parts — the pattern from the consistency pass. Each stage validates its output and
retries on failure.

1. **Grounded outline** — input: learner brief (+ for migration, the existing outline). Web-searches
   canonical sources (`.edu` syllabi, established textbooks, professional-society guidelines) for the
   subject at the declared level; proposes modules → lessons **sized to the level + hours band**; returns
   outline + `groundingSources` (only sources actually retrieved). Migration variant: keep IDs/order,
   attach grounding.
2. **Objectives + prerequisite graph** — per lesson: 1–3 measurable Bloom-tagged objectives; roll up to
   module + course outcomes; derive `prereqs` edges. Validate: `valid_objective` (verb lint + tags),
   every lesson traces to a module outcome, `valid_prereq_graph` (acyclic, earlier-only edges).
3. **Accuracy sweep** — a web-grounded audit of outline + objectives against the canonical sources:
   correct topics, sound order, accurate/correctly-leveled objectives, no glaring omissions. Audit-first:
   `{ok, issues}` → only rewrite the flagged parts. Falls back to unchanged on failure (never worse).
4. **Contract assembly** — compute `level`, `targetHours` (Σ estMinutes), `skills`. Assemble the final
   compiled course for review.

## Downstream interface (to B–E)

- New lesson generation (`lesson_prompt` / `_generate_and_store_lesson`) is extended to **receive the
  lesson's objectives** and align its teaching + checks to them (constructive alignment — verb match).
  This is the minimal consumer that makes NEW courses coherent end-to-end in A. **Full** cross-lesson
  coherence and the lesson-content **factual-rigor pass** are sub-project **B**.
- The prerequisite graph is the substrate for D's graph-driven remediation (fail downstream → review
  upstream) and the spaced-review engine.
- Objectives + outcomes are the assessment targets C aligns to and the mastery signals D gates on.

## University-equivalence specs A satisfies

Fully: **1** (workload target), **2** (per-lesson hours), **3** (measurable outcomes/objectives), **5**
(declared level), **8** (rigor/coherence via grounded outline + acyclic graph), **11** (authoritative
grounding). Partially / sets up: **4** (alignment — objectives handed to lessons; full enforcement in
C), **6–7** (autonomy/integration — via level; deepened in B/C). Assessment specs **9–10, 12–13** are C/D.

## Error handling

- Compiler stage failure after retry → surface a clear "couldn't build your program, try again" (502),
  never write a partial course. Auth failure → existing reauth 503 path.
- Accuracy sweep / verify failure → fall back to the un-swept (but validated) syllabus rather than block
  creation; log that the sweep was skipped (no silent success claim).
- Migration: per-course try/except; one course failing doesn't abort the batch; atomic writes; report
  clean/enriched/error counts.

## Testing strategy

- `valid_objective` — accepts action-verb objectives with valid bloom/knowledge tags; rejects banned
  verbs ("understand/know/…") and missing tags.
- `valid_prereq_graph` — accepts a DAG with earlier-only edges; rejects cycles and forward/unknown edges.
- `valid_compiled_course` — accepts the schema; rejects missing outcomes/objectives/level.
- Each compiler stage with mocked `generate_sourced`/`verify` (deterministic dicts): outline, objectives
  + graph, accuracy sweep (audit-clean → unchanged; audit-flagged → corrected), contract math
  (targetHours = Σ estMinutes/60; level derivation).
- `enrich_course` — preserves lesson IDs + order + existing progress mapping; adds the new fields;
  idempotent (re-running is a no-op on an already-enriched course).
- `detect_brief` — parses the `learnerBrief` block; ignores prose.
- Routes: `POST /compile` returns a proposed course without saving; `POST /courses` writes the compiled
  shape; reauth/ClaudeError paths.
- Backwards-compat: a legacy `course.json` (schemaVersion absent) still loads and renders.
- Frontend: `views/syllabus.js` renders outline/objectives/level/hours/sources; intake detects the brief
  block and transitions; legacy course pages render without the new fields.

## Risks / open questions

- **Auto-generated prerequisites can be wrong** (research caveat). Mitigation: validate acyclicity +
  earlier-only edges; treat as drafts the learner sees in review; keep them lesson-level (not concept).
- **Compile latency** — several grounded stages (~50–190s each) mean compile could take multiple minutes.
  Mitigation: staged loading screen with honest status; it's a one-time-per-course cost. Confirm the
  waitress `channel-timeout=600` covers it (raise if a full compile exceeds it).
- **Migration disruption** — enriching a course you're mid-study changes its course page (adds
  objectives/level/hours) but not its lessons/IDs/progress. Acceptable and additive; flagged.
- **Hours honesty** — `targetHours` is a sized target, not realized effort until B/C/D. Must be framed as
  "estimated total effort," never "you have done N of 130 hours."
