# Deep dive: creatively using Claude DURING lessons

**Date:** 2026-07-16 (overnight). **For:** Werner's morning review. **Status:** proposal only — nothing here is built; each item is a fork you pick.

## Where Claude already works during a lesson

Generation (grounded + audited), deepen, pre-quiz, answer grading, explain-it-back with a
metacognitive follow-up, guided-first side-chat (web-search enabled), capstones, library,
exams, gap reviews. That is a lot of Claude *around* the lesson. The pattern across all of
it: Claude writes artifacts, the learner consumes them. The untapped space is Claude as a
**live participant while you think** — the tutor in the room, not the author of the packet.
That is also the one thing a real university has that no textbook does: a human who responds
to *your* half-formed attempt in the moment.

## The ideas, ranked

Each: what it is, the science, why Claude specifically, cost on the Pi (every non-streamed
call is ~60–90s; streamed chat feels live), and my recommendation.

### 1. Socratic co-work on the exercise (the charter's own vision)

Today the exercise is static: read prompt, type answer, check. Instead, an optional "Work
through it with Claude" mode: you commit to a first step in chat, Claude responds to *that
step* — confirms, asks the next Socratic question, or surfaces the misconception — until you
reach the answer yourself. The existing side-chat already streams and already has
guided-first rules; this is a dedicated mode of it scoped to the exercise, with the lesson's
solution and grader notes in the system prompt.
**Science:** process-level feedback beats outcome feedback (Hattie & Timperley); tutoring is
the 2-sigma benchmark this whole platform chases (Bloom 1984).
**Cost:** streamed chat only — no new generation calls. **Effort:** M.
**Recommendation: build first.** It is the highest-fidelity "real tutor" experience per token
spent, and the charter names Socratic questioning explicitly.

### 2. Fresh retrieval items for reviews (fix the weakest pedagogy link)

SRS reviews currently re-present the SAME exercise — after two or three reviews you are
recalling the answer string, not the concept (answer memorization defeats the testing
effect). Claude should generate 1–2 *fresh* retrieval questions per due lesson from its
objectives + spine entry — same machinery as exam generation, tiny scope. Cache per review
session; grade like checks.
**Science:** retrieval practice with varied items is the strongest single finding in learning
science (Roediger & Karpicke); identical-item re-testing decays fast.
**Cost:** one small generation call per review session (batchable across due lessons).
**Effort:** M. **Recommendation: build early** — it upgrades the pillar the platform is built on.

### 3. Teach-it-to-Claude (protégé effect)

A mode where Claude plays a curious, slightly-confused student and you TEACH the lesson's
concept: it asks naive questions, makes the classic mistake, and you correct it. At the end,
the existing explain-grading pipeline scores how well you taught.
**Science:** learning-by-teaching / protégé effect (Chase et al., Betty's Brain): learners
work harder and monitor their own understanding better when teaching an agent.
**Cost:** streamed chat + one grading call. **Effort:** M.
**Recommendation: build second.** It is explain-it-back with 10x the engagement, and it is a
thing only a live model can do.

### 4. Text viva voce — the oral exam

A conversational examination: Claude probes one module conversationally, follows up on weak
answers ("you said X — what happens when Y?"), adapts depth to your responses, then renders a
verdict against the objectives with the exam grader. Universities use vivas precisely where
MCQs fail: probing the EDGE of understanding.
**Science:** adaptive questioning samples understanding far more efficiently than fixed items
(that is why PhD defenses are oral).
**Cost:** a streamed conversation + one grading call. **Effort:** L (needs its own screen,
rubric prompt, and result semantics — does it feed exam_status or stay formative?).
**Recommendation: WERNER-DECIDE.** Authentic and impressive, but it is a new assessment
surface with real design questions (does a viva count toward passing?).

### 5. Prior-knowledge activation at lesson start

Before a lesson first generates, one free-text question: "What do you already know or
suspect about <topic>?" Your answer is injected into the generation prompt (the profile and
performance summary already are). The lesson then genuinely builds on YOUR starting point —
the thing no university lecture can do for each student.
**Science:** prior-knowledge activation (Ausubel's "the most important single factor");
pairs with the existing pre-quiz (which stays objective).
**Cost:** zero extra calls — it rides the existing generation. **Effort:** S.
**Recommendation: build** — cheapest personalization win available.

### 6. Per-concept "explain differently" (analogy on tap)

"Rusty on this?" today regenerates the WHOLE lesson (~2 min). Add per-concept: select/tap a
spine term → Claude gives a 2-paragraph alternative angle (analogy or contrast) streamed
into the workspace chat, using the learner profile for the analogy domain.
**Science:** multiple representations / new-angle re-explanation (same Bloom corrective logic
the gap review uses, applied mid-lesson).
**Cost:** streamed chat call. **Effort:** S–M. **Recommendation: build.**

### 7. Misconception profile (the AI office-hours summary)

The events DB already stores every wrong check, wrong exam answer with its objective, and
every explain verdict. A "Where I go wrong" view: Claude reads your error history for a
course and writes a short, specific diagnosis ("you consistently invert cause/effect in
monetary policy questions") with counter-examples.
**Science:** error-pattern feedback; formative assessment (Black & Wiliam).
**Cost:** one generation call, cacheable until new errors. **Effort:** M.
**Recommendation: WERNER-DECIDE** — genuinely novel, but only worth it once enough error
data exists (you would see its value after a few exams).

### 8. Mid-lesson production checkpoints (already deferred)

The Claude-for-Teachers borrow: small "do it now" production tasks INSIDE the lesson body,
not just checks at the end. Deferred to its own sub-project earlier tonight — listed here
for completeness, unchanged recommendation (own spec later).

## What I would NOT do (YAGNI, per charter)

Voice anything (Pi + latency + charter's audio slice E is separate); avatar/personality
theming; multi-agent debates as a gimmick; always-on proactive interruptions while reading
(respect flow); gamified anything.

## Suggested order if you approve the direction

1 (Socratic co-work) → 2 (fresh review items) → 5 (prior-knowledge activation) → 6 (analogy
on tap) → 3 (teach-it-to-Claude) → then decide 4 and 7 after living with the first wave.
Items 2 and 5 also answer gaps the overnight pedagogy audit flagged independently.

None of this is built. Pick any subset — each becomes a normal brainstorm→spec→plan cycle.
