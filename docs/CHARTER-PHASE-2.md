# Claude University — Phase 2 Charter: Evidence-Driven Refinement

**Established:** 2026-07-19 (Werner's directive: "make a solid charter and todo list with the
findings, I'll get sonnet to review and implement").
**Status:** Active. Phase 1 (the original [CHARTER.md](CHARTER.md) + [ROADMAP.md](ROADMAP.md))
is complete — all 8 slices plus the feedback waves shipped. Phase 2 refines the live system
using verified evidence instead of intuition.

## What Phase 2 is

Phase 1 built the university. Phase 2 makes it *teach better and feel better*, guided by two
verified evidence bases produced on 2026-07-19:

1. **The project sweep** (2026-07-18/19): a code/charter/test/UX audit of the live system,
   every actionable claim firsthand-verified. Findings live in `.superpowers/sdd/progress.md`
   and the shipped audit-quickwins spec.
2. **The research deep dive**: [research/2026-07-19-improvement-ideas-deep-dive.md](research/2026-07-19-improvement-ideas-deep-dive.md)
   — 104-agent GitHub/Reddit/learning-science sweep, 22 sources, claims adversarially
   verified 3-0 or better unless noted. Cite it before re-litigating any of its calls.

The work items live in [../tasks/todo.md](../tasks/todo.md), tiered by approval status.

## Operating principles (binding on every implementing session)

1. **Evidence over intuition.** Every pedagogy-affecting change must trace to a finding in
   the research doc or a Werner request. If a new idea has no evidence, it goes to the todo's
   "proposed" section for Werner, not into code.
2. **Protect learning from the AI.** The single most important research finding (PNAS 2025
   RCT): unguarded AI help produces *worse* unassisted performance. Any surface where Claude
   talks to the learner near an active exercise/check/exam must coach with hints, never
   reveal answers, and must receive the canonical solution in its prompt so its feedback is
   accurate. New chat-adjacent features inherit this rule by default.
3. **Honest habit UX, never dark patterns.** Passive and truthful surfaces (heatmap, streak)
   over pressure mechanics (XP, leagues, guilt). Gamification stays optional and
   cadence-flexible. No emojis in UI copy.
4. **The learner's effort is part of the product.** Prefer designs where Werner produces
   (writes, explains, retrieves) and Claude critiques/extends — not designs where Claude
   produces and Werner consumes.
5. **Never build the folklore list:** learning-style matching/diagnosis; XP/leagues;
   rigid-streak pressure; highlighting marketed as a study technique. (Evidence: research
   doc, "Do NOT build".)
6. **Keep the Pi light.** ~40MB idle footprint is the norm. No new services, databases, or
   dependencies without a named need. Paid `claude -p` calls are real money — batch them,
   cap them, and never add one to a hot path without a decision record.
7. **Phase 1 engineering rules still bind:** simplest thing that works, YAGNI, single
   source of truth, event log as ground truth, sanitizer default-deny, all quality gates in
   [DEPLOY.md](DEPLOY.md) — especially: **NEVER `rsync --delete`**, always exclude the Pi's
   `content/` and `backend/data/`, check for in-flight generations before restarting.

## Verification rules (non-negotiable, learned the hard way)

- Backend: pytest suite must stay green (`.venv/bin/python -m pytest tests/ -q`).
- Frontend: `node --test` from `frontend/` — **there is NO DOM/jsdom here by design.** Never
  invent fake-DOM tests; app.js wiring is verified by the import check
  (`node -e "import('./src/app.js').then(() => console.log('imports ok'))"`), hand-tracing,
  and live browser verification on the real Pi URL.
- A feature is DONE only after live verification on the Pi (real browser, real data), with
  any synthetic test data deleted afterwards (verify the deletion with a fresh query).
- The events ledger is client-writable: every new read of event payloads must tolerate
  missing/malformed values without crashing.
- Report failures plainly. Never claim done without showing the evidence.

## Decision rights

- **Werner decides:** anything in todo Tier 2 (scheduler change, misconception profile,
  answer persistence, viva, token streaming, houston/infra); any paid-call cost increase;
  any change to how his review schedule or mastery gating behaves.
- **Implementing sessions decide:** routine engineering trade-offs inside an approved item,
  following this charter. When a fork genuinely changes scope or cost — stop and ask.

## Definition of done for Phase 2

Tier 1 of the todo shipped and live-verified; Tier 2 items each explicitly decided by Werner
(built or consciously declined); the folklore list still absent from the codebase; the app
installable as an "app" on Werner's devices; suites green; Pi still light.
