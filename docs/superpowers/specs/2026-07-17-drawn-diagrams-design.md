# Drawn diagrams — Claude-authored Mermaid + constrained SVG figures — design

**Date:** 2026-07-17. **Status:** approved direction (Werner 01:36: "I'd like to include
this: Mermaid/SVG drawn diagrams"). Slice 2 of the graphics wave; builds immediately after
`2026-07-17-lesson-images-design.md` (slice 1) and shares its typed-figure pipeline. The
combined ~25-lesson backfill runs ONCE, after both slices ship.

## Goal

Where a lesson's concept is best shown as a *drawn* figure — a process flowchart, a sequence,
a simple chart, a labeled schematic — Claude draws it itself, as code: Mermaid for anything
graph/flow/chart-shaped, constrained inline SVG for labeled spatial schematics. Code-drawn
diagrams are the evidence-backed choice: ~96% label accuracy versus 11-19% for AI-generated
raster images (CAGE benchmark) — and labels are everything in education. Real photos (slice
1) remain the source for complex realistic imagery like anatomy plates.

**Cost shape:** zero extra Claude calls — diagram code rides the existing lesson-generation
call. One-time: two vendored JS files committed to the repo. The combined backfill (slice
1's CLI, extended) stays ≈ one placement call + one image-vision call per cached lesson.

## Decisions

1. **Same figure pipeline, two new types.** The lesson's `images` slots (slice 1) accept,
   alongside `{"type": "web-image", query, caption}`:
   - `{"type": "mermaid", "code": "<mermaid source>", "caption": ...}`
   - `{"type": "svg", "code": "<svg ...>...</svg>", "caption": ...}`
   Placement uses the same `[[figure:n]]` tokens, same ≤3-per-lesson budget, same
   `valid_lesson` if-present shape rules (per-type required keys; `code` a non-empty string
   ≤8 KB). The prompt's figure-type guidance (pedagogy rule 2) becomes: concrete
   identification → `web-image`; process/flow/sequence/hierarchy/timeline → `mermaid`;
   labeled spatial schematic that Mermaid cannot express → `svg` (simple: ≤ ~25 elements);
   quantitative → `mermaid` `xychart-beta`/`pie`. When a diagram would exceed what simple
   code can draw clearly, prefer a `web-image` slot instead.
2. **Mermaid, vendored and lazy.** `mermaid.min.js` (pinned version, committed under
   `frontend/vendor/`) — no CDN, works offline, ~2-3 MB so it is lazy-loaded (dynamic
   `import()`) only when a lesson actually carries a mermaid figure; first paint stays
   fast. Rendered client-side with `securityLevel: "strict"` (mermaid's own label
   sanitization) inside try/catch: **render failure falls back to the caption as text** —
   never a broken figure, never raw code shown to the learner. Model-authored mermaid has a
   known nonzero syntax-error rate; the fallback is the contract that makes that acceptable.
3. **SVG, doubly sanitized, never trusted.**
   - **Server-side (stdlib `xml.etree` — no new dependency): a strict allowlist sanitizer**
     in `backend/figures.py`, run at generation time before the lesson is cached. Element
     allowlist: `svg g rect circle ellipse line polyline polygon path text tspan title
     defs marker`; attribute allowlist: geometry/paint/text attributes (`viewBox x y x1 y1
     x2 y2 cx cy r rx ry width height d points transform fill stroke stroke-width
     stroke-dasharray font-size font-family font-weight text-anchor dominant-baseline
     opacity fill-opacity marker-end marker-start id class`). Everything else — `script`,
     `foreignObject`, `image`, `use`, `a`, every `on*` handler, every `href`/`xlink:href`,
     `style` elements and attributes — is REJECTED (the figure is dropped, not repaired
     silently, when a forbidden element/attribute or unparseable XML is found; parse via
     `xml.etree.ElementTree` with namespace handling, serialize back canonically). A
     required `viewBox` and a `width`-less root (CSS sizes it) are enforced; missing
     viewBox → drop.
   - **Client-side (vendored DOMPurify `purify.min.js`, ~20 KB, pinned):**
     `DOMPurify.sanitize(code, {USE_PROFILES: {svg: true, svgFilters: true}})` immediately
     before injection — defense in depth; the browser never receives unsanitized markup
     even if a cached lesson file were hand-edited.
   - SVG figures are stored as sanitized code inside the lesson JSON (no files, no serving
     route, nothing on the images route).
4. **Authoring constraints in the prompt** (the known LLM-SVG failure modes are label
   collisions and out-of-viewBox coordinates): fixed `viewBox="0 0 800 500"`; every part
   labeled with `<text>` INSIDE the drawing (no legend); ≤ ~25 elements; ≥14px font; keep
   labels horizontally clear of each other; simple flat colors that read on a light card.
   The draw-look-redraw vision loop is explicitly OUT of this slice (rasterizing SVG on the
   Pi needs a new dependency; revisit only if drawn-figure quality disappoints in practice).
5. **One render path (`renderFigure`)** in `lesson.js`: the slice-1 token expansion becomes
   a switch on `type` — `web-image` → `<img>` arm (slice 1, unchanged); `mermaid` → a
   placeholder `<div class="fig-mermaid" data-fig="n">` hydrated after paint by the
   lazy-loaded renderer (caption-fallback on error); `svg` → DOMPurify-sanitized markup
   injected into the figure; unknown types → nothing. All three share the same
   `<figure class="lesson-fig">` + esc()'d `<figcaption>` wrapper; drawn figures carry the
   credit `Drawn by Claude` in place of a license line (honest-labels rule).
6. **Deepen/revision/backfill seams inherit slice 1's answers.** Diagram code lives in the
   lesson JSON, so deepen regenerates it naturally; `apply_revision` untouched. The
   combined backfill's placement call may propose all three types; its prose-unchanged
   validator and per-lesson costs are unchanged.
7. **Workspace/chat surfaces are untouched.** Diagrams render in lesson bodies only; chat
   stays plain text.

## Error handling

- Invalid mermaid → caption-as-text fallback at render time (client).
- SVG that fails the server allowlist → figure dropped + token stripped at generation time
  (same fail-open contract as slice 1's resolver; a lesson is never blocked by a bad figure).
- Lazy-load failure of the vendored renderer (file missing) → caption-as-text fallback.
- A cached lesson hand-edited to contain hostile SVG → DOMPurify strips it client-side.

## Security

- Two independent sanitization layers for SVG (stdlib allowlist server-side at cache time;
  DOMPurify client-side at render time); mermaid renders under `securityLevel: "strict"`
  from code that never contains learner input (generation output only, learner text never
  enters figure code).
- No new network surface: both libraries are vendored, pinned, and committed; no CDN, no
  runtime fetch. Keep the vendored DOMPurify current when touching this area (it has had
  historical SVG-namespace bypasses).
- Figure code size cap (≤8 KB) enforced in `valid_lesson`, so a runaway generation cannot
  bloat lesson files.

## Testing

- **Backend**: SVG sanitizer — accepts a well-formed labeled schematic unchanged
  (canonicalized); rejects `script`, `foreignObject`, `on*` attributes, `href`, `style`,
  missing viewBox, unparseable XML (each: figure dropped, token stripped, lesson still
  valid); ≤8 KB cap; mermaid slots pass through untouched with shape validation only;
  mixed-type lessons validate; slice-1 web-image behavior unchanged (regression).
- **Frontend**: `renderFigure` switch — svg arm sanitizes (a `<script>`-bearing payload is
  neutralized in the test using the REAL vendored DOMPurify), mermaid arm renders a
  placeholder div and the caption fallback path works without the library, web-image arm
  regression, unknown type renders nothing; esc() cases for captions; import checks. A
  vendored-files-exist test (both pinned files present and non-empty).

## Deploy notes

Standard DEPLOY.md. The two vendored files ship via the normal rsync (frontend is not
excluded). Verify lazy-load works over the Pi origin (plain HTTP — dynamic `import()` is
fine on insecure origins, unlike crypto APIs). THEN run the combined backfill (slice 1 CLI,
now proposing all figure types) once, post-backup, pgrep-clean.

## Out of scope

- Draw-look-redraw vision loop for SVG (revisit on evidence of poor quality).
- Interactive/animated diagrams, KaTeX, mindmap/architecture mermaid variants beyond the
  vendored build's defaults.
- Diagrams in chat, exams, remediation, review items, or capstones.
- Any server-side rasterization dependency (cairosvg etc.).
