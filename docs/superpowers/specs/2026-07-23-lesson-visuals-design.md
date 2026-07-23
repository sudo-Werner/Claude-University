# Lesson Visuals — Richer, On-Brand, and Animated — Design Spec

**Date:** 2026-07-23
**Status:** Brainstorm-approved shape; awaiting spec review before an implementation plan is written.
**Owner decisions locked:** build the full feature as one push (not staged); revive real photos (`web-image`) as well as drawn diagrams.
**Grounding:** two multi-agent grounding passes on 2026-07-23 — a pipeline audit + design-token style contract + learning-science evidence + type-selection strategy, and an animation pass (security review of animated SVG, animation-vs-static evidence, and authoring design). This spec is the durable synthesis; the raw analyses were ephemeral scratch.

---

## 1. Problem

Every figure Claude University has ever shipped is a mermaid diagram rendered in mermaid's stock grey/blue defaults. Live disk state on the Pi (2026-07-23): 13 generated lessons, 6 figures, **6/6 mermaid, 0 svg, 0 web-image**, and **no `images/` directory exists in any of the 4 courses** — meaning no fetched photo has *ever* survived resolution in the app's history, including the human-body course (4 figures, all mermaid) whose subject is the headline example in the figure prompt.

Three compounding causes, each verified in code:

1. **Prompt bias.** The figure guidance frames `web-image` and `svg` as fallbacks and gives `mermaid` the broadest content mandate.
2. **Unequal survival odds.** `mermaid` passes through `process_slots` verbatim with zero gates; `web-image` runs a six-stage fail-open gauntlet (search → license filter → download → magic-byte verify → vision-pick → deadline); `svg` faces an all-or-nothing sanitizer that drops the *whole* figure on a single unlisted attribute.
3. **Silent everything.** Dropped slots are erased with no logging anywhere. There is no way today to distinguish "the model never asked for a photo" from "it asked and the fetch silently died." This is the same silent-failure class as the audit and the Tailscale-key incident.

Even the mermaid that does survive renders off-brand against the app's warm frosted-glass design system.

The fetch **infrastructure works** — a direct test on the Pi returned 8 Wikimedia Commons + 5 Openverse candidates for "human heart anatomy diagram" — so the photo failure is downstream of search, not the network.

## 2. Goal & non-goals

**Goal.** Give lessons the *right kind* of figure, reliably, rendered in the app's design language — and, where motion itself is the concept, a safe animated diagram. Concretely:
- Real photos where recognizing a real thing is the point; drawn schematics where structure is the point; animation where a dynamic process is the point.
- Every figure (including existing mermaid) rendered on-brand.
- A new, security-reviewed animated-SVG capability for dynamic/process content (the "labeled heart with animated blood flow" example).
- Treatment matched to the content: a still where structure is the point, animation where *change* is the point, and learner control (pace / scrub) scaled up only where the material is genuinely hard (§5D ladder).

**Non-goals (explicit).**
- **Not** more figures per lesson. "Richer" means *correct-type and on-brand*, never higher frequency. The evidence forbids decorative additions (see §3).
- **Not** a figure on every lesson. Zero figures is often correct and stays correct.
- **Not** CSS-based animation (rejected on security grounds, §5E).
- **Not** a quota or "diversify the types" instruction to the model (would manufacture decorative figures).
- **Not** interactivity as decoration. A control earns its place by helping a learner manage a genuinely dynamic or hard figure (§3), never as a gimmick on simple content.
- **Not** difficulty-driven *animation*. Difficulty scales the control layer, not whether a figure moves — a hard static concept stays a still (§5D).

## 3. Evidence-grounded constraints (the honest guardrails)

These are binding design constraints, not background. Effect sizes are reported honestly; several are small.

**On figures in general (static):**
- Decorative / seductive visuals carry a small but reliable **harm** with no upside (seductive-details meta-analyses converge on g ≈ −0.16; comprehension ≈ −0.19). Organizational/representational diagrams help (g ≈ 0.24–0.52). → **Every figure must carry information; none is added for interest.**
- Functional color (signaling essential structure) helps; decorative color does not. → **The style contract's palette signals structure, never prettifies.**

