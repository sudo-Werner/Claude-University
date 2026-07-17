# Lesson images — real, licensed, locally cached figures — design

**Date:** 2026-07-17. **Status:** approved direction (Werner 01:30 "go ahead" after the deep
dive `docs/research/2026-07-17-lesson-images-deep-dive.md` and the doubled-budget decision).
Slice 1 of the graphics wave (slice 2 = Claude-drawn Mermaid/SVG diagrams, later, own cycle).

## Goal

Lessons carry real images — anatomy plates, ML diagrams, charts — as proper figures with
captions and credit lines. Claude decides *what* would help and writes the caption; the
backend deterministically finds, license-checks, downloads, and caches the file from open
archives; Claude then *looks at* the candidates and picks the best one (the doubled-budget
vision check). Images serve from the Pi itself: no third-party requests from the browser, no
link rot, works offline. Existing ~25 cached lessons get retrofitted by a one-off CLI; every
new generation and deepen gets figures automatically.

**Cost shape:** per new lesson, ~2 free archive-API calls + a few small downloads + ONE
Claude vision call (thumbnails attached). Backfill ≈ 25 × (one placement call + one vision
call), one-off. Steady state adds roughly one chat-message-class call per generated lesson.

## Decisions

1. **The model never picks URLs.** Lesson generation emits an optional `images` field —
   0-3 slots of `{"query": "<discriminating archive search terms>", "caption": "<one
   sentence saying what to NOTICE>"}` — and places a plain-text token `[[figure:1]]`
   (`[[figure:2]]`, `[[figure:3]]`) in `promptHtml` immediately after the paragraph each
   figure illustrates (verified: `sanitize_html` passes these tokens through verbatim).
   `valid_lesson` gains an **if-present** shape check only (list of ≤3 dicts with non-empty
   string `query` and `caption`) — absent field stays valid, cached lessons unaffected.
2. **Pedagogy rules in the prompt** (evidence-cited in the deep dive): figures only for
   spatial/structural/process/quantitative content the text explains — never decorative,
   bias to omission ("zero images is often correct"); photos/realistic plates for concrete
   identification, schematics for processes, charts for data; caption states what to notice;
   token goes right after the referencing paragraph and the text references the figure;
   ≤1 per major concept, ≤3 per lesson.
3. **Deterministic resolver — new `backend/images.py`.** For each slot, in order:
   - **Wikimedia Commons first**: `action=query&generator=search&gsrsearch=<query>
     filetype:bitmap|drawing&gsrnamespace=6&gsrlimit=8&prop=imageinfo&iiprop=url|extmetadata
     &iiurlwidth=800&iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|AttributionRequired
     |Credit|UsageTerms&format=json`. Candidates come from `thumburl` (server-rendered
     raster at 800px), never `url` (originals are often SVG).
   - **Openverse fallback** when Commons yields <2 license-valid candidates:
     `GET https://api.openverse.org/v1/images/?q=<query>&license=by,by-sa,cc0,pdm&page_size=8`
     (thumbnail via the Openverse thumb proxy; on 429 back off and skip — never retry-loop
     against the 200/day anonymous cap).
   - **License allowlist, fail closed**, matched against enumerated normalized values —
     Commons `LicenseShortName` values equal to (case-insensitive) `Public domain`, `CC0`,
     or starting with exactly `CC BY ` / `CC BY-SA ` (space-terminated so `CC BY-NC…` and
     `CC BY-ND…` can never pass); Openverse `license` in `{cc0, pdm, by, by-sa}`. Anything
     else — including every NC and ND variant — is rejected.
   - **Download + verify** with stdlib `urllib.request` (no new dependency): mandatory
     descriptive User-Agent `ClaudeUniversity/1.0 (personal learning app;
     wernerpvanellewee@gmail.com)` on EVERY request including downloads (Wikimedia policy —
     default UAs get 403), ~10 s timeout per request, response must be HTTP 200 with
     jpeg/png/webp **magic bytes** (never trust extension or Content-Type; **SVG is
     rejected outright** — same-origin XSS), ≤400 KB per file. Up to 4 verified candidates
     per slot land in a `tempfile.mkdtemp` scratch dir.
