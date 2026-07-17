# Vendored frontend libraries

Pinned, committed, no CDN at runtime (spec: `docs/superpowers/specs/2026-07-17-drawn-diagrams-design.md`, decisions 2 and 3).

- **mermaid.min.js** — v11.16.0 — `https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.min.js` — pinned 2026-07-17
- **purify.min.js** (DOMPurify) — v3.4.12 — `https://cdn.jsdelivr.net/npm/dompurify@3.4.12/dist/purify.min.js` — pinned 2026-07-17

To update: re-run the `curl` commands above with a newer version pin, verify the new
file's size floor and marker string (see `tests/test_static.py`), update the version
and date in this file, then commit both together.
