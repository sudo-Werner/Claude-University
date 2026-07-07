# Toward Real Education — Research Synthesis

**Date:** 2026-07-07
**Purpose:** Ground the "make Claude University a real education" program (sub-projects A–E) in
what real education systems do and what the learning-science evidence actually supports. Feeds the
sub-project A spec (richer intake → grounded curriculum → learning objectives) and everything after.
**Method:** four parallel web-grounded research threads (curriculum design; mastery/assessment
science; real online-university mechanics; university-equivalence standards). Sources listed at the end.

---

## 0. The North Star (the reframe)

Do **not** build on Bloom's "2 sigma." That figure does not replicate — modern re-analysis (VanLehn
2011) shows it was largely an artifact of holding tutored students to a higher mastery bar plus extra
time. Realistic ceilings: good tutoring / tutoring-software ~0.5–0.8 SD; mastery learning ~0.4–0.6 SD.
Any "2-sigma from AI" claim is marketing.

The defensible goal is not a magic multiplier. It is: **relentlessly enforce the handful of mechanisms
that actually replicate, and meet the concrete, measurable standards that define "university-level."**
A one-learner AI tutor's real edge is that it can do the things a fixed textbook can't — always enforce
mastery before advancing, always make the learner retrieve, space and interleave review, and reteach a
missed concept in a *different representation* on demand.

---

## 1. What the evidence actually supports (ranked)

**Tier 1 — strongest, most replicated (build the system on these):**
- **Retrieval practice / the testing effect** — being tested produces far better long-term retention
  than re-reading. Roediger & Karpicke (2006); Karpicke & Roediger (2008, *Science*): after a delay,
  extra *studying* added ~nothing while repeated *testing* drove large retention gains. The single
  highest-ROI lever, and trivial for an LLM to generate. → Every lesson ends in active recall; every
  review re-tests, never re-summarizes.
- **Spaced / distributed practice** — Cepeda et al. (2006, 317 experiments); 2025 classroom
  meta-analysis d≈0.54. Spacing beats massing; optimal gap grows with target retention. → Needs
  persistent per-concept mastery + last-seen tracking and a resurfacing scheduler.
- **Formative assessment + specific feedback** — Black & Wiliam (1998) d≈0.4–0.7, disproportionately
  helping strugglers. Feedback quality matters; vague/ego feedback can be null or harmful. → Feedback
  must be specific, task-focused, actionable — not a bare score or praise.

**Tier 2 — solid, moderate, measurement-dependent:**
- **Mastery learning** (Bloom/Guskey; Kulik et al. 1990 d≈0.4–0.52; Slavin 1990 only 0.27 on
  standardized tests — a real, unresolved dispute). Works, moderately; effect depends on outcome
  measure and mastery stringency (~80–90% threshold common).
- **Keller's PSI** (self-paced, mastery-gated units, must-pass-to-proceed) — well-evidenced course
  structure (d≈0.42–0.49; retention persists). Maps almost perfectly onto software delivery.
- **Competency-Based Education / WGU** — progression gated on demonstrated competency, not seat time;
  "direct assessment" by expert evaluators; no letter grades, pass-or-not. Coherent mastery gating at
  scale (but much of its outcome evidence is institutional).
- **Corrective remediation done right** — on a failed check, reteach the *specific* sub-concept in a
  *different* representation (new analogy/modality/worked example), then re-assess before unlocking.
  This is the one thing a static textbook can't do; our existing "deepen" feature already gestures at it.

**Design standard (near-universal in higher ed):**
- **Backward design** (Wiggins & McTighe): desired results → evidence/assessment → activities. Never
  write a lesson before its objective and its assessment exist.
- **Constructive alignment** (Biggs): the verb in the objective ("analyze", "design") must be *activated*
  in the activity and *verified* in the assessment. An "apply" objective tested by a recall MCQ is the
  core failure mode.
- **Measurable objectives**: one observable action verb + object + criterion, tagged to a revised
  Bloom cell (Remember→Understand→Apply→Analyze→Evaluate→Create × Factual/Conceptual/Procedural/
  Metacognitive). The words *understand / know / appreciate / be aware of* are banned — not assessable.
- **Prerequisite graph → topological sequencing → graph-driven remediation**: model the course as
  concept-nodes with prerequisite edges; sequence by topological order; on a downstream failure walk
  *upstream* to find the real gap. Auto-generated prerequisites are drafts to verify, not ground truth.
- **Ground the outline in the discipline's canonical body of knowledge** — named textbooks, published
  syllabi, professional-society guidelines (ACM/IEEE, ABET, etc.) — not the model's free association.
  This is the single biggest lever against "mile-wide, inch-deep" ad-hoc topic lists.

