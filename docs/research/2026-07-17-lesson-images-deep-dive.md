# Lesson images deep dive — what's best for the system

**Date:** 2026-07-17 ~01:20 CEST. **Trigger:** Werner (01:04): "brainstorm ways we can use
graphics a little more... not just txt based graphics, but actual diagrams and images."
Interview answers: **both real images and drawn diagrams, images first; retrofit existing
lessons + all new ones.** Three parallel researchers: open-image sourcing APIs (live-tested),
codebase integration (read-only analysis), learning science + drawn-diagram tech.

## Headline: the LLM should never pick image URLs — it writes queries, the backend fetches

The original sketch ("Claude finds image URLs during its lesson web search, verified against
captured search results, like sources/videos") **does not survive contact with the code or
the ecosystem**:

- `_collect_sources` only captures `{title, url}` pairs from WebSearch result events. Web
  search returns Commons *description pages*, not `upload.wikimedia.org` *file* URLs — a
  model-cited image URL would almost never be in the captured set, so the existing trust
  filter would drop nearly everything (integration researcher, verified against
  claude_client.py:213-258).
- An LLM browsing sees page *text*, never pixels — it cannot judge whether a file is a
  usable labeled diagram, and it cannot reliably read license metadata off arbitrary pages
  (sourcing researcher).
- The backend must download the bytes anyway (Werner chose local caching), at which point
  the trust question disappears: **the server only ever serves bytes it fetched itself from
  a query it issued.**

**Winning architecture (all three researchers independently):** lesson generation emits 0-3
image slots — `{query, caption}` — plus plain-text `[[figure:n]]` placement tokens in the
prose (verified: `sanitize_html` passes `[[figure:1]]` through verbatim). A new
`backend/images.py` resolves each slot deterministically and fails open (no figure is always
acceptable; a wrong or broken figure never is).

## Sourcing (live-tested 2026-07-17)

| Source | Verdict | Facts |
|---|---|---|
| **Wikimedia Commons** (primary) | Excellent for educational figures | One API call does search + license + thumbnail: `action=query&generator=search&gsrnamespace=6&prop=imageinfo&iiprop=url\|extmetadata&iiurlwidth=800` (+ `filetype:bitmap\|drawing` in the query). Live test "human heart anatomy diagram" → three labeled heart plates with full metadata (LicenseShortName, LicenseUrl, Artist, AttributionRequired, Credit). Download `thumburl` (server-rendered PNG at requested width), never `url` (originals are often SVG). **Mandatory descriptive User-Agent** on every request incl. downloads — default python UAs get 403/blocked. |
| **Openverse** (fallback) | Usable, noisier | `GET api.openverse.org/v1/images/?q=...&license=by,by-sa,cc0,pdm`. Anonymous: 20/min, 200/day (verified live from headers) — fine at ~2 req/lesson. Ships a ready-made `attribution` string. Flickr-photo heavy: "heart anatomy" returned mugs and party photos — hence fallback, not primary. Stale provider links exist → always download-and-verify. |
| OpenStax | Free ride | No API, but its CC BY figures are uploaded to Commons ("OpenStax College") — surfaced by the Commons pipeline for free. |
| NIH Open-i | Skip | Alive, but per-result JSON has NO license fields → automated license validation impossible. |
| LibreTexts / direct Flickr | Skip | No API / redundant (Openverse indexes Flickr). |

**License policy (fail closed):** allowlist exactly CC0 / Public Domain / CC BY / CC BY-SA.
Exclude all NC and ND variants (NC is legally grey under the VerBeter umbrella; ND forbids
cropping/annotation). Match against enumerated normalized values — careless substring
matching lets "CC BY-NC-SA" pass a "CC BY" check. Attribution per the CC TASL model (Title,
Author, Source, License + link) rendered under every figure; Commons `Artist` is HTML —
strip tags before building the credit line.

## Integration (verified against the code)

- **Hook point is load-bearing:** `_generate_and_store_lesson` OVERWRITES the lesson file on
  deepen — an images field added anywhere else is silently lost on every "Rusty on this?".
  Image resolution must run inside it (after `valid_lesson`, before the atomic write). This
  covers new generations AND deepen with one hook.
- **Storage:** `content/courses/<id>/images/<lesson_id>-<n>.<ext>` (per-lesson artifact dir
  precedent: exams/, remediation/, review-items/). Needs a new `fsutil.write_bytes_atomic`
  (the existing helper is text-only and would corrupt image bytes).
- **Serving:** new `GET /api/courses/<course_id>/images/<filename>` — `_ID_RE` on course_id,
  strict filename regex `^[a-z0-9-]+-\d+\.(jpg|png|webp)$`, `send_from_directory` (blocks
  traversal), mirroring the existing static routes. Today NO route serves content/ files.
- **HTTP client:** stdlib `urllib.request` with explicit User-Agent + ~10s timeouts. The
  venv has only Flask+waitress; the backend currently makes zero outbound HTTP. No new
  dependency for two GET calls.
- **Safety:** raster only (jpeg/png/webp by magic bytes — NEVER SVG: same-origin XSS when
  served); ≤300 KB/file enforced in code; ≤640-800px thumbnails; 2-3 figures/lesson max.
  Tokens expand ONLY in promptHtml and ONLY against the lesson's own backend-verified images
  array (worst case of a spoofed token: a duplicate of an already-vetted figure); unmatched
  tokens are stripped; captions/credits esc()'d client-side.
- **Seams:** `apply_revision` needs NO change (images follow the lessons/ keep-on-revision
  precedent — pruning them would leave revived cached lessons with dangling tokens).
  Backfill = `backend/images.py` `__main__` CLI cloned from spine.py's batched pattern (one
  `run_structured` call per cached lesson proposes queries/captions/token placement; the
  resolver fetches; lesson JSON rewritten atomically). Run on the Pi, after a fresh 03:30
  backup, never during an in-flight generation.
