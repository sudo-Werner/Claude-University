# Claude University — persona brainstorm sheet

**Date:** 2026-07-22. **Purpose:** raw material for a proper brainstorm. Part 1 collects every
idea raised in this conversation (status-tagged against the live system). Parts 2 and 3 rerun
the same exercise through two new personas: a PhD student and a lecturer. Nothing here is a
commitment — per CHARTER-PHASE-2, new ideas land in the todo's "proposed" section only after
they survive discussion.

Status tags: **[SHIPPED]** live on the Pi · **[BACKLOG]** already in tasks/todo.md ·
**[PROPOSED]** raised this conversation, new.

---

## Part 1 — The curious student (everything raised so far)

### Foundations (from the opening conversation — largely what Phase 1 built)

1. **Socratic tutor over content delivery** — AI as the questioner, not the lecturer; the
   2-sigma tutoring bet. [SHIPPED — Socratic co-work, guided-first chat]
2. **Constant retrieval through dialogue** — the AI tests, the learner produces; materials
   teach, AI verifies. [SHIPPED — checks, explain-it-back, reviews]
3. **Protect productive struggle** — hints not answers near active items. [SHIPPED — PNAS
   guardrails, Tier 1 item 1]
4. **Backward curriculum design** — derive the skill tree from "what I want to be able to do,"
   re-plan as reality arrives. [SHIPPED in part — course creation; re-planning is lighter]
