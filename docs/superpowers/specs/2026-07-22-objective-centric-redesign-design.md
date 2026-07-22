# Objective-Centric Learning Redesign — Design

**Date:** 2026-07-22
**Status:** Design draft for Werner's review (brainstorming). NOT yet approved; NOT committed.
**Provenance:** Synthesized from six research/design workflows this session — online-university lesson structure; Udemy + Dutch/European exam processes; traditional-university curriculum construction; whole-project audit + metrics; the objective-centric pipeline design + adversarial accuracy review; and SOTA curriculum construction (CBME/EPAs, learning engineering, Knowledge Space Theory). Findings tagged web-verified vs training-knowledge in the source workflow outputs.

---

## 1. Problem

Three linked defects, one root cause.

1. **Lessons are thin vs a real university.** Each lesson is a single ~1000-word exercise (measured 800–1270 words; ~85–135 words of actual explanation). Generation literally prompts "write a single exercise-style lesson." University depth comes from a *chain* of small teach→check atoms, one per objective — not more words in one atom.
2. **Exams test untaught material.** The exam blueprint samples a lesson's *assigned* objectives, but a single exercise only *teaches* a slice of them — so "assigned to the lesson" ≠ "taught by the lesson." (Confirmed: Human Body Module-1 Q10 tested l2's ATP-yield objective; l2's spine shows it taught only membrane signalling.)
3. **No completeness guarantee.** Even if we teach and assess every objective we derive, nothing verifies the derived set is the *complete and correct* set required to pass the level. The compiler grounds in canonical sources and accuracy-sweeps for *correctness*, but never checks *completeness*.

Plus honest-UX debt surfaced by the audit: a hard-coded fake "90-minute session" is shown to the learner (`app.js:40 SESSION_MIN=90`); "mastered" means "reviewed ≥3 times" (conflates review cadence with demonstrated ability); mastery is tracked per-lesson, never per-objective; and the app computes almost none of the learning analytics its event log already supports.

**Root cause:** everything is *lesson-grained*. A lesson is an opaque container that both teaches and is assessed as a whole, and objectives are anonymous `{text, bloom, knowledge}` dicts embedded inside it.

---

## 2. Goals & non-goals

**Goals**
- Make the **objective** the atomic unit of the whole system — diagnosed, taught, assessed, mastery-tracked, and spaced at objective grain.
- Guarantee, by construction, that (a) the curriculum's objective set is *complete* for the level, (b) every objective is *taught*, and (c) every objective is *assessed*.
- Add university-grade teaching depth (worked examples, per-objective teach→check) **without** losing the active-retrieval strength that is our best asset.
- Replace fake/《cadence-as-mastery》 signals with honest, per-objective measurement.

**Non-goals / explicitly out**
- No passive lecture/reading layer (OMSCS and Brilliant prove degree-rigor with near-zero lecture — depth comes from more teach→check atoms, not prose).
- No cohort-data methods (learning-curve KC validation, IRT calibration, A/B-tested content) — impossible at one learner; using them would be false precision.
- No "2-sigma" or folklore framing anywhere.
- Keep the learning-*preferences* quiz? Recommend **dropping** it — it is learning-styles-adjacent, which is not evidence-based.

---

## 3. Core principle & the keystone

**Principle:** the objective is the atomic unit end to end.

**Keystone change (blocks everything else):** lift objectives out of anonymous embedded dicts into a **course-level registry of first-class entities with stable IDs** (`o1…oN` at compile, slugged `<courseId>-oN` at write, preserved across revisions positionally exactly as lesson ids are today). The objective **id** and its one Bloom **verb** are the two invariants welded across every stage — the join key for diagnosis, competency mapping, teaching segments, checks, exam blueprint slots, mastery, and spaced review.

---

## 4. The pipeline

### Stage 0 — DEFINE: completeness / competency layer (new; the answer to "what must you master to pass this level")

Adopts the medical Competency-Based model (the one SOTA family that is a structural authoring-time guarantee, so it transfers to n=1).

