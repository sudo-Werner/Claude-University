# Research — Visual Aids / Information Presentation (2026-06-24)

For the request "add more visual aids; what's the best way to present information?".
Note: the earlier research (`2026-06-24-readability-engagement-loading-ux.md`) covered
text readability + loading; it did NOT cover visual/diagram encoding. This fills that gap.
Source: background research agent, web-sourced.

## The evidence (what actually helps)
- **Multimedia principle** (Mayer): words + relevant graphics beat words alone — but
  conditionally, not automatically. Separate verbal/visual channels (dual coding, Paivio).
- **Coherence principle** (the key one for an LLM app): *removing* extraneous visuals
  IMPROVES learning. Decoration competes for working memory. An unconstrained LLM will
  happily add "engaging" visuals that hurt.
- **Seductive-details penalty is real and quantified:** meta-analysis g ≈ −0.16
  (comprehension −0.19, recall −0.17, transfer −0.12). A decorative generated visual is a
  small but reliable *tax* on learning, worst for low-working-memory learners.
- **Signaling / segmenting** (arrows, labels, headings, <hr>) help by exposing structure.
- **Highest-value visuals for technical material:** worked-example / annotated diagrams
  (strongest evidence, helps novices AND experts, improves transfer); flowcharts/process
  diagrams (need text + structure, graphic-only underperforms); comparison tables
  (chunking + cross-dimension comparison); number lines / trees / schematics.
- **Test for any visual:** does it carry information the text doesn't, in a form text can't
  (spatial layout, branching, sequence, comparison)? If not → it's decoration → omit.
- **Expertise-reversal:** heavy scaffolding/labels help novices, become load for experts;
  fade as the learner progresses.

## Feasibility in THIS app (strict default-deny sanitizer, no img/svg/table/JS-libs)
1. **ASCII/Unicode box-and-arrow + number-line diagrams in `<pre>` (already allowed).**
   Zero sanitizer change. Pitfall: `<pre>` doesn't wrap — on a ~448px column only
   ~34–48 chars fit, so author lines ≤ ~32 chars; use Unicode box-drawing (│ ─ ┌ ┐ └ ┘ ├ → ↓),
   monospace, tight line-height, `overflow-x:auto` as a safety net. Best for small vertical
   flows, trees, number lines — not wide diagrams.
2. **Comparison tables — add `<table><thead><tbody><tr><th><td>` to the allowlist.** Low XSS
   risk if attributes stay default-deny (maybe `scope` on <th>). Cap 2–3 columns for mobile,
   `width:100%` + `overflow-x:auto`. The one *new capability* worth the cost.
3. **CSS-only primitives (callouts/boxes/bars from div/span + class allowlist)** — feasible
   but needs allowing `<div>` + a fixed class allowlist + CSS + prompt work; reward overlaps
   tables/<pre>. DEFER.
4. **Inline SVG — NOT worth it.** Raw SVG carries <script>/<foreignObject>/on* handlers;
   sanitizing LLM SVG safely is high-effort/high-risk and defeats default-deny. Skip.
5. Better USE of existing <h2>/<h3>/<hr>/<ul>/<strong> (signaling/segmenting) is itself an
   evidence-based win with zero code.

## Ranked recommendation
1. **Diagrams via prompt** (generation-prompt change, no code): allow ASCII/Unicode diagrams
   in `<pre>` ONLY where they carry structure/process/sequence; ≤32 chars/line; Unicode box
   chars; never decorative. + a one-line `<pre>` CSS safety net.
2. **Coherence / anti-decoration prompt rules** (generation-prompt change): forbid decorative
   visuals; require the "carries info text can't" test; bias to worked-example/annotated
   diagrams; lean on existing signaling tags. Ship WITH #1 so new freedom can't degrade.
3. **`<table>` family in the sanitizer + CSS** (small sanitizer+CSS change): comparison
   tables, 2–3 cols, default-deny attributes.
4. CSS class-allowlist primitives — DEFER. Inline SVG — NOT worth it.

Suggested slice: **#1 + #2 together** (pure prompt, zero risk, ships now), then **#3**
(small, well-bounded sanitizer change).