**Myth — do NOT build around it:**
- **Learning styles (VAK / "teach to the learner's style")** is debunked (Pashler et al. 2008; APA
  2023). Personalize on **prior knowledge, pace, goals, and prerequisite gaps** — never on sensory
  "style." (This is also why the podcast idea should be justified by time-shifting + repetition, not
  "auditory learner.")

---

## 2. University-equivalence spec checklist (the "like-for-like" question)

Each spec is measurable and grounded in a real standard. Bottom line: you can make the *content,
workload, depth, and assessment* like-for-like; you **cannot** make the *credential* like-for-like —
that requires an accredited institution. Frame outputs as "university-*level learning*," never a "degree."

**Workload (US 34 CFR 600.2 credit-hour ≈45 hrs/credit; ECTS 25–30 hrs/credit; both converge):**
1. **125–150 hours of total learning effort per course** — stated and structured to plausibly fill it.
2. **Per-lesson/module learning-hour breakdown** (~1:2 instruction-to-independent-work), so the total is
   auditable, not asserted. *Caveat: hours are a proxy for learning, not the target (Carnegie Foundation
   itself now says seat-time is inadequate). Depth + aligned assessment are what actually make it rigorous.*

**Outcomes & alignment (Biggs; accreditor "measurable, assessed outcomes"):**
3. **Every course + module states measurable outcomes as assessable verbs.** No outcome without a
   testable verb.
4. **Assessment is constructively aligned to each outcome at the matching Bloom level** — an "analyze"
   outcome tested by an analysis task, each item mapped to outcome + tier.

**Depth & level (Dublin Descriptors / QF-EHEA; UK FHEQ 4/5/6; Lumina DQP):**
5. **Declared level with matching cognitive depth** — degree-level goes beyond textbook recall to
   independent judgement (evaluate evidence/arguments/assumptions) and touches the field's forefront.
6. **Rising learner autonomy** — tasks demand independent data-gathering/method-application, not just
   following steps.
7. **Depth *and* integration** — deep specialized knowledge plus explicit cross-links to related
   fields/prior courses, not siloed topic dumps.

**Rigor, assessment & integrity (HLC/MSCHE accreditation; summative-assessment standard):**
8. **Curriculum rigor and coherence** — logical prerequisite order, no gaps, broad survey + deep core.
9. **Terminal summative assessment against a defined pass standard** — project/exam/authentic task with
   an explicit threshold and rubric, certifying the stated outcomes.
10. **Assessment data closes the loop** — outcomes actually measured and recorded (for one learner,
    their own results *are* the data).
11. **Expert/authoritative grounding** — content accurate to the field's current state and traceable to
    authoritative sources (the analogue of "qualified faculty").
12. **Core transferable skills built and assessed** — written communication, critical analysis,
    quantitative reasoning (where relevant), information literacy.