**On animation specifically (the sobering part):**
- Animation is **not reliably better** than a good static diagram. Höffler & Leutner (2007): overall d ≈ 0.37, but *representational* animation d ≈ 0.40 while *decorational* ≈ null; procedural-motor content d ≈ 1.06. Berney & Bétrancourt (2016): overall g ≈ 0.23, and the gain **only materializes** with system-pacing (g ≈ 0.31) and learner control.
- **Transient-information effect** (Wong/Leahy/Sweller 2012): animation overloads working memory because each frame vanishes. Short segments beat static; long continuous loops fall *below* static, especially for many-interacting-parts content.
- **Congruence & apprehension** (Tversky 2002): the visual change must map one-to-one onto the conceptual change, and be slow/simple enough to actually perceive. Many apparent animation "wins" were unfair comparisons where the animation simply carried more content.
- **Signaling** (de Koning, on the cardiovascular animation specifically): cueing the active structure helps (g ≈ 0.4).
- For **static structure / part-identification**, a static labeled diagram is as good or better.
- **Learner control scales with difficulty** (cognitive-load / segmenting principle): letting the learner set the pace — pause, replay, scrub, slow down — helps *more* as intrinsic load rises, because it offloads the transient-information burden onto the interface. This is the evidence basis for scaling *interactivity* (not *animation*) by difficulty (§5D ladder).

**Binding animation rules derived from the above:**
- Animate **only** when the objective is dynamic/procedural/causal and a static frame with arrows would genuinely lose the point.
- The motion must be **congruent** (real flow shown as real directional flow) and **accurate**.
- **Labels stay fixed** (structural, not transient).
- **Learner controls** — play/pause/replay, default paused. Never autoplay-once-and-gone.
- Show the **static labeled diagram as the persistent base** so structure-learning and process-learning each use the format that suits them (and experts can skip the motion).
- **At most one animated figure per lesson.** Multiple looping graphics violate the "one focus / low-glare" layout principle.

Honest expectation to hold internally and in any UI copy: animation is a *small, conditional* gain, earned per objective — not a blanket upgrade.

## 4. Architecture overview

The figure system already has a clean, symmetrical six-touchpoint seam; every change lands in it, and the new animated type flows through the same seam:

1. **Authoring prompt** — `backend/generation.py` `_IMAGES_BLOCK` + `backend/figures.py` `DRAWN_FIGURE_GUIDANCE`.
2. **Shape validation** — `backend/generation.py` `valid_images`.
3. **Server processing** — `backend/images.py` `process_slots` (splits by type; runs `sanitize_svg` for drawn types; fail-open drop).
4. **Server sanitizer** — `backend/figures.py` `sanitize_svg` (strict allowlist, never-repair).
5. **Render** — `frontend/src/views/lesson.js` `figureHTML` / `expandFigureTokens` (emits placeholder; never string-interpolates figure code).
6. **Client hydration** — `frontend/src/app.js` `hydrateFigures` (DOMPurify layer-2, `insertAdjacentHTML`).

**Two-layer security model is preserved throughout:** server-side allowlist sanitizer (authoritative) + client-side DOMPurify (defense-in-depth against tampered cache/DB). Nothing in this spec weakens that; the animation work extends both layers in lockstep.

## 5. Components

Built as one push, but internally sequenced (see §7). Each is independently testable.

### A. Figure telemetry (the linchpin — build first)

**What.** Emit one structured record per figure slot at `process_slots` (the natural choke point that already sees every raw slot and every outcome). Fields keyed by `(course_id, lesson_id, n)`: `requested_type` (mermaid/svg/web-image/svg-animated), `outcome` (rendered/dropped), `drop_reason` naming the exact gate (`sanitizer-rejected`, `license-filtered`, `download-too-big`, `download-bad-magic`, `vision-rejected`, `deadline`). Note: a per-slot record only exists for a type the model *did* request, so "the model never asked for a photo" is not a per-slot `drop_reason` — it is inferred at the population level from the absence of `web-image` records across lessons (the §5D metrics), which is exactly the model-omission-vs-silent-drop distinction we need.

