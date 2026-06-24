# Real-World Evidence Capstone (Post-Roadmap Feature: #1) — AS BUILT

## Vision
When a learner finishes a module (or the whole course), show a short "real-world
connections" capstone — concrete systems/products/research/events where the concepts
they just studied show up — to solidify understanding. Review item #1.

## The link-integrity decision (the one real fork)
LLM-generated *direct URLs* frequently 404 or are fabricated, which would poison
"evidence." So the model supplies, per item, a **title + detail + a source NAME**
(e.g. "Wikipedia", "NumPy docs") — never a URL. The frontend builds the "Explore →"
link as a **live web search** (`https://duckduckgo.com/?q=<title source>`). Always
resolves, zero hallucinated/dead links, still one click to real evidence.
*Revisit later if Werner wants validated direct links (would need server-side URL
checking + an SSRF guard).*

## Scope & decisions
- **Two scopes:** a module capstone (scope = module id, e.g. `m1`) and a course
  capstone (scope = `"course"`), sharing one mechanism.
- **Surfaced in the curriculum** ("View all lessons"): a "Real-world connections →"
  button appears under each fully-complete module, and a course-wide one once every
  lesson is done. (Single integration point; not the dashboard.)
- **Generated on first open, cached** at `content/courses/<cid>/capstones/<scope>.json`
  — same just-in-time + cache pattern as lessons. One Claude call per scope, once.
- 3–5 items; intro + items required; each item needs title, detail, source.

## Backend (`backend/generation.py`, `backend/app.py`)
- `valid_capstone(obj)` — intro non-blank; 2–6 items; each with non-blank title/detail/source.
- `capstone_prompt(*, scope_label, scope_title, concept_titles, brief, profile)` — asks for
  real, recognizable examples and a source NAME (not a URL).
- `ensure_capstone(content_dir, course_id, scope, profile, *, generate)` — cache hit returns;
  else loads the manifest, derives scope_title + concept_titles (module → its lesson titles;
  course → module titles), generates, validates, **sanitizes** (`sanitize_html` on intro +
  item detail; `_html.escape` on item title/source), reconciles scope/title, caches. `None`
  for an unknown module.
- `GET /api/courses/<cid>/capstone/<scope>` — `_ID_RE` on course id; scope must be `"course"`
  or match `_ID_RE` (also blocks path traversal in the cache filename). reauth 503 /
  ClaudeError 502 / None 404.

## Frontend
- `frontend/src/courses.js`: `loadCapstone({fetch, courseId, scope})`.
- `frontend/src/views/capstone.js`: `capstoneHTML(capstone)` — intro + items; "Explore →"
  link built from `htmlDecode(title) + htmlDecode(source)` → DuckDuckGo search (decode so
  escaped `&` in a name isn't double-encoded). `capstone.title` (raw) is `esc()`'d.
- `frontend/src/views/curriculum.js`: per-complete-module + course-complete `data-capstone`
  buttons.
- `frontend/src/app.js`: `showCapstone(scope)` screen (loading card, navigation guard,
  logs `capstone_opened`); curriculum wires `data-capstone` clicks.
- `frontend/styles.css`: `.c-capstone` + `.cap-*` styles.

## Test coverage (shipped)
- `tests/test_generation.py`: valid_capstone (incl. missing-source reject), capstone_prompt,
  ensure_capstone module + course scope (caching, sanitization, unknown module None).
- `tests/test_courses_api.py`: module + course scope, unknown module 404, reauth 503.
- `frontend/tests/courses.test.js`: loadCapstone fetch + error shape.
- `frontend/tests/views.test.js`: capstone buttons only on completed modules/course,
  capstoneHTML rendering, explore-link entity decoding.

## Verified
Pi e2e (Tailscale, throwaway course): a completed "Foundations of Addition" module
produced 5 real connections (CPU ALU, Excel SUM, double-entry accounting, Google Maps
distance, NumPy) with working search-based Explore links. Both module and course
capstone buttons appeared at the right completion thresholds.
