# Readability/Engagement (#3) + Loading States (#3b) — PROPOSAL (needs Werner's sign-off)

Grounded in [docs/research/2026-06-24-readability-engagement-loading-ux.md](../../research/2026-06-24-readability-engagement-loading-ux.md).
Unlike #4/#5/#1 (already shipped), this one was scoped as "research → propose → you
decide → build." Here's the proposal.

## What the research says (short version)
- The biggest readability/engagement wins are **generation-prompt changes**, not UI:
  conversational 2nd-person tone (Mayer's personalization effect), chunked/scannable
  structure (79% of users scan), the solution written as a **worked example** (steps +
  reasoning), and warm/specific feedback microcopy (Duolingo, minus the gamification).
  We already saw this works: #5's "explain more deeply" output is exactly this style.
- For multi-second waits, **skeleton screens + staged status narration** are cheap
  (pure HTML/CSS/JS) and recover most of the perceived-speed benefit. **Streaming**
  (token-by-token) is the ceiling but needs backend work.

## Proposed build — three slices, pick what you want

### Slice A — Readability & engagement (generation-prompt only) — RECOMMENDED
Fold the evidence-backed techniques into the **default** `lesson_prompt` (so every
lesson, not just deepened ones, gets them):
- Address the learner as "you", tutor tone, plain language, short sentences.
- Chunk: short paragraphs, **bold the key term**, bullets for lists.
- Write `solutionNote` as a brief **worked example** (the reasoning, not just the answer).
- Make concept-check explanations **specific and encouraging**, never just "wrong".
- (Interleaving of question formats: apply only once basics are in place — deferred,
  it overwhelms novices.)
**Effort:** small (one prompt, plus matching tests). **Risk:** low — prompt-only, no
schema/UI change. **Payoff:** every newly generated lesson reads better immediately.

### Slice B — Loading states (frontend only) — RECOMMENDED
Replace the plain "Preparing your lesson… / Rewriting… / Gathering…" cards with:
- A **skeleton** of the lesson/capstone layout (greyed blocks + a CSS shimmer).
- **Staged status narration** cycling honest messages on a timer
  ("Reading the topic… Writing the exercise… Preparing the checks…").
Applies to lesson generation, #5 deepen, and #1 capstone waits.
**Effort:** small-medium (one shared loading component + CSS). **Risk:** low — pure
frontend. **Payoff:** the long Claude waits feel much shorter and show "what Claude is
doing", which is exactly what you asked for in #3b.

### Slice C — Streaming (optional, bigger) — DEFER unless you want it
Stream lesson generation token-by-token so text appears in ~1s (time-to-first-token),
cutting perceived wait up to ~70%. The course-creation chat already streams; lessons
use a single validated-JSON call that doesn't stream cleanly. Would need a real
backend change (stream partial content, then reconcile/validate). **Effort:** large.
**Recommendation:** skip for now; Slice B gets most of the felt benefit far cheaper.

## Recommendation
Build **A + B** next (both low-risk, high-payoff, and B directly answers #3b). Hold C.
Each ships as its own slice (TDD → review → deploy → Pi-verify), same as #4/#5/#1.