**Sink decision (my call, overridable):** write as `event_type="lesson_figure_selection"` rows via the existing `events.insert_events` (the `course_id`/`topic_id` columns already exist), so it's queryable alongside the rest of the app's analytics. The only stored free-text is the model-authored search `query`, which is low-PII; retention follows the events table's existing posture.

**Why.** The only way to distinguish model-omission from silent pipeline drops, and the prerequisite for honestly evaluating B and D. ~10 lines at existing `return None` points; changes no behavior.

**Tested.** Generate N lessons, confirm exactly one record per slot; feed slots that trip known gates (an oversized PNG, an SVG with a disallowed attribute) and confirm the record names that gate. Capture a **baseline on the current prompt before any other component ships.**

### B. Drop-point fixes (revive web-image + svg)

Fix only the gates the audit isolated; guided by what (A) shows actually fires.

**web-image:**
- **Size cap** (`images.py` `MAX_BYTES = 400 KB`, `iiurlwidth=800`) silently rejects any detailed anatomy/diagram PNG, and the 800px thumbnail is soft on high-DPI screens. Fix (decided by Werner 2026-07-23): request a **1600px-wide** Commons rendition **and** raise the byte cap to **~2 MB**. This targets the real lever — we fetch a downscaled rendition, never the multi-MB original, so a 5 MB cap would change nothing. Trades a little page weight for photos that both *exist* and look crisp.
- **License matcher** (space-terminated string match) drops valid hyphenated forms (`CC-BY-SA-4.0`, `CC BY-SA 3.0 Migrated`). Fix: broaden the matcher to accept the real Commons/Openverse license spellings.
- **`vision_pick` null:** keep **failing closed** (a wrong photo is worse than none — this is arguably correct), but the telemetry from (A) must record every null so we can see how often "no candidate fit" fires. Decision is explicit, not accidental.

