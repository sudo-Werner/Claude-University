# Design brief — Claude University (for Claude design / browser)

Paste the block below into the design tool. It encodes the platform's constraints so the
output matches the engine we're building. Full context lives in
`docs/superpowers/specs/2026-06-21-claude-university-design.md`.

---

Design a **personal learning platform** ("Claude University") — a calm, focused, daily-use
study app. **Dark theme.** Accent colours: purple `#7c6aff` and blue `#4fc3f7`. Font:
`system-ui`. **No external CSS frameworks.** Must be **mobile-friendly** (used on phone and
laptop).

**Guiding principle:** the UI must *reduce* cognitive load. One primary action per screen.
**Progressive reveal** — the learner always answers before any solution appears, and hints
are gated (revealed on request, not shown by default). Nothing should feel like a firehose.

**Design these two screens first (the daily surfaces):**

1. **Dashboard** — the home screen, immediately actionable on open:
   - "Today's session" card (next topic + a clear start button)
   - Overall course progress
   - Streak indicator
   - A **90-minute session timer** with three visible phases: warm-up → peak → cool-down
   - A "reviews due" count (spaced-repetition cards waiting)

2. **Lesson flow** — the core learning surface, a guided sequence:
   - Pre-quiz (a few questions, answered *before* the lesson)
   - Lesson body (readable, chunked — only 2–3 new concepts at a time)
   - An inline concept check (fill-in-blank or multiple choice)
   - An exercise with a **hidden solution** (revealed only after an attempt)
   - An "explain it back" text box (the learner writes the concept in plain English)

**Please return three things:**
1. A **design-tokens spec** (text): exact hex colours, type scale, spacing scale, border
   radius, and a component list with their states (default / hover / active / disabled / error).
2. A **screenshot** of each screen.
3. The **raw HTML/CSS**.

---

## After you have the designs

Save them into the project so I (Claude Code) can build against them:
- Screenshots → `content/design/` (e.g. `content/design/dashboard.png`, `lesson.png`)
- Design-tokens spec → `content/design/tokens.md`
- Raw HTML/CSS → `content/design/reference/`

Then tell me they're in, and I'll rebuild them as real components in the engine and
self-verify with a browser before you review.