4. **Vision pick (the doubled-budget stage).** One `claude_client` structured call per slot
   with the candidate thumbnails readable on disk: the prompt names the lesson topic, the
   slot's caption, and the candidate file paths, and instructs Claude to Read them, then
   reply with ONLY `{"pick": <1-based index or null>, "reason": "<one sentence>"}`.
   `run_structured` gains an optional `tools` parameter (passed as `--allowedTools`; used
   here with `["Read"]` only). Semantics:
   - valid `pick` → that candidate's file moves (atomically) to the final path; the rest are
     deleted;
   - explicit `null` → **drop the figure** (an informed "none of these fit" beats a bad
     image);
   - call failure (ClaudeError/timeout/unparseable) → **fail open to the first candidate**
     (the deterministic baseline is never worse than the pre-vision design).
5. **Storage + resolved shape.** Files at `content/courses/<course_id>/images/
   <lesson_id>-<n>.<jpg|png|webp>` written via a new `fsutil.write_bytes_atomic` (the
   text-only helper would corrupt bytes). After resolution the lesson's `images` entries are
   REWRITTEN to `{"n": <int>, "type": "web-image", "file": "<lesson_id>-<n>.<ext>",
   "caption": <str>, "credit": <plain-text TASL line — HTML stripped from Commons Artist>,
   "license": "<short name>", "licenseUrl": <str|null>, "sourceUrl": "<file page or
   foreign_landing_url>"}`. `type` is the slice-2 seam: drawn-diagram arms add new types
   without touching storage or layout. Slots that resolved to nothing are removed and their
   tokens stripped from `promptHtml`.
6. **Hook point: inside `_generate_and_store_lesson`**, after `valid_lesson` passes and
   before the atomic write — the ONLY placement that covers cache-miss generation AND deepen
   (deepen overwrites the lesson file wholesale; images resolved anywhere else would
   silently vanish on every "Rusty on this?"). The whole image stage **fails open**: any
   exception → lesson stored without that figure (token stripped); an archive outage can
   never block or fail a lesson. Injected as a callable default (`resolve_images=`) so tests
   monkeypatch it the way `generate`/`verify_generate` already work.
7. **Serving route:** `GET /api/courses/<course_id>/images/<filename>` — `_ID_RE` on
   course_id, filename must match `^[a-z0-9-]+-\d\.(jpg|png|webp)$`, then
   `send_from_directory(CONTENT_DIR / course_id / "images", filename)` (traversal-safe,
   mirrors the existing static routes). 404 on any mismatch. No directory listing.