**svg:**
- Add `stroke-linecap` and `stroke-linejoin` to `ALLOWED_ATTRS` (the app's own icons use them). This stops a 95%-clean model SVG from being discarded whole.

**Tested.** Unit tests: a ~1.5 MB / 1600px-rendition PNG now survives (and a >2 MB one is still rejected); a hyphenated CC license now passes; an SVG with `stroke-linecap="round"` now sanitizes clean. Telemetry before/after confirms the gates actually stop firing on real generations.

### C. On-brand style contract

**Mermaid.** Prepend a one-line `%%{init: {"theme":"base","themeVariables":{…}}}%%` directive to every mermaid `code` string, mapping mermaid's palette to `content/design/tokens.md`: `primaryColor` ≈ `--purple-soft` `#ece7ff`, node border `--purple` `#7c6aff`, `background` transparent (so the glass card shows through), `fontFamily` `system-ui`, brand pie/xychart palettes. Safe under mermaid's `securityLevel:"strict"` (themeVariables is not in the secure lock-list).

**SVG.** A style guide that stays strictly inside the `figures.py` allowlist: flat `fill` + `fill-opacity` tints (no `rgba()` packing, no gradients, no blur/shadow — `filter`/`style` are banned), arrowheads drawn as `<polygon>` triangles (marker orient/size attrs aren't allowlisted), labels placed on the drawing. Palette from the design tokens — **except where a color itself is the information** (arterial-red vs. venous-blue, hot vs. cold, acid vs. base): there the established domain convention wins over the brand palette, because the evidence's "functional color" (§3) *is* that conventional signal — brand-purple for oxygenated blood would break the very cue it's meant to carry. Brand tokens still set the surrounding non-semantic ink/stroke/fills.

**CSS.** Add a `--glass-inner` tile behind `.lesson-fig-svg`/`.lesson-fig-mermaid` and stop force-stretching small mermaid diagrams.

**Honest tension (documented, accepted):** the app's signature depth (blur, soft shadow) is impossible in sanitized SVG. The contract substitutes thin strokes and low-opacity fills — SVG figures will always look flatter than the surrounding glass UI. This is functional signaling, which the evidence supports, not decorative styling.

**Tested.** Apply the init directive to the 6 existing mermaid figures and **verify the warm palette in-app on the real Pi URL** (mermaid renders in the browser — verify in-app, not in isolation). Run the SVG style-guide example through `sanitize_svg` and confirm it survives.

### D. Type-selection tuning (quality, not quantity)

Rewrite `DRAWN_FIGURE_GUIDANCE` as a **two-stage decision**: Stage 1 (does any figure belong? — "zero images is often correct") is kept verbatim. Stage 2 (which type?) becomes a type-neutral router:
- **web-image** — first-class, not a fallback. Hard rule: whenever the learner must recognize a real thing by appearance (anatomy, organisms, minerals, artefacts), a drawing cannot substitute.
- **static drawn (svg/mermaid)** — the default: structure/relationships/hierarchy, or a process readable at a glance from arrows and labels.
- **animated (svg-animated)** — only when meaning *is* change over time (§5E gate test).

Delete the "too complex to draw → prefer web-image" framing that casts photos as the loser's option. Consolidate the router into a single source of truth (it's currently duplicated across `generation.py` and `images.py`).

**Second axis — difficulty scales the *treatment*, not the type.** Content-type (above) decides *what* the figure is; a coarse **difficulty band** decides *how much interactivity and authoring investment* it earns. The two must not be conflated: whether a figure animates is governed by whether the content is *dynamic* (a process/motion), **never** by how hard it is — a hard *static* concept (e.g. "precision vs. accuracy") gains nothing from motion and, per §3, can be hurt by it. Difficulty instead scales the *control layer*, for which the evidence is specifically supportive (learner control helps more as load rises, §3). Difficulty is read primarily from the objective's existing `bloom`/`knowledge` tags (the Phase-0 objective-id backbone — Bloom is itself a cognitive-complexity ladder), refined by an optional generator estimate of intrinsic load (unfamiliar terms, many interacting parts). Keep it **coarse — 3 bands** — never a false-precise number. The two axes combine into a treatment ladder:

| Content | Difficulty | Treatment |
|---|---|---|
| Static (structure / identification) | any | Labelled still — the default (tap-to-reveal for hard static is a deferred v2) |
| Dynamic / process | everyday | Animation + play/pause (§5G) |
| Dynamic / process | hard | Animation + learner control — scrub / speed — authored in shorter, signalled segments |
| Dynamic, hardest + high-value | — | Flagged as a **Tier-B bespoke showcase** (hand-built, §5G) |

`dynamic?` gates the motion; the difficulty band scales the control layer and flags Tier-B candidates. **Release 1** wires the generic control layer (§5G) onto *every* animated figure, and uses difficulty to (a) sharpen segment/signal authoring on hard dynamic figures and (b) flag Tier-B candidates. Richer per-band interactivity (tap-to-reveal on hard static; bespoke controls beyond the showcases) is a **v2 gated on telemetry actually validating the difficulty signal** (§10) — we do not build elaborate machinery on an unproven guess.

**"Good selection" = population-level distribution health per content stratum**, derived free from each objective's existing `bloom`/`knowledge` tags (via the Phase-0 objective-id backbone) — not a per-lesson ground-truth label (which isn't honestly available). Never tell the model to balance types.

**Tested via telemetry metrics over a rolling window:** (1) concrete-ID alignment rate (identification-stratum figure-bearing lessons requesting ≥1 web-image; starting target ≥ 0.6, tunable); (2) type non-degeneracy alarm (diagnostic if >85% mermaid — a monitor, never told to the model); (3) web-image realization rate (of requested photos, fraction that resolve — separates "won't ask" from "won't resolve," directly testing B). **Regression gate:** alignment ↑ AND figures/lesson within ±10% of baseline AND zero-figure rate not falling; else revert.