13. **Academic-integrity safeguard on the certifying assessment** — mostly moot for one self-directed
    learner (no one to cheat against; the assessment's value is honest self-check).

**Honest hard limits (the professor/PhD bar):**
- **The credential.** Accreditation is granted to *institutions* by recognized accreditors. A
  self-hosted one-learner system can replicate learning, not a degree. Say so plainly in the UI.
- **Expert correctness (spec 11) is only partially closable.** An LLM is not a certified subject-matter
  expert and can be *confidently wrong* — the thing an expert catches instantly. Internal consistency
  (already shipped) ≠ factual correctness to the field. Mitigation: primary-source grounding, explicit
  treatment of uncertainty/debate, flagging confidence, harder assessment, and plausibly a
  **factual-rigor verification pass** (a correctness cousin of the consistency pass). Narrows, never
  fully closes, the gap.

---

## 3. Operational patterns from real platforms (what to copy / drop)

**Copy (fits a solo AI tutor):**
- **Course-page contract (Coursera):** every course states "What you'll learn" (outcomes), "Skills
  you'll gain," difficulty, estimated time, module list w/ per-item time budgets, credential. Generated
  up front; sets expectations. Cheap, high-value.
- **Diagnostic placement (Duolingo) + no-stakes readiness check (WGU):** offer "start from scratch" or a
  short diagnostic that *places* the learner / reports readiness, so known material is skipped. LLM
  generates + scores it trivially. This is the heart of the "richer intake."
- **Mastery levels with points (Khan):** Attempted → Familiar → Proficient → Mastered, *level-down on
  misses*, plus a spaced gate on review challenges (Khan: ≥Familiar on 3 skills + ≥Proficient on 1 +
  >12h since last). Legible progress model that drives spacing.
- **Two-tier assessment (WGU):** objective (auto-graded MCQ, lower-order) + performance (learner produces
  an artifact, rubric-graded — natural fit for the LLM rubric grading already shipped).
- **Weighted grading + explicit pass threshold (edX):** assignment weights + minimum-to-pass (~70%).
- **Structured achievement record (Open Badges / CLR, 1EdTech):** model completion as an assertion with
  criteria + evidence + date — the lightweight transcript analog, not accreditation.
- **Specialization → Capstone shape (Coursera):** ordered units ending in a consolidating project
  (already shipped as the capstone feature).

**Drop (assumes scale/institutions we don't have):**
- **Peer review / peer grading** — impossible with one learner; the natural replacement is exactly what
  Coursera is now shifting to: **AI rubric grading** of the learner's artifacts.
- Marketplace / multi-instructor catalog, cohorts, proctoring, identity-verified certificates, formal
  credit/accreditation. No one to cheat; nothing to proctor.

**Key architectural insight (shapes sub-project D):** Duolingo uses a **fixed lesson sequence with
adaptive content *within* each lesson**, not full path regeneration. That's the cleaner design — a fixed
generated skeleton keeps mastery tracking and gating tractable while difficulty/remediation adapt
underneath. Fully regenerating the sequence per interaction makes progress impossible to reason about.

---

## 4. How this reshapes the program (sub-projects A–E)

- **A — Program backbone (intake → grounded curriculum → objectives).** Becomes backward design in
  software: intake as Stage-1 elicitation (goal/transfer wanted, prior knowledge, why) **plus an optional
  diagnostic placement**; outline **grounded in canonical sources** and represented as a **prerequisite
  graph**; every lesson emits **measurable, Bloom-tagged objectives** rolled up to module/course
  outcomes; the course carries the **course-page contract** (outcomes, skills, declared level, target
  hours). Specs 1–8, 11 land here. This is the foundation.
- **B — Knowledge spine (cross-lesson coherence).** Lessons generated with memory of what prior lessons
  established, aligned to their objectives — the across-lessons version of the consistency pass. Serves
  specs 7–8 (integration, coherence) and the expert-rigor bar.
- **C — Aligned assessment.** Constructive alignment enforced at generation (assessment verb = objective
  verb); two-tier (objective + rubric-graded performance artifact); Bloom-ladder rigor; terminal
  summative assessment with a pass standard. Specs 3–4, 9, 12. **Retrieval practice is the spine here.**
- **D — Mastery loop (gating + remediation + transcript + review engine).** CBE-style gating on
  demonstrated objectives; failed check → graph-driven, *different-representation* remediation → re-assess
  → unlock; the **spaced-retrieval review engine** (persistent per-concept mastery + scheduler);
  structured achievement record. Fixed-skeleton-adaptive-within architecture. Specs 5–6, 9–10, 13.
- **E — Audio/podcast lectures (parallel track).** Justified by time-shifting + repetition (not learning
  style); designed as the lecture/review layer that *feeds* the active retrieval loop, never replaces it.
  Script generation is free (Claude); TTS is a quality-vs-cost-vs-privacy fork (cloud API = metered $ +
  external dependency vs. local Pi TTS = free/private but lower quality) — decide with a spike.

**Cross-cutting:** a possible **factual-rigor verification pass** (correctness cousin of the consistency
pass) to narrow the expert-correctness gap; and honest UI framing ("university-level learning," not a
degree; flag uncertainty rather than assert confidently).

---

## 5. Sources

**Curriculum design & objectives**
- Wiggins & McTighe, *Understanding by Design* (2005) — https://andymatuschak.org/files/papers/Wiggins,%20McTighe%20-%202005%20-%20Understanding%20by%20design.pdf
- UbD framework (peer-reviewed, PMC) — https://pmc.ncbi.nlm.nih.gov/articles/PMC1885909/
- Constructive alignment (Biggs, overview) — https://en.wikipedia.org/wiki/Constructive_alignment
- Krathwohl (2002), Revised Bloom's Taxonomy overview — https://cmapspublic2.ihmc.us/rid=1Q2PTM7HL-26LTFBX-9YN8/Krathwohl%202002.pdf
- Writing measurable objectives (UIC CATE) — https://teaching.uic.edu/cate-teaching-guides/syllabus-course-design/learning-objectives/
- How to Write Well-Defined Learning Objectives (PMC/NIH) — https://pmc.ncbi.nlm.nih.gov/articles/PMC5944406/
- Mapping Course Objectives to Program Outcomes (U. Missouri) — https://provost.missouri.edu/programs-centers/program-assessments/assessment-of-student-learning/mapping-course-objectives-to-program-outcomes/
- ABET Criteria 2025–26 — https://www.abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-engineering-programs-2025-2026/
- Knowledge graphs for concept prerequisites (Springer, 2019) — https://slejournal.springeropen.com/articles/10.1186/s40561-019-0104-3
- ACE: AI-Assisted Construction of Educational Knowledge Graphs (JEDM) — https://jedm.educationaldatamining.org/index.php/JEDM/article/view/737
- Bruner spiral curriculum / coherence (Cambridge Assessment) — https://www.cambridgeassessment.org.uk/Images/598388-perspectives-on-curriculum-design-comparing-the-spiral-and-the-network-models.pdf

**Mastery, assessment & the evidence base**
- Bloom (1984), *The 2 Sigma Problem* — https://journals.sagepub.com/doi/10.3102/0013189X013006004
- Nintil systematic review (mastery/tutoring/VanLehn) — https://nintil.com/bloom-sigma/
- Kulik, Kulik & Bangert-Drowns (1990), Mastery Learning meta-analysis — https://journals.sagepub.com/doi/10.3102/00346543060002265
- Guskey, *Mastery Learning* + correctives — https://tguskey.com/wp-content/uploads/Mastery-Learning-1-Mastery-Learning.pdf , https://files.eric.ed.gov/fulltext/ED523991.pdf
- Roediger & Karpicke (2006), Power of Testing Memory — https://journals.sagepub.com/doi/10.1111/j.1467-9280.2006.01693.x
- Karpicke & Roediger (2008, *Science*) — https://web.mit.edu/jbelcher/www/learner/retrieval.pdf
- Cepeda et al. (2006), Distributed Practice — https://augmentingcognition.com/assets/Cepeda2006.pdf
- Distributed practice classroom meta-analysis (2025) — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12189222/
- Black & Wiliam (1998), Formative Assessment — https://fairtest.org/value-formative-assessment-pdf/
- Jonsson & Svingby (2007), Scoring rubrics — https://www.sciencedirect.com/science/article/abs/pii/S1747938X07000188
- Messick (1995), Validity — https://people.bath.ac.uk/edspd/Weblinks/MA_Ass/Resources/Quality%20issues/Messick%201995%20AP.pdf
- Competency-Based Education, Put to the Test (WGU, Education Next) — https://www.educationnext.org/competency-based-education-put-to-the-test-western-governors-university-learning-assessment/

**Online-university mechanics**
- How edX works — https://www.edx.org/how-it-works ; grading — https://edx.readthedocs.io/projects/edx-partner-course-staff/en/latest/student_progress/course_grades.html
- Coursera course-page example — https://www.coursera.org/learn/react-capstone-project ; AI grading — https://blog.coursera.org/ai-grading-in-peer-reviews-enhancing-courseras-learning-experience-with-faster-high-quality-feedback/
- Khan Academy mastery levels — https://support.khanacademy.org/hc/en-us/articles/5548760867853--How-do-Khan-Academy-s-Mastery-levels-work ; Mastery Challenges — https://support.khanacademy.org/hc/en-us/articles/360037494231-What-are-Mastery-Challenges
- WGU assessment policies — https://cm.wgu.edu/t5/WGU-Student-Policy-Handbook/Assessment-Policies/ta-p/133
- Duolingo ML assessment (Settles et al., TACL) — https://research.duolingo.com/papers/settles.tacl20.pdf
- Open Badges v3.0 (1EdTech) — https://www.imsglobal.org/spec/ob/v3p0 ; CLR — https://www.1edtech.org/clr/faq

**University-equivalence standards**
- Federal credit-hour guidance (GEN-11-06) — https://fsapartners.ed.gov/sites/default/files/attachments/dpcletters/GEN1106.pdf
- Carnegie Unit FAQ — https://www.carnegiefoundation.org/about/faqs/the-carnegie-unit/
- ECTS (European Education Area) — https://education.ec.europa.eu/education-levels/higher-education/inclusive-and-connected-higher-education/european-credit-transfer-and-accumulation-system
- Dublin Descriptors / QF-EHEA (2005) — https://ehea.info/media.ehea.info/file/WG_Frameworks_qualification/71/0/050218_QF_EHEA_580710.pdf
- UK FHEQ (2024, QAA) — https://www.qaa.ac.uk/docs/qaa/quality-code/the-frameworks-for-higher-education-qualifications-of-uk-degree-awarding-bodies-2024.pdf
- Degree Qualifications Profile (Lumina) — https://www.luminafoundation.org/files/resources/dqp.pdf
- HLC Criteria for Accreditation — https://www.hlcommission.org/accreditation/policies/criteria/
- MSCHE Standards (14th ed.) — https://www.msche.org/standards/fourteenth-edition/

**Debunked**
- Pashler et al. (2008), Learning Styles: Concepts and Evidence — https://www.apa.org/pubs/journals/features/edu-a0037478.pdf
- APA (2023), Learning Style Myth — https://www.apa.org/pubs/journals/releases/edu-edu0000366.pdf