8. **Frontend rendering (`lesson.js`)**: a pure pre-render transform expands `[[figure:n]]`
   tokens — **only in `promptHtml`**, **only against the lesson's own `images` array**, and
   only for entries with `type === "web-image"` (unknown types render nothing until their
   slice ships) — into:
   `<figure class="lesson-fig"><img src="/api/courses/<cid>/images/<file>" alt="<esc(caption)>"
   loading="lazy"><figcaption>${esc(caption)} <span class="fig-credit">${esc(credit)}
   <a href="${esc(licenseUrl or sourceUrl)}" target="_blank" rel="noopener noreferrer">
   ${esc(license)}</a></span></figcaption></figure>`.
   Unmatched or duplicate-spoofed tokens are stripped (worst case of a token typed in chat:
   nothing — chat text is esc()'d and never token-expanded). Entries whose token never
   appears in `promptHtml` (retrofit case) render in a "Figures" block after the prose.
   Filename is esc()'d and additionally regex-checked client-side before building the src.
9. **Backfill CLI** — `python -m backend.images <course_id>|--all` on the Pi, cloned from
   `spine.py`'s batched `__main__` pattern: for each cached lesson without images, ONE
   `run_structured` call reads the existing lesson and proposes `{images: [{query,
   caption}], promptHtml}` where `promptHtml` is the EXISTING html with tokens inserted
   (validator asserts the html is unchanged apart from inserted `[[figure:n]]` tokens — the
   backfill must never rewrite prose); then the same resolver + vision pick runs; the lesson
   JSON is rewritten via `write_text_atomic`. Procedural guards: run only after the 03:30
   backup has produced a fresh tar, and never while `pgrep` shows an in-flight generation.
10. **`apply_revision` unchanged.** Image files follow the `lessons/` keep-on-revision
    precedent: pruning them would leave a revived cached lesson with dangling tokens.
11. **Caps are code, not convention:** ≤3 figures/lesson, ≤400 KB/file, 800 px thumbnails,
    ≤8 search results examined and ≤4 candidates downloaded per slot, ~10 s per HTTP
    request, and the whole image stage wrapped so it cannot push a generation past its
    540 s stream ceiling (resolver total budget ≤120 s per lesson; on overrun: fail open).

## Error handling

- No license-valid candidate / all downloads fail / vision says none → figure dropped, token
  stripped, lesson ships. Never a broken `<img>`, never a 4xx/5xx from the image stage.
- Openverse 429 → skip fallback this slot (no retry loop against the daily cap).
- Vision-call failure → first candidate (deterministic baseline).
- Serving route: unknown/malformed filename → 404 JSON error shape like sibling routes.
- Frontend: missing file (manually deleted) → the `<img>` alt text + caption still render;
  no JS error.

## Security

- The model supplies only search TEXT and captions; every URL the system touches comes from
  archive APIs the backend queried itself; every served byte was downloaded, magic-byte
  verified, size-capped, and stored by the backend. SVG never accepted.
- Tokens expand only in `promptHtml` against backend-written `images` entries; captions,
  credits, filenames, and license strings are esc()'d at render; Commons `Artist` HTML is
  tag-stripped server-side before storage.
- Serving route is `_ID_RE` + strict-filename + `send_from_directory` (no traversal).
- The vision call reads only files the backend just wrote into a scratch dir it created.
- Tests never call live archive APIs or Claude: the resolver takes injectable `http_get` /
  `structured` callables; fixtures use canned Commons/Openverse JSON and tiny real
  jpeg/png/webp byte strings (and an SVG/oversize/wrong-magic set for rejection tests).

## Testing

- **Backend**: slot shape validation (if-present rule; >3 slots invalid; cached lessons
  without images untouched); Commons parsing incl. license allowlist edge cases
  (`CC BY-NC-SA 4.0` REJECTED, `CC BY-SA 3.0` accepted, `Public domain` accepted); Openverse
  fallback + 429 skip; magic-byte checks (SVG bytes rejected even named .png; >400 KB
  rejected); vision pick semantics (pick / null / failure→first); token stripping for
  dropped slots; `_generate_and_store_lesson` integration (fail-open on resolver exception;
  deepen path re-resolves; file written under images/); serving route (200 + correct
  mimetype, 404s for traversal/regex violations); backfill validator (prose-unchanged
  assertion catches a rewritten promptHtml); `write_bytes_atomic` (bytes intact, tmp
  cleaned).
- **Frontend**: token expansion happy path (figure + caption + credit + license link,
  esc()'d XSS cases for caption/credit/filename); token in chat text NOT expanded; unmatched
  token stripped; tokenless images render in the Figures block; unknown `type` renders
  nothing; import-resolution check.

## Deploy notes

Standard DEPLOY.md (never `--delete`; content/ excluded — cached images live only on the Pi
and are covered by the daily backup tar). No new pip dependencies. Deploy the feature FIRST,
verify health + a no-op lesson GET, then run the backfill CLI on the Pi (post-backup,
pgrep-clean). Backfill is resumable (lessons already carrying `images` are skipped). After
backfill: spot-check `du -sh content/`, one retrofitted lesson GET, and the backup size next
morning.

## Out of scope

- Slice 2: Mermaid/SVG drawn diagrams (typed `type` field is the only slice-1 concession).
- A per-figure "swap image" UI action (escape hatch if a picked image disappoints — ticket).
- Openverse OAuth registration (only if usage ever nears the anonymous cap).
- Images in exams, remediation, review items, capstones, or the bibliography.
- Any hotlinking mode.