### E. Animated SVG figures (new capability)

**New figure type `svg-animated`** (not animation inside the existing `svg` type). Data shape is a strict superset — `{type:"svg-animated", code, caption}`, no new fields. A distinct type lets the frontend show controls, honor `prefers-reduced-motion`, and enforce animation-specific validation **without touching the shipped static-`svg` path** — zero regression risk.

**Security model (the core of this component).** Use **SMIL, not CSS**.
- CSS-in-SVG (`<style>` + `@keyframes`) is **rejected**: a `<style>` inside inline SVG is not scoped to the figure — its rules apply page-wide, so a figure could restyle/hide honest-UX chrome or exfiltrate via `url()`/`@import` (the app has **no CSP** today). It also needs a full CSS parser the sanitizer doesn't have. Too much surface.
- SMIL's abuse surface is narrow and controllable, and **crucially the bundled DOMPurify 3.4.12 already allows `animateTransform` + `animateMotion` while stripping the dangerous `animate`/`set`/`mpath`** — so the two layers agree with essentially no client change, and the safe subset is the one DOMPurify's authors deliberately kept.

**Release-1 subset (conservative, security-review authoritative):** `animateTransform` + `animateMotion` **only**. This unlocks slide/pulse/zoom/spin/shear and motion-along-a-path — enough for the heart-flow example — while making the canonical SMIL XSS (`attributeName`→`href` injection) *structurally impossible*: neither element takes an arbitrary `attributeName` (`animateTransform`'s is locked to `transform`; `animateMotion` has none). `href`/`xlink:href` therefore stay fully banned.

- **`ALLOWED_ELEMENTS` delta:** add exactly `animateTransform`, `animateMotion` (camelCase is load-bearing). **Not** `animate`, `set`, `animateColor`, `mpath`, `discard`.
- **`ALLOWED_ATTRS` delta:** `attributeName`, `type`, `dur`, `begin`, `repeatCount`, `values`, `additive`, `accumulate` (transform); `path`, `keyPoints`, `rotate` (motion). Omit `from`/`to`/`calcMode` (DOMPurify strips them — authors express keyframes via `values`), and `end`/`restart` (reintroduce event syntax).
- **Value restrictions (server, reject → whole figure dropped):** `attributeName` must be exactly `"transform"` on `animateTransform` and rejected on `animateMotion`; `type` enum `translate|scale|rotate|skewX|skewY` (no `matrix`); `dur`/`begin` clock-values only (rejects all event syntax like `rect.click`, `anim.end`, `accessKey(x)`); `values`/`keyPoints` numeric-list only (blocks `url(`, `<`, `:`, letters); `path` path-grammar only; `repeatCount` `indefinite`|number.
- **Client DOMPurify config:** add the two elements + attrs to the advisory allowlists, and **explicitly `FORBID_TAGS`** `animate`/`set`/`mpath`/`animateColor`/`discard`/`style`/`image`/`use`/`a`/`foreignObject`/`script` (redundant with defaults today, but documents intent and survives a future DOMPurify that promotes them). `FORBID_ATTR` `href`/`xlink:href`. No `ADD_TAGS`, no `ADD_ATTR`.
- **Budget:** reuse the 8 KB cap; add ≤ 30 drawn elements and ≤ 8 animation elements; every `dur` 1–20 s.

**Deferred to a separate later security review (NOT in this release):** plain `<animate>` behind a strict geometry/paint `attributeName` allowlist, which would enable fade (`opacity`) and "flowing dashes" (`stroke-dashoffset`). It requires re-enabling a DOMPurify-*disabled* element (`ADD_TAGS:["animate"]`) — a genuine defense-in-depth cost. `<set>`/`<mpath>` stay banned permanently. The authoring grounding wanted this now; the security grounding (which inspected the actual bundle) says defer it. We defer.

**Authoring.** Append `svg-animated` guidance to the figure prompt with the load-bearing rule: **the drawing must be a correct, fully-labeled diagram with the animation removed** — base positions equal the animation's start state, motion expressed relatively (paths from `M0,0`), so stripping the animation leaves a sensible still frame. Prefer `animateMotion` (no `attributeName` surface). At most one animated figure per lesson. Colors from the design tokens.

Worked example carried in the spec (validated by grounding): a `viewBox="0 0 800 500"` four-chamber heart, deoxygenated→blue `#4fa3e8`, oxygenated→**red** (domain convention beats brand-purple here — §5C), cream chambers, warm `#241f1a` labels, four `<circle>` blood cells travelling `animateMotion` paths from `M0,0` along the vessels — 24 elements, 4 animation elements, well under 8 KB; strip the four `<animateMotion>` and a correct labeled still diagram remains. (This is the slim *model-generated* Tier-A figure; the richer hand-built Tier-B heart, §5G, carries more cells and a beat — allowed because Tier B is exempt from this budget.)

**UX (in the frosted-glass figure card).** Default = **paused on the still first frame** with a Play affordance (honors the read-first/low-glare principle; makes reduced-motion a trivial subset). A small frosted mini-glass control chip (built off `--glass-soft`/`--tab-pill` tokens), **provided by the figure player (§5G)**: Play/Pause, Replay, Loop toggle (default on), and — for hard dynamic figures — an optional speed/scrub. All are driven through the player's clock ownership (§5G), so the SVG itself carries no script. `prefers-reduced-motion`: pause + still frame, controls remain to opt in, no motion nudge. `IntersectionObserver` pauses off-screen figures. Reuse the existing `stillFresh()`/`isConnected` staleness guard. `aria-label`s + `role="group"` + the SVG `<title>`.

**Reliability — fail gracefully to a static frame (four layers):** (1) author discipline (still frame is the fallback, exercised daily by reduced-motion users so it can't rot); (2) server drop-on-reject (never a blocked lesson); (3) client DOMPurify strip still leaves the static base; (4) caption painted before hydration is the last fallback. **No new vendor library** — SMIL is native and reuses the DOMPurify path already loaded for static svg (one fewer failure mode than mermaid).

### F. Content-Security-Policy header (defense-in-depth)

The security review found **no CSP anywhere** — the two sanitizers are the sole defense against external references. Add a response CSP as a cheap third layer: at minimum `default-src 'self'; object-src 'none'; base-uri 'none'`, no `unsafe-inline` for scripts. Our figures carry no external `url()` and no `<style>`, so the surface is already closed by the allowlists — CSP is depth for free. Verify it doesn't break the existing app (inline styles/scripts audit first).

### G. Interactive figure player (app-side controls)

The controls are a property of the **trusted app**, never of the figure. The model-generated SVG stays pure declarative markup (the §5E subset); a small player module in `frontend/src/app.js` wraps every `svg-animated` figure and owns *all* interactivity. This is precisely what keeps interactivity safe — **no executable code is ever emitted into a lesson**; the sanitizers keep stripping any that appears.

**Mechanism (verified in a live mockup, 2026-07-23).** The player calls `svg.pauseAnimations()` to take the SVG's own SMIL clock offline, then drives it from one `requestAnimationFrame` loop: `t += dt * rate; svg.setCurrentTime(t)`. Because the beat (`animateTransform`) and the flow (`animateMotion`) share that single clock, one `rate` scales the whole figure coherently. Measured on the heart mockup: `rate = 1.0` runs true-time, `rate = 2.5` runs 2.5×, and `animationsPaused()` confirms the SVG's own clock is off (the app owns time).

**Tier A — generic, release 1, on every model-generated animated figure.** Play/pause, replay, loop toggle, and — since scrubbing a SMIL clock is free and universally useful — an optional **speed / scrub** control. Domain-neutral. Honors `prefers-reduced-motion` (start paused on the still frame), `IntersectionObserver` pauses off-screen figures. **No new figure field** — the player attaches to any `svg-animated` figure by type alone.

**Tier B — bespoke showcases, curated, hand-built.** A small, deliberately-added set of hand-authored interactives for the hardest, highest-value dynamic concepts, where a *semantic* control beats a generic one — e.g. a **heart-rate slider** (55–180 bpm, Resting→Sprinting) instead of a raw speed slider. Authored by hand, not generated (they cannot be mass-produced at quality), added on demand rather than per-lesson. **Trust boundary:** a Tier-B showcase is developer-authored and code-reviewed, committed in-repo like any frontend component — so it is **trusted by review**, not run through the *model-output* sanitizer (§5E), which exists to defend against untrusted model/cache content. It may therefore use the fuller SMIL surface the untrusted path forbids (e.g. `xlink:href` group-targeting for the beat) and is exempt from the §5E element/animation budget. What still binds it: the figure markup carries **no script** (interactivity is the trusted app player or a bespoke variant of it), and the CSP (§5F) still bounds any external reference. The published heart mockup (`scratchpad/heart-mockup.html`) is the first Tier-B showcase and the reference implementation. **Default scope:** ship Tier A in this release; Tier B is a post-release curated track (heart first), never a release gate.

**Why the model may not emit interactive widgets.** Arbitrary per-figure JS is exactly the surface the two-layer sanitizer exists to close. The player holds the line: fixed, trusted controls scale to every figure; bespoke behavior is hand-built and reviewed.

**Tested.** A Playwright check that the player pauses the SVG's own clock (`animationsPaused()` true) and that `setCurrentTime` advances at the selected rate (≈1.0× and ≈2.5×); play/pause/replay/scrub state transitions; reduced-motion starts paused; an off-screen figure pauses. Reuses the existing frontend import-resolution check on the changed `app.js` module.

## 6. Data model changes

- New figure `type` value `"svg-animated"`; `{type, code, caption}` shape unchanged (superset).
- `valid_images` (`generation.py`): one new branch mirroring `svg` (non-empty `code ≤ 8192` + caption), routed through the extended sanitizer.
- `isValidFigureEntry` (`lesson.js`): `|| entry.type === "svg-animated"` with the same non-empty-`code` check.
- `figureHTML` routes `svg-animated` to a placeholder carrying `data-fig-svg-anim="n"` for control wiring.
- No change to token expansion, fail-open drop, or the caption fallback.
- **No new field for interactivity or difficulty.** The generic player (§5G) attaches to any `svg-animated` figure by type; the difficulty band that scales authoring / Tier-B (§5D) is read from the objective's existing `bloom`/`knowledge` tags, not stored per figure. Tier-B showcases are bespoke app modules keyed by lesson/objective, not a generated figure `type`.

## 7. Sequencing (within the one push)

1. **Telemetry (A)** + baseline capture. The linchpin — without it we can't tell whether B/D did anything.
2. **Style contract (C)** — pure win, independent, fixes figures already live. Verify on the Pi.
3. **Drop-point fixes (B)** — guided by what (A) shows actually fires.
4. **Type-selection tuning (D)** — behind the regression gate; depends on both A (to measure) and B (so requested photos can resolve).
5. **Animated SVG (E)** — the sanitizer extension + new type + UX; its own malicious-figure corpus and client-layer test.
6. **Interactive figure player (G)** — with or just after E: the trusted app-side control layer every animated figure needs (Tier-A generic controls). Tier-B bespoke showcases (the heart first) are a **post-release curated track, not a release gate**.
7. **CSP (F)** — after an inline-style/script audit; independent, ship when safe.

## 8. Testing strategy

- **Python unit tests** for every allowlist change and drop-point fix (extend `tests/test_figures.py`, `tests/test_generation.py` / images tests).
- **Malicious-figure corpus** (must return `None`): `<set attributeName="href" to="javascript:…">`, `<animate attributeName="href" …>`, `animateTransform attributeName≠transform`, event-based `begin`, `type="matrix"`, non-numeric `values`, `mpath`+`xlink`, `<style>`, `foreignObject`, oversize. Must-pass: spin/slide/pulse/motion examples that then actually animate.
- **Client-layer test** (new, since `app.js`/DOMPurify aren't in the Python suite): a Playwright check running the real `frontend/vendor/purify.min.js` with the new config — must-pass figures keep their animation elements; `animate`/`set`/`mpath`/`style` are removed; `from`/`to`/`calcMode` stripped (locks the `values`-only contract).
- **Still-frame test:** strip all `animate*` from a generated `svg-animated`, assert the remainder passes `sanitize_svg` and still contains every `<text>` label — proves the fallback is meaningful.
- **Frontend import-resolution check** on changed modules (project practice; `app.js` isn't unit-tested for wiring).
- **Pi live-verification:** regenerate a handful of lessons across domains (esp. human-body), confirm via telemetry that web-image and svg now appear, visually confirm the on-brand palette and a working animated figure with controls + reduced-motion, on the real Pi URL.

## 9. Open decisions

Technical calls I've made (overridable by Werner):
- Telemetry sink = events table (§5A).
- `vision_pick` null = keep failing closed, but now visible in telemetry (§5B).
- Animation subset = conservative `animateTransform`+`animateMotion` now; `<animate>` deferred (§5E).
- Add a CSP (§5F).
- concrete-ID alignment target = 0.6 to start, tunable (§5D).

Decided by Werner (2026-07-23):
- **Photo-preferred = all subjects.** No subject allowlist — a real photo/plate is *available* for any course when a concrete-identification figure is warranted. This does NOT force a photo into every lesson: whether a figure appears at all, and whether it's a photo vs. schematic vs. chart, stays the per-figure content judgment of §3 (spatial/structural/process/quantitative, never decorative). The §5D change is therefore "stop framing photos as a fallback," not "add a subject gate."
- **Backfill = yes.** Apply the style contract + prompt changes (and re-resolve figures) onto the 6 existing figures / 13 lessons via the existing `backfill_course` path, not new lessons only.
- **Image size = 1600px Commons rendition + ~2 MB cap** (§5B). Chosen over the 5 MB idea because we fetch a downscaled rendition, not the original — 1600px is the lever that makes figures crisp on high-DPI screens.
- **Treatment ladder (§5D + §5G).** Figure treatment is a function of two generation-time signals — content-type (gates whether it animates) and a coarse 3-band difficulty (scales interactivity + flags Tier-B). Difficulty is read from the objective's existing bloom/knowledge tags, refined by an optional generator estimate, and **validated against telemetry before interactivity is scaled on it** (§10). Interactivity ships via a trusted app-side figure player (§5G), keeping generated SVGs declarative; bespoke showcases (Tier B, e.g. the heart-rate heart) are hand-built and curated, not generated. Release 1 = Tier A on every animated figure; Tier B added on demand, heart first.

## 10. Honest caveats & risks

- **Animation is a small, conditional win** — and a bad animation teaches worse than a good static diagram. The §3 rules are the price of it helping at all; if we can't meet them for a given lesson, the static labeled diagram is the correct output.
- **SVG can never carry the brand's blur/shadow depth** (sanitizer bans `filter`/`style`). Drawn figures will look flatter than the glass UI.
- **Photo effort asymmetry is partly real** — an external fetch can legitimately fail; the model's learned avoidance is justified if realization stays low even after B. Metric (3) exists to tell prompt problems from pipeline problems; don't over-tune the prompt against a pipeline issue.
- **"Fun" is bounded by "functional."** Motion that carries meaning (blood flow): yes. Motion for life/polish on static content: no — it's the exact failure the evidence warns against.
- **No decorative bloat, ever** — the regression gate on figure frequency (§5D) is the enforcement.
- **Difficulty is a guess until telemetry says otherwise.** The band scales interactivity and Tier-B investment but is an authoring-time estimate. Keep it coarse (3 bands) and validate against the §5A telemetry — do "hard"-rated figures actually draw more replays / correlate with lower first-try mastery? — before building richer per-band interactivity. Don't scale machinery on an unvalidated signal.