5. **The coach against quitting** — the real failure mode of self-study is dropout, not bad
   pedagogy. [SHIPPED in part — heatmap, flexible streak; see also #21 Advisor]

### Open backlog calls (my votes from the repo review)

6. **Token streaming** — biggest felt-latency lever for the 30–90s wait. [BACKLOG Tier 2 #10 —
   vote: build; composes with #15 Night shift]
7. **Viva mode, formative-only** — conversational module exam feeding the misconception
   profile, never gating exam_status; item 7's rubric is its engine. [BACKLOG Tier 2 #11 —
   vote: approve as formative]
8. **FSRS** — decline consciously; unproven at n=1, SM-2's flaw is theoretical. [BACKLOG
   Tier 2 #6 — vote: close as declined]
9. **Houston contention, cheap fix** — systemd MemoryMax cap + swap; the only open item that
   actively breaks generation. [BACKLOG Tier 2 #12 — vote: do the 20-minute version now]
10. **Interleaved review sessions** — shuffle due items across courses/modules into one mixed
    queue; interleaving's evidence (g ≈ 0.42) is exactly for discriminable item types.
    [PROPOSED]
11. **Confidence calibration on checks** — one-tap sure / think-so / guessing before reveal;
    track calibration over time ("overconfident on X-type items"). Zero Claude calls.
    [PROPOSED]
12. **Real external readings** — occasionally assign an actual chapter/paper from the Library's
    real sources and have Claude examine you on it; keeps "materials teach, AI verifies"
    honest. [PROPOSED]

### Outside the box

13. **Assignments grounded in your actual life** — exercises built from your real repos and
    trading data on the same Pi; deletes the transfer gap. Only a university of one can do
    this. [PROPOSED — top pick]
14. **Spot-the-flaw lessons** — Claude deliberately writes a subtly wrong explanation; you find
    the error. Erroneous-example/refutation-text evidence; trains calibrated distrust of AI.
    [PROPOSED]
15. **Grade your past self** — resurface your own months-old explain-back verbatim and critique
    it. Spaced retrieval + calibration + visceral progress; data already in the event log.
    [PROPOSED — top pick]
16. **Knowledge-rot detection** — idle-hours job re-checks completed lessons against fresh
    search; "what you learned in March has been revised." A degree with a changelog.
    [PROPOSED]
17. **The night shift** — nightly job pre-generates tomorrow's due-review items and likely next
    lesson; wait becomes zero, paid calls batch into one predictable window. [PROPOSED]
18. **Learner-authored textbook as graduation** — compile explain-backs, notes, corrected
    misconceptions into a book the learner wrote; Claude as editor only. Charter principle 4
    at full strength. [PROPOSED]

### The curious-student wishes

19. **Questions become the university** — one-tap capture of mid-lesson tangent questions as
    first-class objects; the curriculum later grows lessons from them, your question quoted at
    the top. The course you finish ≠ the course that was planned. [PROPOSED — top pick]
20. **Taken to the edge** — every course ends at the frontier: live disagreements, open
    problems, recent real papers — not just "mastered." [PROPOSED]
21. **Seminar mode** — assignment is a real primary text; Claude is the sharp seminar partner
    who read it too: challenges your reading, defends wrong interpretations, makes you point
    at the passage. [PROPOSED]
22. **The map, not the dashboard** — the field drawn as an atlas: mastered regions lit,
    decaying regions dimming (SRS knows), adjacent unexplored territory in outline, frontier
    dark. Spine data is the raw material. [PROPOSED]
23. **An advisor, with a calendar** — monthly/termly "advisor meeting": reviews the event log,
    says one hard true thing, asks what pulled at you, proposes next term's shape, grants
    permission to drop dead courses. One scheduled call per month. [PROPOSED — top pick]

---

## Part 2 — The PhD student

A different job entirely: not absorbing settled knowledge but producing original knowledge.
The unit of work stops being the lesson and becomes **the research question**. Everything below
follows from that shift.

### What they'd want

1. **A living literature review** — a managed corpus, not a search box. New-paper triage on a
   schedule: "three preprints this week touch your question; this one threatens assumption X."
   The lit review is never 'done'; the system keeps it alive.
2. **Research-question sharpening** — Socratic narrowing from "I'm interested in Y" to a
   defensible, answerable, novel question; repeated stress-testing of scope ("what result
   would make this thesis fail?").
3. **Reviewer-2 mode** — adversarial review of drafts and experimental designs *before*
   humans see them: attacks the methodology, the stats, the novelty claim, the missing
   citations. The spot-the-flaw idea turned outward onto your own work.
4. **Just-in-time methods tutor** — the coursework a PhD actually needs arrives scoped to the
   live study: "you're about to run a mixed-effects model; here is the 40-minute course on
   exactly that, with your own data as the exercise." (Part 1 #13, specialized.)
5. **The research logbook with memory** — every dead end, abandoned approach, and pilot result
   captured; answerable months later: "why did we abandon approach X in March?" The event-log
   philosophy applied to research.
6. **Writing partner with integrity boundaries** — critiques argument structure, flags
   unsupported leaps, never ghostwrites. The learner-produces principle is an *ethical*
   requirement here, not just pedagogy.
7. **Citation audit** — verify that every citation in your draft actually says what you claim
   it says. Cheap, mechanical, catches the most embarrassing failure class in academia.
8. **Defense rehearsal** — the viva idea at full strength: adaptive mock defense probing the
   weakest chapter, follow-ups on hedged answers, verdict against your own claims.
9. **The "so what" drill** — periodically articulate the contribution to three audiences
   (examiner, adjacent-field colleague, layperson); the system tracks whether the story is
   converging.
10. **Anti-isolation cadence** — the PhD's real killer is despair, not difficulty. Weekly
    check-ins on progress *and* morale; the advisor-meeting idea (Part 1 #23) with higher
    stakes.
11. **Frontier watch** — who else is working on this, what got published where, am I about to
    be scooped; knowledge-rot detection (Part 1 #16) pointed at a thesis instead of a lesson.
12. **The untaught skills as side-quests** — reviewing papers, giving talks, writing grants:
    the professional curriculum no program teaches, delivered as short courses when the need
    arises.

### How it would look

Not a lesson player — a **workbench**. Three panes of state that persist for years: the corpus
(papers, annotations, triage), the logbook (experiments, dead ends, decisions), and the drafts
(chapters under adversarial review). The AI is a colleague present in all three, and "progress"
is not a completion bar but the thesis's claim-tree slowly turning from conjecture-red to
evidence-green. The atlas idea survives, but the map is of *your argument*, not of a field.

---

## Part 3 — The lecturer

The inversion: this persona's output is other people's learning. They want leverage over their
scarcest resource — human contact time — and they want to remain unambiguously the author of
their course. (This is also the persona that turns Claude University from a product-of-one
into a product, if that ever tempts you.)

### What they'd want

1. **Course-authoring copilot, lecturer as editor-in-chief** — first-draft syllabi, lessons,
   problem sets generated from *their* materials and stance; every artifact approved before a
   student sees it. Authorship is non-negotiable — the system drafts, the lecturer decides.
2. **Misconception radar across the class** — the misconception profile aggregated: "40% of
   the cohort inverts cause and effect on monetary policy." Tells the lecturer what Tuesday's
   lecture must re-teach. The single highest-value item for teaching quality.
3. **Confusion hotspots per lecture** — where students' questions and wrong checks cluster,
   mapped back to the minute/concept in the material that caused them. Closes the feedback
   loop lectures have never had.
4. **Infinite isomorphic question variants** — assessment items regenerated per student from
   the same template: kills answer-sharing without surveillance, and enables mastery-based
   retakes.
5. **Rubric-faithful grading assistant** — first-pass grading with the canonical rubric
   in-prompt, uncertainty flagged for human review; the lecturer grades the hard 15%, audits
   the rest. (The 11%-hallucination warning binds: never the cheapest model.)
6. **Office-hours triage** — the guardrailed tutor absorbs the repeated 80% of questions;
   escalates the interesting 20% to the human *with context* ("she's asking about X because
   she missed Y in week 2").
7. **Per-student briefings before contact time** — thirty seconds per name before a tutorial:
   current mastery, recent struggles, the one thing worth asking them about. Makes small human
   moments count.
8. **Syllabus rot detection** — Part 1 #16 pointed at the lecturer's own course: which
   readings are superseded, which figures revised, which examples aged badly. Run it every
   term break.
9. **Assessment redesign for the AI era** — help converting take-home essays into formats that
   survive ubiquitous AI: process portfolios, in-class production, orals (the viva machinery,
   productized).
10. **Rehearsal against a simulated struggling student** — teach-it-to-Claude inverted: the
    lecturer explains a hard concept to a model playing a genuinely confused student, and
    finds the holes before the real lecture does.

### How it would look

A **cockpit**, not a course player: one screen showing the class as a living map (the atlas,
aggregated — which regions the *cohort* has lit up, where it's dark), a queue of drafts
awaiting approval, a queue of escalated student questions, and the misconception radar. The
design rule that carries over from Werner's charter: the AI never says anything to a student
that the lecturer hasn't sanctioned in kind — guardrails become an institutional promise
instead of a personal one.

---

## Cross-persona observations (brainstorm fuel)

- **The same five machines serve all three personas:** the guardrailed tutor, the misconception
  rubric, the SRS/event log, the sources/Library engine, and the viva. Personas differ in
  *where the machines point* — at a lesson, at a thesis, at a cohort.
- **The advisor/anti-isolation idea recurs in every persona** (student #23, PhD #10, lecturer's
  per-student briefings). Whatever else gets built, the "someone is keeping company with your
  long-term trajectory" layer looks like the universal missing piece.
- **Authorship boundaries move with the persona:** student — AI authors lessons, learner
  authors understanding; PhD — AI may author *nothing* visible in the thesis; lecturer — AI
  drafts everything, human signs everything. Worth writing down as a design axis.
- **The atlas reappears three times** (field map, claim-tree, cohort map). One rendering
  engine, three data sources.