- A web-grounded call emits an explicit **required-competency list** for `(subject, level)`, anchored in external authorities (subject-benchmark statements, professional-body outcomes, canonical textbook TOC, degree curricula). Each competency = `{id, text, targetLevel}` where `targetLevel` is a *target mastery level* (Bloom/entrustment-style), never binary "covered."
- This list is a **durable artifact that sits ABOVE the lesson list** and the audit runs against *it*, not against generated lessons.

### Stage 1 — EVALUATE: placement diagnostic (new)

Resolves the chicken-and-egg (objectives don't exist yet) via a cheap **scope skeleton** — big ideas + candidate objectives derived before the diagnostic, which the diagnostic probes against.

- **Instrument: prerequisite-structured adaptive routing — NOT CAT/IRT.** IRT needs a calibrated item bank we cannot have; claiming it is false precision. Instead, adaptivity comes from *structure*: probe the hardest/highest-Bloom node in each strand; if passed (confidently), impute mastery of its prerequisite chain (DAG-justified, not psychometric); if failed, descend to localize the frontier. Formally grounded in **Knowledge Space Theory** (Doignon & Falmagne — the basis of ALEKS: knowledge states, fringes, learning paths).
- **Cost-honest:** a 2-round batch (one call for anchors, one for targeted follow-ups), ~10–12 items, ≤~10 min — not per-answer round-trips. Runs on the background-job path.
- **Output:** a per-candidate profile `{status: known|uncertain|gap, pKnown, confidence, evidence: directlyTested|imputed|untested, misconceptions[]}` using a **one-shot Bayesian (guess/slip) update**, mapped to honest bands (never a false-precise %), with confidence capped for imputed nodes.
- **Uses:** scopes the curriculum (a confidently-known objective **compresses to a brief review pass — never fully dropped**, per decision §5); seeds the per-objective BKT prior; and sets the per-objective scaffolding start level (expertise-reversal — experts get less worked-example guidance from the start).

### Stage 2 — DERIVE: outcomes-first compiler + completeness gate

Inverts the current compiler (which fixes lesson *titles* first, then pours objectives in).

- **Order:** scope skeleton (big ideas + candidate objectives) → diagnostic → derive final objectives scoped to the gap → **form lessons by clustering objectives around a single big idea** (a validated non-trivial `bigIdea` per lesson).
- **Enforce:** a hard 1–3 coherent-objectives-per-lesson budget (validator, not prompt text); Bloom-verb tagging; objective-level prerequisite DAG.
- **Competency-first:** every objective must cite the competency id(s) it serves (the edge that makes coverage checkable).
- **VERIFY (new hard compile gate):** build the **competency × objective matrix** (ten Cate grid / CDIO ITU). **Fail compile** on any required-competency row with zero mapped objectives (gap). **Flag** any objective mapped to no competency (orphan). **Depth audit:** the objectives mapped to a competency must actually *reach its targetLevel* (computed from Bloom tags) — a competency needing "apply" is not satisfied by only "remember" objectives. **Reachability:** extend the existing acyclic-DAG check with a KST well-gradedness assertion — every required competency's terminal objective sits on a gap-free prerequisite path from an entry node. **Doer-effect gate:** fail on any required competency whose chain has exposition but no bound practice/check.
- **Emit** the compile-time exam blueprint (Table of Specifications: objective × Bloom × item count), weld it to competencies, and weight it by Impact × Frequency (principle, not fine proportions).
- Keep the existing canonical-source grounding and one-directional accuracy sweep.
- **Output:** a schemaVersion-3 manifest adding the `objectives[]` registry, the `competencies[]` artifact, and the blueprint.

### Stage 3 — TEACH: objective-indexed segment chain

- A lesson becomes a chain of **collapsible, self-paced** teach→check segments (Werner's chosen pacing), one per objective, each: a short `conceptIntro`; a **3-part worked example** (`why → ordered steps[] → commonTrap`) with **faded variants** (client reveals a prefix of steps by mastery — full example for novices, fading to a bare problem for the near-expert, respecting expertise-reversal); the **concept-check**; a **post-attempt explanation shown even when correct** (Brilliant-style, retrieval-first); and a generation-time `misconceptions[]` map (likely wrong answers → the misconception → a targeted hint).
- **Coverage by construction:** a validator fails generation unless every objective has a taught segment AND ≥1 check.
- **Cost/timeout:** generate segments lazily/streamed per objective, reusing `jobs.py` + the live-progress feed already built.
- **Bookends** (OU leereenheid): the objective stated in learner-facing terms at the top of each segment, and a one-line recap immediately before the check.

### Stage 4 — EVALUATE objectives: programmatic mastery + honest metrics

- **Ladder:** per-segment formative checks (unlimited, low-stakes) → an end-of-lesson **graded roll-up sampling ALL the lesson's objectives** (assembled from already-generated checks — no new paid call) → module/final exams blueprinted **only from covered objectives**.
- **Per-objective mastery: fixed-parameter BKT**, aggregating check history + roll-up + exam items + spaced-review recall — **programmatic assessment** (van der Vleuten): reliability from many low-stakes points, not one test. This is an **awareness layer**, not a gate.
- **Gating (Werner's decision §5): exams remain the single hard gate** (all module exams → final). The BKT per-objective signal informs the learner (a competency/mastery map), drives scaffolding and review, but does not itself gate.
- **Honesty fixes:** separate "demonstrated mastery" (earned by performance) from "review cadence" (reported separately) — replaces `level_for`'s reps≥3 rule. **Guessing-correct** MCQ scoring (subtract chance; today it's raw 1.0/0.0) — applied internally only; the learner always sees a clean 0–100% (no negative per-question numbers). Practice-mode vs exam-mode on the same blueprint. Diagnose-then-route resit: on failure, show which objectives failed, route to their segments, regenerate fresh questions.
- **Spacing: adopt FSRS** (default weights, no per-user training — Pi stays light) over SM-2 (whose expanding-interval assumption is empirically weak). Objective-grained review; the recall signal is **graded** (answer latency + hint use + retry count), not binary; interleave objectives within a review session (but never interleave expository prose). Retrievability = P(recall now).
- **Kill fake metrics + light up the starved analytics** (mostly free from existing events): real **time-on-task** (sessionized, idle-capped — removes `SESSION_MIN=90`); **retrievability**; **solution-peek/gaming** and **persistence** from the already-logged-but-unused hint/solution events; **completion/drop-off**; **lapse/leech**; a **confidence tap** for calibration (Brier) — one small new input, also enabling the hypercorrection effect.

---

## 5. Decisions (Werner)

- **Gating:** exams stay the hard gate; the aggregated per-objective BKT evidence is an **awareness/visibility layer**, not a gate.
- **Scoping:** **no objective is ever fully dropped** — a confidently-known one compresses to a brief review pass.
- Adopt **FSRS** over SM-2. Move **compile onto the background-job path**. Add the **confidence tap**. Build the **roll-up from existing checks** (zero paid calls). Rename `diagnostic.js` → placement; drop or repurpose the learning-preferences quiz.
- **Guessing-correction:** applied **internally only** — the learner always sees a clean 0–100% score, never a negative per-question number.
- **FSRS recall signal:** **graded** (from answer latency + hint use + retry count), not binary right/wrong.
- **Objective storage: single master copy (refs-canonical)** — objectives live only in the registry; lessons/exams/events reference them by id through one resolver (single source of truth). Trade-off accepted: the Phase-0 data-model cutover touches every objective-reader at once rather than allowing a gradual dual-read.
- **Cost:** the paid-call increase (scope skeleton + diagnostic + per-segment generation + competency/matrix validation retries) is accepted (Werner: token cost is not a constraint).

---

## 6. The objective data model (the spine)

Registry fields on `manifest.objectives[]` (schemaVersion 3):

- `id` — stable, positionally preserved across revisions. THE join key. (Owner: Stage 2; the one blocking dependency.)
- `text` — verb-led, measurable, banned-verb lint.
- `bloom` — one terminal verb (the constructive-alignment invariant).
- `knowledge` — factual | conceptual | procedural | metacognitive.
- `bigIdea` — one enduring-understanding sentence, validated non-trivial.
- `competencyRefs[]` — the required competencies this objective serves (Stage-0 ids). Powers the completeness matrix.
- `prereqs[]` — objective-level acyclic DAG, earlier-only, KST well-graded.
- Seeds/state keyed by id: diagnostic `preScore` + `scaffoldStart`; per-objective `mastery` (BKT posterior + opportunities); FSRS review state; event tags (`lesson_check`, `explain`, exam per-question all carry the objective id).

Separate artifacts: `competencies[]` (Stage 0) and the exam `blueprint` (Table of Specifications), both at course level.

---

## 7. SOTA grounding & honest magnitudes

Backward design (Wiggins/McTighe); constructive alignment (Biggs; Bloom-verb invariant); CBME + EPAs + the competency×unit coverage matrix (ten Cate; ACGME Milestones; CDIO); Knowledge Space Theory (Doignon & Falmagne / ALEKS); worked-example effect + faded guidance (Sweller); retrieval practice / testing effect; segmentation (Mayer, ~6-min engagement cap); programmatic assessment (van der Vleuten); Bayesian Knowledge Tracing; the doer effect (CMU KLI/OLI); FSRS.

**Honest effect sizes (never inflate):** aligned mastery learning d≈0.4–0.5; human tutoring d≈0.79 (VanLehn 2011, not "2-sigma"); retrieval practice g≈0.5–0.7 measured *vs restudy* (so it justifies a check-heavy spine but does NOT justify thin teaching — it was never measured against no-teaching).

---

## 8. Accuracy corrections applied (from the adversarial review)

- **Drop per-objective Hake normalized gain** — it's a group-level statistic, essentially meaningless at n=1. Keep a simple pre/post delta, labelled as noisy.
- **BKT must not declare "mastered" in ~2 items** — require a minimum number of independent opportunities and/or a higher threshold; treat the diagnostic as the prior only, never also as a BKT observation (double-count).
- **"Spiral (Bruner)" was mislabeled** — what we do is chain *distinct* objectives at ascending Bloom via prerequisites; name it that, don't claim spiral.
- **Exam-bug framing:** the blueprint *does* draw from a lesson's assigned objectives; the defect is assigned≠taught. Coverage-by-construction closes exactly that.
- **Model LLM-grader error in the guess/slip parameters** for free-response (effective guess = grader leniency; effective slip includes grader false-negatives).
- **"Retrieval without feedback has no benefit" is an overclaim** — the testing effect is robust over restudy even without feedback; don't use it to justify the design.
- Don't replace `EXAM_WEIGHT` with BKT blindly — that constant encodes *stakes* (summative > formative), which is orthogonal to BKT's format handling; preserve the stakes distinction.

---

## 9. Honest caveats (n=1, AI-generated) — must be reflected in-app copy, never oversold

- Our "external authority" is LLM-web-retrieved, not an accredited hand-curated framework (QAA/ABET/CanMEDS are real negotiated documents). This is medical-*grade structure*, not medical-*grade validation*.
- No stakeholder panel sets target levels — ours are model-inferred.
- No committee — one LLM grader + Werner; single-rater calibration we can't cross-check.
- Prerequisite edges can't be empirically validated at n=1 — treat them as hypotheses.
- Weighted blueprinting is best-effort at short exam lengths.

---

## 10. Phasing (dependency-ordered; each phase independently deployable + Pi-verifiable)

- **Phase 0 — Objective-id backbone.** Assign stable objective ids in the compiler; preserve across write/revise via the `keepId` mechanism (like lesson ids, §11); add the single `resolve_objectives` resolver and **cut every objective-reader (lessons, exams, mastery) over to it in this phase** — refs-canonical means one master copy with no embedded fallback, so this data-model cutover is atomic (the accepted cost of the single-source-of-truth choice). Ship schemaVersion 3; migrate the 4 live Pi courses via the enrich path on a *copy first*, with the daily content backup verified. No user-visible change. Unblocks everything.
- **Phase 1 — Completeness + outcomes-first compiler.** Stage 0 DEFINE + Stage 2 competency-first derivation + the VERIFY matrix/depth/reachability gate + compile-time blueprint. Fixes the completeness and exam-alignment root causes. Move compile to the background job.
- **Phase 2 — Teaching redesign.** Stage 3 segment chain + worked examples + post-attempt explanations + coverage validators + lazy segment generation.
- **Phase 3 — Placement diagnostic.** Stage 1 (needs the scope skeleton from Phase 1).
- **Phase 4 — Objective-grained evaluation + mastery + metrics.** Stage 4: per-objective BKT awareness layer, roll-up, guessing-correction, FSRS, honest analytics, kill `SESSION_MIN=90`, separate mastery from cadence.

Quick honesty win deployable anytime, independent of the above: **replace the fake 90-minute session with the real per-lesson `estMinutes`** and add measured time-on-task.

---

## 11. Risks & mitigations

Each risk carries a concrete plan, a verification, and an honest status (solved / bounded / accepted).

- **Objective-id preservation across revisions** (the load-bearing risk). **Plan:** reuse the existing explicit `keepId` mechanism (`compiler._resolve_revised_ids`, the revise prompt at compiler.py:393) — each surviving objective names the exact existing id it keeps; new objectives get ids above the max; a validator rejects any `keepId` that doesn't match an existing id. Positional assignment only happens on first compile (no history to lose). **Verify:** a Phase-0 test that revises a course (rename/reorder/insert/delete objectives) and asserts every surviving objective keeps its id and its event/mastery history stays joined. **Status: solved** (reuses a proven pattern).
- **Paid calls + validator-retry on a route that has 502'd.** **Plan:** move compile onto the background-job path (`jobs.py` + live-progress feed, already built and Pi-verified at 567s this session) — removes the HTTP-timeout ceiling entirely (the 502 was the 540s synchronous timeout). The completeness-matrix gate is **deterministic pure code** over the manifest, not a paid call, so it adds negligible time. Diagnostic and per-segment lessons stream/lazy-generate. **Verify:** the live-progress infra already proves the pattern. **Status: solved.**
- **Cold-start diagnostic noise.** **Plan:** asymmetric scoping — only compress an objective on strong, directly-tested evidence (never on imputed), and never fully drop one — so the worst outcome is briefly reviewing something already known (safe), never skipping something needed. **Verify:** a rule/test that scoping never returns "skip" and never compresses on `evidence == imputed`; the completeness gate + "flag not covered" button are backstops. **Status: bounded by design, not eliminated.**
- **Migration blanks historical per-objective mastery.** **Plan:** accept a clean per-objective start (re-accrues as the learner studies); the migration is **additive** — tags new events with objective ids, never rewrites/deletes existing event, mastery, streak, or heatmap data. **Verify:** run on a copy first, daily backup confirmed (2026-07-15 incident rule), assert no existing rows deleted. **Status: accepted, zero data loss.**
- **The completeness gate proves internal consistency, not external completeness** (elevated from §9). It guarantees the objectives cover the competencies *we derived* — not that we derived all the *right* competencies. **Plan/backstops:** ground the DEFINE call in canonical/accreditation sources; the accuracy sweep; and the "flag not covered" escape hatch as the human check (hence it is not optional). **Status: accepted ceiling** — medical-grade structure, not medical-grade validation; must be reflected honestly in-app.

**Cross-cutting:** the dependency-ordered phasing is itself a mitigation (each phase ships and is Pi-verified independently — no big-bang); test-on-a-copy + daily backups guard every migration.

---

## 12. Resolved (Werner, 2026-07-22)

- **Guessing-corrected score:** applied **internally only**; the learner sees a clean 0–100%.
- **FSRS recall signal:** **graded** (answer latency + hint use + retry), not binary.
- **Objective storage:** **single master copy (refs-canonical)** — one registry, one resolver; the Phase-0 cutover is atomic (§10). Chosen over the bridge for single-source-of-truth cleanliness, accepting a larger, more-coupled Phase 0.
