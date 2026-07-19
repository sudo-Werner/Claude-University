# Improvement ideas deep dive — GitHub / Reddit / learning-science sweep

**Date:** 2026-07-19. **Method:** deep-research workflow (104 agents): 5 search angles →
22 sources fetched → 108 claims extracted → top 25 adversarially verified by 3-vote
panels (24 confirmed, 1 refuted). Reddit itself blocks crawling; its practitioner signal
arrived via Anki Forums, HN, and a 9-year Duolingo forum corpus in a peer-reviewed study.

## What our current design gets right (strongest evidence in the field)

- **Retrieval practice + spaced repetition are the two best-evidenced techniques in
  learning science** — the only two rated "high utility" in Dunlosky et al. 2013 (PSPI);
  spaced retrieval beats massed g = 1.01 (0.74 after bias correction, Latimier 2021).
  Our concept checks + SM-2 reviews sit exactly on this base.
- **Condition that matters:** retrieval WITHOUT corrective feedback shows no classroom
  benefit — every check must explain the right answer (ours do; keep it that way).
- **Interleaving (moderate evidence, g ≈ 0.42):** works for discriminable problem TYPES
  (quiz/exam items), weak for expository prose. Apply to Arcade/exam item mixing, not
  lesson reading.
- Real-world caveat: a 2024 classroom study found spaced-retrieval effects smaller in
  authentic settings than lab figures — real but modest gains, not miracles.

## High-value adoptable ideas (ranked by fit for us)

1. **AI-chat guardrails — the single biggest pedagogical risk flagged.** Bastani et al.
   (PNAS 2025, preregistered RCT, ~1000 students): unguarded GPT-4 chat = +48% practice
   scores but **−17% on the subsequent unassisted exam vs. no AI at all**; a guardrailed
   hint-only tutor (never reveals answers, canonical solution injected into the prompt so
   feedback is accurate) eliminated the harm (exam-neutral). We already built Socratic
   co-work as never-reveals, but the DEFAULT lesson side-chat and its behavior during an
   active (unrevealed) exercise need an audit against this exact design: hints-not-answers
   for active items + solution injected for accuracy. Guardrails only *neutralized* harm
   in the RCT — no design yet shown to beat no-AI on exams (open question).
2. **FSRS as SM-2's successor.** The expanding-intervals assumption at SM-2's core has no
   empirical support over uniform spacing (g = 0.034, CI includes zero) — spacing itself
   does the work. Anki ships FSRS opt-in; OpenTutor ships FSRS-only (code-verified).
   FSRS's "30%+ more accurate" marketing figure is unverified — the honest case is
   "modern, optimizable scheduler; SM-2's core assumption is folklore." Open question
   whether the gain is measurable at single-learner scale.
3. **Review heatmap (passive, honest habit UI).** Anki's Review Heatmap add-on pattern:
   GitHub-contribution-style calendar showing past study activity AND future due load in
   one view, streak alongside — no notifications, points, badges. Directly buildable from
   our events table + SRS queue (and we can forecast due load properly, which the add-on
   can't).
4. **Flexible streaks; gamification stays optional.** Mogavi et al. (ACM L@S 2022, 9-year
   Duolingo corpus + interviews): documented "gamification misuse" (XP farming, streak
   anxiety, cheating); most-requested fixes = per-user toggle to disable gamification and
   flexible streak cadence (weekly option for schedule-mismatched learners). Our daily
   streak is rigid; the Arcade has no XP/leagues — keep it that way.
5. **Structured teach-back rubric → misconception profile.** Studyield (code-verified)
   grades Feynman-style explanations into structured JSON: accuracy/clarity/completeness/
   understanding 0-100 + misconceptions + strengths + follow-ups. We already have
   explain-it-back and teach-it-to-Claude; adopting the structured-rubric output (esp.
   the misconceptions field) is a concrete implementation path for the parked
   misconception-profile idea. No validation data exists on AI-graded teach-back vs.
   human judgment — fine for feedback, unproven as a mastery gate.
6. **Highlight → retrieval prompt.** Highlighting is "low utility" as a study technique
   (Dunlosky) — fine as annotation (that's how we scoped it), but a one-tap "turn this
   highlight into a review item / SRS card" converts a low-utility habit into the
   highest-utility one. Dovetails with the parked notes-resurfacing discussion.
7. **Learner-editable tutor memory** (DeepTutor, 27.8k stars): the learner profile is
   visible, editable, and every synthesized claim cites the raw traces below it —
   "nothing in your profile is unaccountable." The right trust model for the
   misconception profile if/when we build it.
8. **Preserve learner authoring** (Skola's stance): the act of creating cards/notes IS
   part of learning (generation effect, self-explanation g ≈ 0.55). Middle path for an
   AI-writes-everything platform: learner writes summaries/cards/explanations, AI
   critiques and extends — not the reverse.
9. **Exam clone** (Studyield): generate practice exams matched to an uploaded past
   paper's style/difficulty. Least applicable to us (no external past papers), but the
   pattern — style-matched assessment generation — could apply to "practice exam in the
   style of this course's real final."

## Do NOT build (folklore / documented harm)

- **Learning-style adaptation** (diagnose visual/auditory learner, match modality): the
  canonical folklore item — APS-commissioned review found no adequate evidence; properly
  designed crossover studies contradict it; consensus held 2008-2024. Varying modality
  for everyone (e.g. video explainers) is fine; per-learner style matching is not.
- **XP / leagues / rigid streak pressure:** documented misuse and abandonment.
- **Cheapest-tier models for grading/feedback:** 11% hallucination rate for the smallest
  tier vs ≤3% for better models in a 2,000-instance eval (2025 preprint, 2-1 verify vote
  — weakest finding here, but directionally consistent). Our grading runs through the
  Max-subscription `claude -p` (Sonnet/Opus-class), so we already comply; the warning
  binds any future "use a cheaper model for grading" cost optimization.

## Refuted in verification (excluded)

- Skola's polish being attributable to skeuomorphic index-card rendering (0-3 vote).

## Open questions the evidence can't answer

1. Does FSRS's accuracy edge hold at single-learner scale with heterogeneous lesson items?
2. What chat-guardrail design produces a *positive* exam effect (vs. merely neutral)?
3. Does AI-graded teach-back correlate with human judgment well enough to gate mastery?
4. Does a passive heatmap + flexible streak measurably sustain solo study vs. no habit UI?

## Sources (22 fetched; key ones)

Dunlosky et al. 2013 PSPI · Pashler et al. 2008/2009 PSPI · Latimier et al. 2021 EPR
meta-analysis · Bastani et al. PNAS 2025 (doi 10.1073/pnas.2422633122) · Mogavi et al.
ACM L@S 2022 (doi 10.1145/3491140.3528274) · arXiv 2508.05952 (LLM tutor hallucination)
· github.com/{zijinz456/OpenTutor, studyield/studyield, HKUDS/DeepTutor, ArtCC/freelingo,
h16nning/skola, glutanimate/review-heatmap, open-spaced-repetition/awesome-fsrs} ·
Anki Forums FSRS debate · Wharton Knowledge (chess-club RCT summary).