- **Ops:** Pi has 22 GB free; content/ is 1.6 MB today. Daily backup keeps 7 tars → every MB
  of images ≈ 7 MB of backup; ~25 lessons ≈ 10-20 MB images ≈ ~100-150 MB backup impact —
  comfortable, but the caps must be code-enforced. Deploy rsync already excludes content/.
- **Generation-path resilience:** image fetching adds outbound HTTP to the ~110s generation
  path (540s ceiling) — short timeouts, fail open to a figure-less lesson; a Commons outage
  must never block a lesson.

## Learning science (what the prompt must encode)

The evidence is unusually clean: **relevant, labeled, text-adjacent images produce a medium
positive effect (multimedia effect g≈0.39, Guo 2020; signaling g≈0.3-0.5, Alpizar 2020 —
largest for low-prior-knowledge learners), while decorative images actively HURT (seductive
details meta-analysis, Sundararajan & Adesope 2020: negative effects; Mayer coherence 23/23
tests, median d≈0.86 for excluding extraneous material).** Spatial contiguity (figure beside
the paragraph it illustrates, labels on the image not in a legend): d≈0.72 (Ginns 2006).

Five prompt-encodable rules:
1. Include a figure ONLY for spatial/structural/process/quantitative content the text
   explains — never decoration; when in doubt, omit (models over-include; bias to omission).
2. Photos/realistic plates for concrete identification (anatomy, organisms, objects);
   schematics for processes and abstract relations; charts for quantitative data.
3. Every figure: labeled parts + a caption saying what to NOTICE, not a title.
4. Figure sits immediately after the paragraph that references it ("as shown in Figure 1");
   never grouped at the end (retrofit exception: backfilled figures may land at the block
   the CLI chooses).
5. Budget ≤1 figure per major concept, 1-3 per lesson, zero is often correct.

## Slice 2 future-proofing (drawn diagrams — decided now, built later)

- **Never generate raster images for diagrams:** code-generated diagrams hit ~96% label
  exact-match vs 11-19% for diffusion image models (CAGE benchmark) — for education, labels
  are everything.
- Slice 2 = **Mermaid** (vendored single-file, offline, parse-validate before render, text
  fallback on error) for flow/sequence/chart shapes + **constrained inline SVG** (fixed
  viewBox, element budget, DOMPurify svg-profile sanitized server-side before caching AND
  client-side) for labeled schematics. Known LLM-SVG failure modes: label collisions,
  out-of-viewBox coordinates — keep schematics simple; real Commons plates (slice 1) stay
  the better source for complex anatomy.
- **Decision that binds slice 1:** the lesson stores TYPED figure entries and the frontend
  renders through ONE `renderFigure()`-style path, so slice 1 ships the `web-image` arm and
  slice 2 adds `mermaid`/`svg` arms without touching lesson storage or layout.

## Recommended build (slice 1)

1. `lesson_prompt`: optional `images` field (0-3 × {query, caption}) + `[[figure:n]]` tokens,
   with the five pedagogy rules; `valid_lesson` gains an if-present shape check only.
2. `backend/images.py`: Commons-first/Openverse-fallback resolver + downloader (allowlist
   licenses, magic-byte + size validation, TASL credit assembly, fail-open), plus the
   spine-style backfill CLI.
3. `fsutil.write_bytes_atomic`; hook in `_generate_and_store_lesson`; images route in app.py.
4. `lesson.js`: token expansion into `<figure>/<figcaption>` (typed, one render path),
   esc()'d caption + credit line with license link; unmatched tokens stripped.
5. Backfill the ~25 cached lessons on the Pi (per-lesson placement call ≈ chat-message cost).

**Cost:** ~2 free API calls + a few tens of KB download per new lesson; backfill ≈ 25 small
Claude calls one-off. No new paid calls in steady state beyond what generation already does.

## Open risks (accepted / mitigated)

- Top licensed hit can be topically right but visually wrong — captions still teach;
  cheapest escape hatch later: a per-figure "swap image" action (not in slice 1).
- Openverse 200/day anon cap — backoff on 429; register OAuth only if usage grows.
- Model may over-conservatively omit figures given the strict rules — watch the first
  generations, tune the prompt bias if lessons stay bare.
