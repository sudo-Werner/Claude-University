# Accredited Sources / "Real Academic Institution" — Design Spec

**Goal:** make it visible where a course's teaching comes from, grounded in REAL,
accredited/authoritative sources retrieved via web search — not model-recalled citations.
Werner's framing: "mimic a real academic institution, try to get accredited sources."

**Chosen scope (Werner, 2026-07-01):** BOTH, PHASED. Phase 1 = a course-level "Library"
(accredited bibliography) shown as the visible overview. Phase 2 = per-lesson grounding
(each lesson cites the real sources it used; roll up into the Library).

## Feasibility (spiked + confirmed on the Pi, 2026-07-01)
- The Max-subscription `claude -p` DOES web-search headlessly with
  `--allowedTools WebSearch WebFetch --output-format stream-json --verbose`. ~51s for a
  search pass (well within the 240s timeout).
- The stream carries `web_search_result` items as clean `{title, url}` pairs — captured
  from the ACTUAL search, so real (no hallucinated URLs). A `result` event carries the
  final text (our JSON).
- Sources returned with zero extra steering were already accredited: Stanford CS229/CS231n
  course pages, arXiv, Springer textbook chapter, PubMed Central (NCBI), HAL. Good.
- Caveat: a `rate_limit_event` appeared — the Max web-search budget is finite, so grounding
  EVERY lesson (Phase 2) uses it faster than one pass per course (Phase 1).

## The trust guarantee (why this is honest)
Displayed sources = the INTERSECTION of (a) what Claude cites in its JSON and (b) the
`{title,url}` set actually captured from the web-search results. Any URL Claude emits that
was NOT in the real search results is dropped. So every link shown was genuinely retrieved.
Accreditation `type` is derived from the URL's domain SERVER-SIDE (reliable), not trusted
from the model:
- `*.edu`, university course domains (stanford/mit/berkeley/ox.ac.uk…) → **University**
- `arxiv.org`, `*.nih.gov`/ncbi, `hal.*`, `*.acm.org`, `*.ieee.org`, doi.org → **Peer-reviewed**
- `link.springer.com`, `oreilly.com`, `cambridge.org`, `oup.com`, `manning.com` → **Textbook**
- official docs domains (`docs.*`, `*.org` project docs, python.org, pytorch.org…) → **Official docs**
- otherwise → **Reference** (still shown, lower-tier badge)

## Phase 1 — Course Library (build first)

### Backend
- **`claude_client.run_sourced(prompt, *, validate=None, model=DEFAULT_MODEL, runner=_spawn_cli)`**
  — runs the CLI with WebSearch/WebFetch + `stream-json --verbose`, collects (1) all
  `web_search_result` `{title,url}` pairs and (2) the final `result` text → `extract_json`.
  Returns `(obj, captured_sources)`. Same auth-failure detection (`api_error_status` 401/403)
  and one JSON-retry as `run_structured`. Restricted to `--allowedTools WebSearch WebFetch`
  so the model can't wander into other tools.
- **`generation.bibliography_prompt(*, title, brief, module_titles)`** — instructs Claude to
  web-search the subject and return ONLY JSON `{"sources":[{"title","url","note"}]}` of the
  most authoritative, accredited sources it FOUND (prefer university course material,
  peer-reviewed papers, official docs, established textbooks). `note` = one line on what it
  covers. (No `type` from the model — we derive it.)
- **`generation.valid_bibliography(obj)`** — `sources` is a 3–12 item list; each has non-blank
  `title`, an `http(s)` `url`, non-blank `note`.
- **`generation.source_type(url)`** — domain → type per the table above.
- **`generation.ensure_bibliography(content_dir, course_id, *, generate_sourced)`** — like
  `ensure_capstone`: cache at `content/courses/<id>/library.json`. On miss: build the prompt
  from the manifest, call `generate_sourced` → `(obj, captured)`, **filter** `obj.sources` to
  those whose normalized `url` ∈ captured set, attach derived `type`, sanitize `title`/`note`
  (`sanitize_html`) + validate url scheme, sort by type rank, store, return
  `{courseId, title, sources:[{title,url,type,note}]}`.
- **`app.py`: `GET /api/courses/<cid>/library`** → `ensure_bibliography`; reauth 503
  `{code:"reauth"}` / ClaudeError 502 / missing course 404. (Generation via
  `claude_client.run_sourced(prompt, validate=generation.valid_bibliography)`.)

### Frontend
- **`courses.js`: `loadLibrary({fetch, courseId})`** → library or `{error}`.
- **`views/library.js`: `libraryHTML(library)`** — an academic bibliography: grouped by type
  (University → Peer-reviewed → Textbook → Official docs → Reference), each entry = title as a
  real clickable link (`target=_blank rel="noopener noreferrer"`, href `esc`'d), a type badge,
  and the note. Header explains: "Accredited sources this course draws on — retrieved from the
  web, not invented."
- **`app.js`:** a `library` screen + `showLibrary()` (loading skeleton via `startLoading`,
  nav guard), reached from a **"Library" button on the course dashboard** (next to "View all
  lessons") so it's visible right after a course is created.
- **`styles.css`:** bibliography list + `.src-badge` per type.

### Tests
- backend: `valid_bibliography`, `source_type` (domain→type table), `bibliography_prompt`,
  `ensure_bibliography` (URL-intersection filter drops model URLs not in captured set;
  caching; sanitization), `run_sourced` (parses captured sources + final JSON from a fake
  stream), route (200/reauth/404).
- frontend: `loadLibrary` fetch+error; `libraryHTML` grouping/links/badges; escaping.

### Verify (Pi)
Create a course, open its Library, confirm real accredited links resolve and are grouped/typed.

## Phase 2 — Per-lesson grounding (build after Phase 1 is verified)
- Lesson generation switches (or gains a sourced path) to `run_sourced`; capture the real
  sources per lesson via the same intersection guarantee; store `sources` on the lesson JSON;
  render a "Sources" section on the lesson; **deepen** re-grounds.
- The course Library becomes the DEDUPED ROLL-UP of every lesson's sources (plus/instead of
  the Phase-1 subject bibliography — decide at Phase 2 time).
- Weigh the rate-limit/latency cost (+~30–50s per lesson) once Phase 1 shows real usage.

## Explicitly deferred / not now
- HEAD-validating each URL (they're already live search hits; add only if we see dead links).
- Ranking/curation beyond type grouping; per-source excerpts/quotes; offline caching of source
  content. YAGNI until asked.
