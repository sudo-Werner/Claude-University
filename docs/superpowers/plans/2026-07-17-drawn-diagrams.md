# Drawn Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Where a lesson's concept is best shown as a *drawn* figure — a process flowchart, a sequence, a simple chart, a labeled schematic — Claude draws it itself, as code: Mermaid for anything graph/flow/chart-shaped, constrained inline SVG for labeled spatial schematics, riding the existing lesson-generation call (zero extra Claude calls).

**Architecture:** The slice-1 typed-figure pipeline (`images` slots, `[[figure:n]]` tokens, one resolver hook in `_generate_and_store_lesson`, one render path in `lesson.js`) gains two new slot types alongside `web-image`. A new stdlib-only allowlist sanitizer (`backend/figures.py`) cleans Claude-authored SVG server-side before it is ever cached; mermaid code needs no server-side transform (it never touches learner input and renders under `securityLevel: "strict"` client-side). The generation hook splits a lesson's slots by type: svg/mermaid are processed locally (no network), web-image slots alone go to the existing `resolve_images` resolver — a shared `images.process_slots` function (reused by both the hook and the backfill CLI) does this split so the logic exists in exactly one place. The frontend renders svg/mermaid as inert placeholders (never string-interpolating figure code into the HTML template) and hydrates them after paint via two vendored, lazy-loaded, pinned libraries (`mermaid.min.js`, `purify.min.js`) — DOMPurify sanitizes SVG a second time client-side, mermaid renders under strict security with a caption-as-text fallback on any error.

**Tech Stack:** Python stdlib `xml.etree.ElementTree` (no new pip dependency); existing Flask app/routes; vendored, pinned `mermaid.min.js` (11.16.0) and `purify.min.js`/DOMPurify (3.4.12) — no CDN, no new npm dependency; existing vanilla-JS ES-module frontend; existing `pytest` / `node:test` test runners.

**Spec:** `docs/superpowers/specs/2026-07-17-drawn-diagrams-design.md` — the single source of requirements (slice 2 of the graphics wave; context: `docs/superpowers/specs/2026-07-17-lesson-images-design.md`, slice 1, ALREADY MERGED — its typed-figure pipeline is what this plan extends; `docs/research/2026-07-17-lesson-images-deep-dive.md` section "Slice 2 future-proofing" and "Learning science" inform the pedagogy rules). Implement exactly what the design spec says, nothing extra.

## Ambiguity resolutions

Details the spec left to this plan, resolved by reading the real (already-merged) code and verified by actually running the resulting code in a scratch worktree before writing these steps down (see the report accompanying this plan for the verification tally):

1. **Original slot number `n` is preserved by padding, not by changing `resolve_images`'s signature.** The spec/task text offered two options ("(n, slot) pairs or a parallel indices list"); a third, simpler option needs NO signature change at all: `resolve_images`'s existing loop is `for i, slot in enumerate(slots[:MAX_SLOTS], start=1): ... if not isinstance(slot, dict): continue`. Building a `web_image_slots` list the SAME LENGTH as the original slots, with every non-web-image position set to `None`, means the existing positional `enumerate` already assigns each surviving web-image slot its correct original `n` — `resolve_images` already skips `None` (not a dict). Verified: none of the 7 existing direct `resolve_images(...)` calls in `tests/test_images.py` needed to change, and a scratch integration test confirmed `n` survives correctly when slot 1 is svg, slot 2 is mermaid, and slot 3 is web-image.
2. **The shared drawn-figure prompt-guidance text (`DRAWN_FIGURE_GUIDANCE`) lives in `backend/figures.py`, not `backend/generation.py` or `backend/images.py`.** Both `generation.py`'s `_IMAGES_BLOCK` and `images.py`'s `backfill_prompt` need the identical guidance ("same guidance as _IMAGES_BLOCK" per the task). `images.py` already needs `figures.sanitize_svg`, and `generation.py` already imports `images` — if the guidance text lived in `generation.py`, `images.py` would need to import `generation.py` back, creating a circular import (`generation` → `images` → `generation`). `figures.py` has no dependents importing back into it, so it is the one place both can import from without a cycle.
3. **`images.process_slots`'s injectable resolver parameter is named `resolve_images_fn`, not `resolve_images`.** Naming it `resolve_images` would shadow the module-level `resolve_images` function inside `process_slots`'s own body, making the "use the real resolver when no override is given" fallback (`resolve_images_fn or resolve_images`) impossible to write cleanly.
4. **The injected-resolver calling convention stays exactly `resolver(course_id, lesson_id, slots, content_dir=content_dir)`** — no `http_get`/`structured` passthrough — identical to slice 1's existing hook convention. This means every existing `fake_resolver(course_id, lesson_id, slots, *, content_dir)` test double in `tests/test_generation.py` keeps working completely unmodified.
5. **`sanitize_svg` rejects `xlink:href` by comparing the attribute's resolved namespace URI** (`http://www.w3.org/1999/xlink`) rather than string-matching the literal prefix `xlink:href` — this also catches any other `xlink:*` attribute and is robust to whatever namespace prefix alias the input XML happens to declare (`xmlns:foo="http://www.w3.org/1999/xlink"` would still be caught).
6. **Root `width`/`height` rejection is a separate explicit check, run BEFORE the generic attribute-allowlist walk.** `width`/`height` are legitimately allowlisted attributes for child shapes (`rect`, etc.), so the allowlist alone cannot distinguish "the root svg element" from "any element" — this is exactly the case the spec calls out explicitly.
7. **`app.js`'s new `hydrateFigures`/`loadScript`/`loadPurify`/`loadMermaidLib` helpers use the closure's injected `window`/`doc`** (from `init({window, fetch})`), never the bare global `window`/`document` — matching every other DOM access already in this file (`doc.createElement`, `window.setInterval`, etc.).
8. **Vendored library versions are pinned to the exact resolved jsdelivr version at plan-verification time** (`mermaid@11.16.0`, `dompurify@3.4.12`, confirmed via `x-jsd-version` response headers on a HEAD request against the `@11`/`@3` floating tags on 2026-07-17), not left as floating tags — a floating tag would make a future redeploy silently pull a different, unverified file.
9. **The pre-existing frontend regression test "renders nothing for an unknown figure type" used `type: "mermaid"` as its example** (correct in slice 1, since mermaid didn't exist yet). Now that mermaid is a known, rendered type, that test is repointed to a genuinely unknown type (`"carousel"`) so it keeps testing what it always meant to test — this is the ONE existing test this plan modifies (verified: it is the only test that breaks when the mermaid arm is added; the other 264 existing frontend tests pass unmodified).
10. **New backend test files/append points follow slice 1's precedent**: `tests/test_figures.py` is new (mirrors `tests/test_images.py`'s placement at the repo root, not `backend/tests/`); new tests append to `tests/test_generation.py` and `tests/test_images.py`.

## Global Constraints

Every task's requirements implicitly include this section. Every value below is copied verbatim from the binding spec.

- SVG element allowlist, exactly: `svg g rect circle ellipse line polyline polygon path text tspan title defs marker`.
- SVG attribute allowlist, exactly: `viewBox x y x1 y1 x2 y2 cx cy r rx ry width height d points transform fill stroke stroke-width stroke-dasharray font-size font-family font-weight text-anchor dominant-baseline opacity fill-opacity marker-end marker-start id class`.
- SVG sanitizer REJECTS (returns `None`, never repairs): any non-allowlisted element or attribute, any `on*` attribute, `href`/`xlink:href` anywhere, `style` elements or attributes, unparseable XML, a root missing `viewBox`, a root carrying `width` or `height` (CSS sizes it — width/height stay allowed on non-root shapes like `rect`).
- SVG input size cap: ≤8 KB (`8 * 1024` bytes, measured on the UTF-8 encoded input).
- Figure code cap (mermaid and svg `code` field): non-empty string, ≤8192 characters.
- Lesson-level figure budget: ≤3 slots (`images` list length ≤3) — unchanged from slice 1.
- Figure-type guidance (prompt copy, decision 1): concrete identification → `web-image`; process/flow/sequence/hierarchy/timeline → `mermaid`; labeled spatial schematic mermaid cannot express → `svg` (≤ ~25 elements); quantitative → `mermaid` `xychart-beta`/`pie`; prefer `web-image` when a drawing would be too complex to draw clearly in code.
- SVG authoring constraints (decision 4), exactly: fixed `viewBox="0 0 800 500"`; every part labeled with a `<text>` element INSIDE the drawing (no legend); font-size at least 14px; simple flat colors that read on a light card.
- Drawn-figure credit line, exactly: `Drawn by Claude` (replaces the license line web-image figures carry).
- Mermaid render config, exactly: `mermaid.initialize({ startOnLoad: false, securityLevel: "strict" })`.
- DOMPurify sanitize call, exactly: `DOMPurify.sanitize(code, { USE_PROFILES: { svg: true, svgFilters: true } })`.
- SVG is double-sanitized: the server-side allowlist (`figures.sanitize_svg`) runs once at generation/cache time; DOMPurify runs again client-side at render time. Neither layer is optional.
- Mermaid render failure → caption-as-text fallback (the figcaption is already in the placeholder; nothing else is injected). SVG rejected server-side → figure dropped, its token stripped, same fail-open contract as slice 1's web-image resolver.
- Vendored files, pinned, committed under `frontend/vendor/` (create the directory), no CDN at runtime: `mermaid.min.js` (11.x, pinned to `11.16.0`, from `https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.min.js`) and `purify.min.js` (3.x, pinned to `3.4.12`, from `https://cdn.jsdelivr.net/npm/dompurify@3.4.12/dist/purify.min.js`).
- Vendor serving route: `GET /vendor/<path:filename>` → `send_from_directory(frontend_dir / "vendor", filename)`, mirroring the existing `/src/<path:filename>` route.
- Placement tokens, budget, and per-type `valid_lesson` shape rules reuse slice 1's mechanics unchanged: `[[figure:1]]`, `[[figure:2]]`, `[[figure:3]]`; ≤3 slots.
- No new pip dependencies — `xml.etree.ElementTree` is stdlib. No new npm dependencies — both frontend libraries are vendored static files.
- Backend tests: `.venv/bin/pytest -q` from repo root (tests live in `tests/`). Frontend tests: `node --test frontend/tests/*.test.js` — the explicit glob is required, a bare directory silently runs nothing.
- After any `frontend/src/app.js` change, run the import-resolution check: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` (app.js is not unit-tested by repo convention).
- Tests NEVER call live archive APIs or the real Claude CLI, and NEVER call a live CDN — every network-adjacent dependency is injectable or a committed local file. The vendoring `curl` commands in Task 2 Step 1 are a one-time implementer step, not a test.
- `apply_revision` is NOT touched — diagram code lives in the lesson JSON like every other field and follows slice 1's existing keep-on-revision precedent.
- Workspace/chat surfaces are untouched — diagrams render in lesson bodies only.
- No emojis anywhere. No refactors or renames outside what this plan specifies.
- One commit per task. Commit messages follow this repo's existing style (`feat(figures): ...` / `feat(images): ...` / `test(...): ...`), each ending with the line:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Backend — SVG sanitizer + typed slot shapes (`backend/figures.py`, `backend/generation.py`)

**Files:**
- Create: `backend/figures.py`
- Modify: `backend/generation.py` — imports (line 7); `valid_images` (lines 208-224); `_IMAGES_BLOCK` (lines 292-307); the resolver hook inside `_generate_and_store_lesson` (lines 1272-1285)
- Test: `tests/test_figures.py` (new)
- Test: `tests/test_generation.py` (append)

**Interfaces:**
- Consumes: `backend.images.resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=_http_get, structured=_default_structured, deadline_seconds=120)` — used AS-IS, unmodified (it already skips non-dict entries in `slots`, which this task relies on — see Ambiguity Resolution 1). `backend.claude_client.ClaudeError`.
- Produces: `figures.sanitize_svg(code) -> str | None`; `figures.ALLOWED_ELEMENTS`, `figures.ALLOWED_ATTRS`, `figures.MAX_INPUT_BYTES` (constants); `figures.DRAWN_FIGURE_GUIDANCE` (str — Task 2's `images.backfill_prompt` appends this same constant); `generation.valid_images` (extended to accept typed slots — Task 2/3 rely on this being the single source of truth for slot-shape validity); `generation._IMAGES_BLOCK` (extended additively); the hook inside `_generate_and_store_lesson` now stores typed entries `{"n": <int>, "type": "svg"|"mermaid", "code": <str>, "caption": <str>}` for drawn figures alongside the existing web-image entry shape — this is the data contract Task 3's frontend renders against. (Task 2 will further refactor this hook's internals to call a new shared `images.process_slots`, but must not change its external behavior or this shape.)

- [ ] **Step 1: Write the failing `backend/figures.py` test suite**

Create `tests/test_figures.py`:

```python
from backend import figures


def test_sanitize_svg_accepts_labeled_schematic_canonical_output():
    src = ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
           'fill="#eee" stroke="#333"/><text x="20" y="35" font-size="14">Pump</text></svg>')
    out = figures.sanitize_svg(src)
    assert out == ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
                    'fill="#eee" stroke="#333" /><text x="20" y="35" font-size="14">Pump</text></svg>')


def test_sanitize_svg_strips_default_xmlns_from_output():
    src = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">'
           '<g><circle cx="50" cy="50" r="20" fill="#fff"/>'
           '<text x="30" y="80" font-size="14">Valve</text></g></svg>')
    out = figures.sanitize_svg(src)
    assert "xmlns" not in out
    assert out == ('<svg viewBox="0 0 800 500"><g><circle cx="50" cy="50" r="20" fill="#fff" />'
                    '<text x="30" y="80" font-size="14">Valve</text></g></svg>')


def test_sanitize_svg_rejects_script_element():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><script>alert(1)</script></svg>') is None


def test_sanitize_svg_rejects_foreignobject():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><foreignObject><div>x</div></foreignObject></svg>') is None


def test_sanitize_svg_rejects_onclick_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect onclick="alert(1)" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_href():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><a href="https://evil.example"><rect width="10" height="10"/></a></svg>') is None


def test_sanitize_svg_rejects_xlink_href():
    src = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'viewBox="0 0 800 500"><rect xlink:href="evil.png" width="10" height="10"/></svg>')
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_style_element():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><style>rect{fill:red}</style><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_style_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect style="fill:red" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_missing_viewbox():
    assert figures.sanitize_svg('<svg><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_root_width_or_height():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500" width="800"><rect width="10" height="10"/></svg>') is None
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500" height="500"><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_allows_width_height_on_non_root_elements():
    out = figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>')
    assert out == '<svg viewBox="0 0 800 500"><rect width="10" height="10" /></svg>'


def test_sanitize_svg_rejects_oversize_input():
    big = '<svg viewBox="0 0 800 500">' + ('<g></g>' * 3000) + '</svg>'
    assert len(big.encode("utf-8")) > figures.MAX_INPUT_BYTES
    assert figures.sanitize_svg(big) is None


def test_sanitize_svg_rejects_unparseable_xml():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect></svg>') is None


def test_sanitize_svg_rejects_non_svg_root():
    assert figures.sanitize_svg('<div viewBox="0 0 800 500"></div>') is None


def test_sanitize_svg_rejects_disallowed_element_and_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><use href="#x"/></svg>') is None
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect cursor="pointer" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_empty_or_non_string():
    assert figures.sanitize_svg("") is None
    assert figures.sanitize_svg(None) is None
    assert figures.sanitize_svg("   ") is None


def test_drawn_figure_guidance_mentions_both_types_and_authoring_rules():
    g = figures.DRAWN_FIGURE_GUIDANCE
    assert '"type": "mermaid"' in g
    assert '"type": "svg"' in g
    assert 'viewBox="0 0 800 500"' in g
    assert "14px" in g
    assert "~25 elements" in g
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_figures.py -q`
Expected: `ModuleNotFoundError: No module named 'backend.figures'` (or `ImportError`).

- [ ] **Step 3: Implement `backend/figures.py`**

Create `backend/figures.py`:

```python
"""Strict allowlist SVG sanitizer for Claude-authored diagrams — server side, run once
at generation time before a lesson is cached. Never repairs: any forbidden element,
forbidden attribute, missing viewBox, a width/height on the root, or unparseable XML
means the WHOLE figure is dropped (returns None), never a partially-cleaned figure.
Client-side DOMPurify is a second, independent layer at render time (spec decision 3) —
this function is not the only defense, but it must never let anything hostile through
on its own.
"""

import xml.etree.ElementTree as ET

MAX_INPUT_BYTES = 8 * 1024

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"

ALLOWED_ELEMENTS = {
    "svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "path", "text", "tspan", "title", "defs", "marker",
}

ALLOWED_ATTRS = {
    "viewBox", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "d", "points", "transform", "fill", "stroke",
    "stroke-width", "stroke-dasharray", "font-size", "font-family",
    "font-weight", "text-anchor", "dominant-baseline", "opacity",
    "fill-opacity", "marker-end", "marker-start", "id", "class",
}

# Prompt copy shared by generation.py's _IMAGES_BLOCK and images.py's backfill_prompt —
# lives here (not in generation.py or images.py) so neither of those two modules needs
# to import the other just for this string (images.py already needs sanitize_svg above;
# generation.py already imports images.py — putting this text in either of THEM would
# risk a circular import).
DRAWN_FIGURE_GUIDANCE = (
    "\n\nA figure slot may also be a diagram Claude draws itself, as code — no extra "
    "image call, no URL. Choose the figure type by what the content needs: concrete "
    "identification (anatomy, organisms, objects) needs a web-image; a process, flow, "
    "sequence, hierarchy, or timeline needs mermaid; a labeled spatial schematic that "
    "mermaid cannot express needs svg (keep it simple: at most ~25 elements); "
    "quantitative data needs mermaid xychart-beta or pie. When a diagram would be too "
    "complex to draw clearly in code, prefer a web-image slot instead.\n"
    '  A mermaid slot: {"type": "mermaid", "code": "<mermaid source>", "caption": '
    '"<one sentence saying what to NOTICE>"}.\n'
    '  An svg slot: {"type": "svg", "code": "<svg ...>...</svg>", "caption": "<one '
    'sentence saying what to NOTICE>"}. SVG authoring rules: fixed viewBox="0 0 800 '
    '500"; label every part with a <text> element INSIDE the drawing itself, never a '
    "separate legend; font-size at least 14px; use simple flat colors that read clearly "
    "on a light card.\n"
    '  A web-image slot may also state "type": "web-image" explicitly (omitting type '
    "still defaults to web-image).\n"
)


def _local_name(tag):
    """Strip a Clark-notation namespace (e.g. '{http://www.w3.org/2000/svg}rect' ->
    ('rect', 'http://www.w3.org/2000/svg')) so the allowlist check is namespace-aware
    but not namespace-syntax-dependent. Returns (local_name, namespace_uri_or_None)."""
    if tag.startswith("{"):
        uri, _, local = tag[1:].partition("}")
        return local, uri
    return tag, None


def _check_element(el):
    """Recursively validate one element and its subtree against the allowlists.
    Returns True if the whole subtree is clean, False on the first violation
    (short-circuits — the caller drops the whole figure on any False)."""
    local, uri = _local_name(el.tag)
    if uri is not None and uri != _SVG_NS:
        return False
    if local not in ALLOWED_ELEMENTS:
        return False
    for attr_name in el.attrib:
        attr_local, attr_uri = _local_name(attr_name)
        if attr_uri == _XLINK_NS:
            return False  # xlink:href (or any other xlink:* attribute) — reject outright
        if attr_local.lower().startswith("on"):
            return False  # onclick, onload, ... — belt-and-suspenders over the allowlist below
        if attr_local in ("href", "style"):
            return False
        if attr_local not in ALLOWED_ATTRS:
            return False
    for child in el:
        if not _check_element(child):
            return False
    return True


def _strip_namespace(el):
    """Rewrite this element's tag (and its children's, recursively) to drop the SVG
    namespace URI, so ET's serializer emits clean `<rect .../>` instead of
    `<ns0:rect xmlns:ns0="...">`. Attribute names need no rewriting: only bare or
    xlink-namespaced attributes are possible at this point, and xlink ones were
    already rejected by _check_element."""
    local, _ = _local_name(el.tag)
    el.tag = local
    for child in el:
        _strip_namespace(child)


def sanitize_svg(code):
    """Strict allowlist SVG sanitizer. Returns canonical sanitized SVG markup, or
    None if code is empty/not a string, oversized (>8KB), unparseable XML, not
    rooted at <svg>, missing a viewBox, carries a width/height on the root, or
    contains ANY element, attribute, on* handler, href/xlink:href, or style not on
    the allowlist. Never repairs — a violation drops the whole figure, it is never
    partially cleaned."""
    if not isinstance(code, str) or not code.strip():
        return None
    if len(code.encode("utf-8")) > MAX_INPUT_BYTES:
        return None
    try:
        root = ET.fromstring(code)
    except ET.ParseError:
        return None
    local, uri = _local_name(root.tag)
    if uri is not None and uri != _SVG_NS:
        return None
    if local != "svg":
        return None
    if "viewBox" not in root.attrib:
        return None
    # The root must NOT carry width/height (CSS sizes it) — width/height ARE allowlisted
    # attributes generically (needed on shapes like <rect>), so this must be checked here
    # explicitly, before the generic walk below would otherwise let them through.
    if "width" in root.attrib or "height" in root.attrib:
        return None
    if not _check_element(root):
        return None
    _strip_namespace(root)
    return ET.tostring(root, encoding="unicode")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_figures.py -q`
Expected: `18 passed`.

- [ ] **Step 5: Write the failing `generation.py` typed-slot and prompt-guidance tests**

Append to `tests/test_generation.py` (near the existing `test_valid_lesson_images_shape_when_present` / `test_lesson_prompt_includes_images_slot_instructions` tests):

```python
def test_valid_images_mermaid_slot_shape():
    assert gen.valid_images([{"type": "mermaid", "code": "graph TD; A-->B;", "caption": "c"}]) is True
    assert gen.valid_images([{"type": "mermaid", "code": "", "caption": "c"}]) is False
    assert gen.valid_images([{"type": "mermaid", "code": "x" * 8193, "caption": "c"}]) is False
    assert gen.valid_images([{"type": "mermaid", "code": "x" * 8192, "caption": "c"}]) is True
    assert gen.valid_images([{"type": "mermaid", "code": "x"}]) is False  # missing caption


def test_valid_images_svg_slot_shape():
    assert gen.valid_images([{"type": "svg", "code": "<svg></svg>", "caption": "c"}]) is True
    assert gen.valid_images([{"type": "svg", "code": "", "caption": "c"}]) is False


def test_valid_images_unknown_type_rejected():
    assert gen.valid_images([{"type": "video", "code": "x", "caption": "c"}]) is False


def test_valid_images_web_image_default_unchanged():
    assert gen.valid_images([{"query": "q", "caption": "c"}]) is True
    assert gen.valid_images([{"type": "web-image", "query": "q", "caption": "c"}]) is True


def test_lesson_prompt_includes_drawn_figure_guidance():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    assert '"type": "mermaid"' in p
    assert '"type": "svg"' in p
    assert 'viewBox="0 0 800 500"' in p
    assert "Drawn by Claude" not in p  # that's the FRONTEND credit text, not prompt copy


def test_ensure_lesson_splits_mixed_type_slots_preserving_original_n(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["promptHtml"] = "<p>a</p>[[figure:1]]<p>b</p>[[figure:2]]<p>c</p>[[figure:3]]"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["images"] = [
        {"type": "svg", "code": '<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>', "caption": "s"},
        {"type": "mermaid", "code": "graph TD; A-->B;", "caption": "m"},
        {"query": "cells", "caption": "w"},
    ]

    def fake_resolver(course_id, lesson_id, slots, *, content_dir):
        # only the web-image slot (index 3, others None) should be passed through
        assert slots[0] is None and slots[1] is None
        assert slots[2] == {"query": "cells", "caption": "w"}
        return [{"n": 3, "type": "web-image", "file": "demo-l1-3.jpg", "caption": "w",
                 "credit": "c", "license": "CC0", "licenseUrl": None, "sourceUrl": ""}]

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=fake_resolver)
    ns_types = [(e["n"], e["type"]) for e in out["images"]]
    assert ns_types == [(1, "svg"), (2, "mermaid"), (3, "web-image")]
    assert "[[figure:1]]" in out["promptHtml"]
    assert "[[figure:2]]" in out["promptHtml"]
    assert "[[figure:3]]" in out["promptHtml"]


def test_ensure_lesson_svg_rejection_strips_only_its_own_token(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["promptHtml"] = "<p>a</p>[[figure:1]]<p>b</p>[[figure:2]]"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["images"] = [
        {"type": "svg", "code": "<svg><rect></svg>", "caption": "bad, unparseable"},  # rejected
        {"type": "mermaid", "code": "pie", "caption": "m"},
    ]

    def boom(*a, **kw):
        raise AssertionError("resolver should not be called: no web-image slots")

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=boom)
    assert "[[figure:1]]" not in out["promptHtml"]
    assert "[[figure:2]]" in out["promptHtml"]
    assert out["images"] == [{"n": 2, "type": "mermaid", "code": "pie", "caption": "m"}]


def test_ensure_lesson_mermaid_only_never_calls_resolver(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["promptHtml"] = "<p>a</p>[[figure:1]]"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["images"] = [{"type": "mermaid", "code": "graph TD;", "caption": "m"}]

    def boom(*a, **kw):
        raise AssertionError("resolver should not be called")

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=boom)
    assert out["images"] == [{"n": 1, "type": "mermaid", "code": "graph TD;", "caption": "m"}]
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -q -k "mermaid or svg or drawn_figure_guidance"`
Expected: failures — `valid_images` rejects the typed slots (unknown-shape branch doesn't exist yet), `lesson_prompt` doesn't mention `"type": "mermaid"`, and the hook tests fail because `resolve_images` currently receives the WHOLE slots list unfiltered (the fake resolver's `assert slots[0] is None` fails, and the "should not be called" resolvers get called).

- [ ] **Step 7: Wire typed slots into `generation.py`**

Edit `backend/generation.py` line 7:

```python
from backend import claude_client, courses, figures, fsutil, images, spine
```

Replace `valid_images` (lines 208-224):

```python
def valid_images(images_val):
    """If-present shape check for the raw generator output's images slots. Absent
    (None) stays valid — cached lessons without the field, and lessons that
    legitimately have zero figures, are unaffected. Parameter is NOT named
    `images` — that name is now the imported backend.images module in this
    file's global scope.

    Three slot shapes (drawn-diagrams slice, decision 1): a slot with no `type`
    key, or `type: "web-image"`, needs non-empty string `query` + `caption`
    (unchanged from slice 1); `type: "mermaid"` or `type: "svg"` needs a
    non-empty string `code` (<=8192 chars) + non-empty string `caption`. Any
    other `type` value is invalid."""
    if images_val is None:
        return True
    if not (isinstance(images_val, list) and len(images_val) <= 3):
        return False
    for slot in images_val:
        if not isinstance(slot, dict):
            return False
        kind = slot.get("type", "web-image")
        if kind == "web-image":
            for field in ("query", "caption"):
                if not (isinstance(slot.get(field), str) and slot[field].strip()):
                    return False
        elif kind in ("mermaid", "svg"):
            code = slot.get("code")
            if not (isinstance(code, str) and code.strip() and len(code) <= 8192):
                return False
            if not (isinstance(slot.get("caption"), str) and slot["caption"].strip()):
                return False
        else:
            return False
    return True
```

Extend `_IMAGES_BLOCK` (lines 292-307) additively — append `figures.DRAWN_FIGURE_GUIDANCE` to the existing tuple concatenation, changing only the closing paren line:

```python
_IMAGES_BLOCK = (
    "\n\nOptionally include real figures — anatomy plates, diagrams, charts — the backend finds, "
    "license-checks, and caches them automatically; you NEVER provide a URL, only a search query "
    "and a caption. Add a figure ONLY for spatial, structural, process, or quantitative content "
    "the text explains — NEVER decorative; when in doubt, omit one (zero images is often correct). "
    "Prefer a real photo or plate for concrete identification (anatomy, organisms, objects), a "
    "schematic for a process or abstract relation, and a chart for quantitative data. Every figure "
    "needs a caption stating what to NOTICE, not a title. Place the figure immediately after the "
    "paragraph that references it — never grouped at the end — using a bare placement token on its "
    "own, right after that paragraph: [[figure:1]] for the first figure, [[figure:2]] for the "
    "second, [[figure:3]] for the third. Budget at most ONE figure per major concept and at most "
    "THREE per lesson.\n"
    '  images (optional — omit the key entirely if no figure genuinely helps): a list of 0-3 '
    '{"query": "<discriminating archive search terms>", "caption": "<one sentence saying what to '
    'NOTICE>"}, one per [[figure:n]] token you placed, in the same order.\n'
) + figures.DRAWN_FIGURE_GUIDANCE
```

Replace the resolver hook inside `_generate_and_store_lesson` (lines 1272-1285):

```python
    # Image resolution: the ONLY hook point that covers both cache-miss generation
    # AND deepen (deepen overwrites the lesson file wholesale). Fails open: any
    # exception here means the lesson ships with zero figures, never a blocked lesson.
    # Typed slots (drawn-diagrams slice): mermaid/svg are processed locally (svg
    # sanitized, dropped on rejection; mermaid passed through — already shape-checked
    # by valid_images); only web-image slots go to the resolver. web_image_slots keeps
    # the SAME LENGTH as slots with non-web-image positions set to None, so the
    # resolver's positional enumerate(..., start=1) still assigns each surviving
    # web-image slot its ORIGINAL 1-based number — no change to resolve_images's
    # signature is needed (it already skips non-dict slots).
    slots = lesson.pop("images", None)
    resolver = resolve_images or images.resolve_images
    resolved = []
    if isinstance(slots, list) and slots:
        local_entries, web_image_slots = _process_local_slots(slots)
        web_resolved = []
        if any(s is not None for s in web_image_slots):
            try:
                web_resolved = resolver(course_id, lesson_id, web_image_slots, content_dir=content_dir)
            except Exception:
                web_resolved = []
        resolved = sorted(local_entries + web_resolved, key=lambda e: e["n"])
    lesson["images"] = resolved
```

Add the `_process_local_slots` helper immediately before `_generate_and_store_lesson` (line 1197):

```python
def _process_local_slots(slots):
    """Split lesson image slots by type (drawn-diagrams slice). Returns
    (local_entries, web_image_slots): local_entries holds resolved mermaid/svg
    entries {n, type, code, caption} — mermaid passes `code` through verbatim
    (already shape-validated by valid_images before this runs); svg runs `code`
    through figures.sanitize_svg and is DROPPED (not added) on rejection, same
    fail-open contract as an unresolved web-image slot. web_image_slots is the
    SAME LENGTH as slots with every non-web-image position set to None."""
    local_entries = []
    web_image_slots = []
    for i, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            web_image_slots.append(None)
            continue
        kind = slot.get("type", "web-image")
        if kind == "svg":
            sanitized = figures.sanitize_svg(slot.get("code", ""))
            if sanitized is not None:
                local_entries.append({"n": i, "type": "svg", "code": sanitized,
                                       "caption": slot.get("caption", "")})
            web_image_slots.append(None)
        elif kind == "mermaid":
            local_entries.append({"n": i, "type": "mermaid", "code": slot.get("code", ""),
                                   "caption": slot.get("caption", "")})
            web_image_slots.append(None)
        else:
            web_image_slots.append(slot)
    return local_entries, web_image_slots
```

Note: this `_process_local_slots` helper is a Task-1-only intermediate — Task 2 extracts this exact logic into a shared `images.process_slots` (reused by the backfill CLI too) and removes this helper from `generation.py`. It is written out in full here because Task 1 must be independently correct and tested.

- [ ] **Step 8: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py tests/test_figures.py tests/test_images.py -q`
Expected: all pass, including the 208 pre-existing tests in these three files (regression-safe).

- [ ] **Step 9: Commit**

```bash
git add backend/figures.py backend/generation.py tests/test_figures.py tests/test_generation.py
git commit -m "$(cat <<'EOF'
feat(figures): strict SVG sanitizer + typed mermaid/svg image slots

Server-side allowlist sanitizer for Claude-authored SVG diagrams
(xml.etree, stdlib only), plus typed mermaid/svg slot shapes and
prompt guidance in generation.py's image-slot machinery. The
generation hook now splits slots by type — svg/mermaid processed
locally, only web-image slots reach the existing resolver — while
preserving each slot's original placement-token number.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Vendoring + backfill extension (`frontend/vendor/`, `backend/images.py`, `backend/app.py`)

**Files:**
- Create: `frontend/vendor/mermaid.min.js`, `frontend/vendor/purify.min.js`, `frontend/vendor/VERSIONS.md`
- Modify: `backend/app.py` (static routes, lines 782-794)
- Modify: `backend/images.py` — imports (line 20); `backfill_prompt` (lines 371-393); `_valid_images_slots` (lines 396-408); `backfill_course` (lines 422-459); add `process_slots`
- Modify: `backend/generation.py` — refactor the Task-1 hook to call `images.process_slots`; remove `_process_local_slots`
- Test: `tests/test_static.py` (append)
- Test: `tests/test_images.py` (append)
- Test: `tests/test_generation.py` (no new tests needed — Step 9 below reruns Task 1's hook tests unmodified to prove the refactor is behavior-preserving)

**Interfaces:**
- Consumes: `figures.sanitize_svg`, `figures.DRAWN_FIGURE_GUIDANCE` (Task 1); `images.resolve_images` (slice 1, unmodified).
- Produces: `images.process_slots(course_id, lesson_id, slots, *, content_dir, resolve_images_fn=None) -> list[dict]` — the single shared implementation of the type-splitting logic, called by both `_generate_and_store_lesson` (generation.py) and `backfill_course` (images.py). `GET /vendor/<filename>` route.

- [ ] **Step 1: Download and verify the pinned vendor files**

Run from repo root:

```bash
mkdir -p frontend/vendor
curl -sL "https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.min.js" -o frontend/vendor/mermaid.min.js
curl -sL "https://cdn.jsdelivr.net/npm/dompurify@3.4.12/dist/purify.min.js" -o frontend/vendor/purify.min.js
wc -c frontend/vendor/mermaid.min.js frontend/vendor/purify.min.js
grep -c "mermaid" frontend/vendor/mermaid.min.js
grep -c "DOMPurify" frontend/vendor/purify.min.js
```

Expected: `mermaid.min.js` > 1,000,000 bytes and contains the string `mermaid`; `purify.min.js` > 10,000 bytes and contains the string `DOMPurify`. (These two `curl` calls are the ONE deliberate exception to "tests never call live APIs" — a one-time implementer step, not a test; the resulting files are committed static assets from here on.)

- [ ] **Step 2: Write `frontend/vendor/VERSIONS.md`**

Create `frontend/vendor/VERSIONS.md`:

```markdown
# Vendored frontend libraries

Pinned, committed, no CDN at runtime (spec: `docs/superpowers/specs/2026-07-17-drawn-diagrams-design.md`, decisions 2 and 3).

- **mermaid.min.js** — v11.16.0 — `https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.min.js` — pinned 2026-07-17
- **purify.min.js** (DOMPurify) — v3.4.12 — `https://cdn.jsdelivr.net/npm/dompurify@3.4.12/dist/purify.min.js` — pinned 2026-07-17

To update: re-run the `curl` commands above with a newer version pin, verify the new
file's size floor and marker string (see `tests/test_static.py`), update the version
and date in this file, then commit both together.
```

- [ ] **Step 3: Write the failing vendor-files-exist and vendor-route tests**

Append to `tests/test_static.py`:

```python
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "frontend" / "vendor"


def test_vendored_mermaid_present_and_nontrivial():
    p = _VENDOR_DIR / "mermaid.min.js"
    assert p.exists(), "run Task 2 Step 1: curl mermaid.min.js into frontend/vendor/"
    data = p.read_bytes()
    assert len(data) > 1_000_000
    assert b"mermaid" in data.lower()


def test_vendored_purify_present_and_nontrivial():
    p = _VENDOR_DIR / "purify.min.js"
    assert p.exists(), "run Task 2 Step 1: curl purify.min.js into frontend/vendor/"
    data = p.read_bytes()
    assert len(data) > 10_000
    assert b"DOMPurify" in data


def test_vendor_purify_served_with_js_mimetype(client):
    resp = client.get("/vendor/purify.min.js")
    assert resp.status_code == 200
    assert "javascript" in resp.content_type
```

- [ ] **Step 4: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_static.py -q`
Expected: the two file-existence tests PASS already (files were downloaded in Step 1), but `test_vendor_purify_served_with_js_mimetype` fails with a 404 (no `/vendor/<path:filename>` route yet).

- [ ] **Step 5: Add the vendor route to `backend/app.py`**

Edit `backend/app.py`, inserting between the existing `/src/<path:filename>` route and the `/styles.css` route (lines 788-792):

```python
    @app.get("/src/<path:filename>")
    def src_files(filename):
        return send_from_directory(frontend_dir / "src", filename)

    @app.get("/vendor/<path:filename>")
    def vendor_files(filename):
        return send_from_directory(frontend_dir / "vendor", filename)

    @app.get("/styles.css")
    def styles():
        return send_from_directory(frontend_dir, "styles.css")
```

- [ ] **Step 6: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_static.py -q`
Expected: `3 passed` (plus the 3 pre-existing tests in that file — `6 passed` total).

- [ ] **Step 7: Write the failing `process_slots` and typed-backfill tests**

Append to `tests/test_images.py`:

```python
def test_process_slots_mixed_types(tmp_path):
    content_dir = tmp_path / "courses"
    slots = [
        {"query": "q", "caption": "c"},
        {"type": "svg", "code": '<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>', "caption": "s"},
        {"type": "mermaid", "code": "pie", "caption": "m"},
    ]

    def fake_resolver(course_id, lesson_id, slots_arg, *, content_dir):
        assert slots_arg[0] == {"query": "q", "caption": "c"}
        assert slots_arg[1] is None and slots_arg[2] is None
        return [{"n": 1, "type": "web-image", "file": "demo-l1-1.jpg", "caption": "c",
                 "credit": "c", "license": "CC0", "licenseUrl": None, "sourceUrl": ""}]

    result = images.process_slots("demo", "demo-l1", slots, content_dir=content_dir,
                                   resolve_images_fn=fake_resolver)
    assert [e["n"] for e in result] == [1, 2, 3]
    assert [e["type"] for e in result] == ["web-image", "svg", "mermaid"]


def test_process_slots_never_raises_on_resolver_exception(tmp_path):
    content_dir = tmp_path / "courses"
    slots = [{"type": "mermaid", "code": "pie", "caption": "m"}, {"query": "q", "caption": "c"}]

    def boom(*a, **kw):
        raise RuntimeError("archive outage")

    result = images.process_slots("demo", "demo-l1", slots, content_dir=content_dir, resolve_images_fn=boom)
    # local mermaid entry survives even though the web-image resolver blew up
    assert result == [{"n": 1, "type": "mermaid", "code": "pie", "caption": "m"}]


def test_valid_images_slots_backfill_accepts_typed_slots():
    assert images._valid_images_slots([{"type": "mermaid", "code": "pie", "caption": "c"}]) is True
    assert images._valid_images_slots([{"type": "svg", "code": "<svg></svg>", "caption": "c"}]) is True
    assert images._valid_images_slots([{"type": "svg", "code": "", "caption": "c"}]) is False
    assert images._valid_images_slots([{"type": "bogus", "code": "x", "caption": "c"}]) is False


def test_backfill_prompt_includes_drawn_figure_guidance():
    lesson = {"topic": "Cells", "promptHtml": "<p>Cells divide.</p>"}
    p = images.backfill_prompt(lesson)
    assert '"type": "mermaid"' in p
    assert '"type": "svg"' in p


def test_backfill_course_mermaid_slot_stores_without_network_call(tmp_path, monkeypatch):
    content_dir = tmp_path / "courses"
    lessons_dir = content_dir / "demo" / "lessons"
    lessons_dir.mkdir(parents=True)
    lesson_path = lessons_dir / "demo-l1.json"
    lesson_path.write_text(json.dumps({"id": "demo-l1", "topic": "Cells", "promptHtml": "<p>Cells divide.</p>"}))

    def fake_generate(prompt, validate):
        obj = {"images": [{"type": "mermaid", "code": "graph TD; A-->B;", "caption": "flow"}],
               "promptHtml": "<p>Cells divide.</p>[[figure:1]]"}
        assert validate(obj)
        return obj

    def boom_http(url):
        raise AssertionError("no network call should happen for a mermaid-only proposal")

    monkeypatch.setattr(images, "_http_get", boom_http)
    updated = images.backfill_course(content_dir, "demo", generate=fake_generate)
    assert updated == 1
    saved = json.loads(lesson_path.read_text())
    assert saved["images"] == [{"n": 1, "type": "mermaid", "code": "graph TD; A-->B;", "caption": "flow"}]
    assert "[[figure:1]]" in saved["promptHtml"]


def test_backfill_course_svg_rejection_strips_token_and_continues(tmp_path):
    content_dir = tmp_path / "courses"
    lessons_dir = content_dir / "demo" / "lessons"
    lessons_dir.mkdir(parents=True)
    lesson_path = lessons_dir / "demo-l1.json"
    lesson_path.write_text(json.dumps({"id": "demo-l1", "topic": "Cells", "promptHtml": "<p>Cells divide.</p>"}))

    def fake_generate(prompt, validate):
        obj = {"images": [{"type": "svg", "code": "<svg><rect></svg>", "caption": "bad"}],
               "promptHtml": "<p>Cells divide.</p>[[figure:1]]"}
        assert validate(obj)
        return obj

    updated = images.backfill_course(content_dir, "demo", generate=fake_generate)
    assert updated == 1
    saved = json.loads(lesson_path.read_text())
    assert saved["images"] == []
    assert "[[figure:1]]" not in saved["promptHtml"]
    assert "<p>Cells divide.</p>" in saved["promptHtml"]
```

- [ ] **Step 8: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_images.py -q -k "process_slots or backfill_course_mermaid or backfill_course_svg or valid_images_slots_backfill or backfill_prompt_includes_drawn"`
Expected: `AttributeError: module 'backend.images' has no attribute 'process_slots'` (and the two `_valid_images_slots`/`backfill_prompt` tests fail on the missing typed-shape support and missing guidance text).

- [ ] **Step 9: Implement `process_slots` and the typed backfill extension in `backend/images.py`; refactor `generation.py`'s hook to use it**

Edit `backend/images.py` line 20:

```python
from backend import claude_client, figures, fsutil
```

Add `process_slots` immediately before `backfill_prompt` (line 371):

```python
def process_slots(course_id, lesson_id, slots, *, content_dir, resolve_images_fn=None):
    """Shared by the generation hook (backend/generation.py's
    `_generate_and_store_lesson`) and `backfill_course` below: splits typed image
    slots by type, processes mermaid/svg locally (svg sanitized via
    figures.sanitize_svg, dropped on rejection; mermaid passed through verbatim —
    already shape-validated upstream), and routes ONLY web-image slots to
    resolve_images — preserving each slot's ORIGINAL 1-based position as `n` by
    padding non-web-image positions with None (resolve_images already skips
    non-dict slots via `isinstance(slot, dict)`, so this needs no change to its
    signature). Returns the combined entries list sorted by n. Never raises: a
    resolve_images exception drops only the web-image entries — already-processed
    local (mermaid/svg) entries are kept. `resolve_images_fn` is the same
    dependency-injection seam tests already use (defaults to this module's own
    `resolve_images`)."""
    if not isinstance(slots, list):
        return []
    local_entries = []
    web_image_slots = []
    for i, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            web_image_slots.append(None)
            continue
        kind = slot.get("type", "web-image")
        if kind == "svg":
            sanitized = figures.sanitize_svg(slot.get("code", ""))
            if sanitized is not None:
                local_entries.append({"n": i, "type": "svg", "code": sanitized,
                                       "caption": slot.get("caption", "")})
            web_image_slots.append(None)
        elif kind == "mermaid":
            local_entries.append({"n": i, "type": "mermaid", "code": slot.get("code", ""),
                                   "caption": slot.get("caption", "")})
            web_image_slots.append(None)
        else:
            web_image_slots.append(slot)
    resolver = resolve_images_fn or resolve_images
    web_resolved = []
    if any(s is not None for s in web_image_slots):
        try:
            web_resolved = resolver(course_id, lesson_id, web_image_slots, content_dir=content_dir)
        except Exception:
            web_resolved = []
    return sorted(local_entries + web_resolved, key=lambda e: e["n"])
```

Extend `backfill_prompt` (lines 371-393, now shifted below `process_slots`) additively:

```python
def backfill_prompt(lesson):
    topic = lesson.get("topic", "")
    prompt_html = lesson.get("promptHtml", "")
    return (
        "You are retrofitting ONE existing cached lesson with optional figure "
        "placements. Read its body below and decide whether 0-3 figures would "
        "genuinely help, following these rules: a figure is warranted ONLY for "
        "spatial, structural, process, or quantitative content the text explains "
        "— never decorative; when in doubt, propose none. Prefer a real photo or "
        "plate for concrete identification, a schematic for a process, a chart for "
        "quantitative data. Budget at most one figure per major concept, at most "
        "three total.\n"
        f"Lesson topic: {topic}\n"
        f"Lesson body (HTML):\n{prompt_html}\n\n"
        "Reply with ONLY a JSON object (no prose, no fence) with exactly these keys:\n"
        '  images: a list of 0-3 {"query": "<discriminating archive search terms>", '
        '"caption": "<one sentence saying what to NOTICE>"}.\n'
        '  promptHtml: the EXACT lesson body above, UNCHANGED character-for-character, '
        "except for inserting a bare placement token [[figure:1]] (then [[figure:2]], "
        "[[figure:3]] for additional figures) on its own, immediately after the closing "
        "tag of the paragraph each figure illustrates — one token per images entry, in "
        "order. Do NOT rewrite, rephrase, or otherwise alter any existing text.\n"
        + figures.DRAWN_FIGURE_GUIDANCE
    )
```

Replace `_valid_images_slots` (immediately after `backfill_prompt`):

```python
def _valid_images_slots(images_val):
    """Backfill-specific images-shape check: unlike generation.valid_images,
    the key must ALWAYS be a list (possibly empty) — the proposal always states
    a decision, it never omits the field. Same three per-slot shapes as
    generation.valid_images (web-image needs query+caption; mermaid/svg need
    code (<=8192 chars) + caption); any other `type` is invalid."""
    if not (isinstance(images_val, list) and len(images_val) <= MAX_SLOTS):
        return False
    for slot in images_val:
        if not isinstance(slot, dict):
            return False
        kind = slot.get("type", "web-image")
        if kind == "web-image":
            for field in ("query", "caption"):
                if not (isinstance(slot.get(field), str) and slot[field].strip()):
                    return False
        elif kind in ("mermaid", "svg"):
            code = slot.get("code")
            if not (isinstance(code, str) and code.strip() and len(code) <= 8192):
                return False
            if not (isinstance(slot.get("caption"), str) and slot["caption"].strip()):
                return False
        else:
            return False
    return True
```

In `backfill_course`, change the resolve call to use the new shared function:

```python
        try:
            resolved = process_slots(course_id, lesson_id, proposal["images"], content_dir=content_dir)
        except Exception:
            resolved = []
```

Now refactor `backend/generation.py`'s hook (Task 1's inline version) to call the shared `images.process_slots` instead, and remove the now-dead `_process_local_slots` helper. Remove the `_process_local_slots` function entirely (it was added in Task 1, lines directly above `_generate_and_store_lesson`). Replace the hook body from Task 1's Step 7 with:

```python
    # Image resolution: the ONLY hook point that covers both cache-miss generation
    # AND deepen (deepen overwrites the lesson file wholesale). Fails open: any
    # exception here means the lesson ships with zero figures, never a blocked lesson.
    # Splitting typed slots by type (svg/mermaid processed locally, only web-image
    # slots hit the resolver) is shared with the backfill CLI via images.process_slots.
    slots = lesson.pop("images", None)
    resolved = []
    if isinstance(slots, list) and slots:
        try:
            resolved = images.process_slots(course_id, lesson_id, slots, content_dir=content_dir,
                                             resolve_images_fn=resolve_images)
        except Exception:
            resolved = []
    lesson["images"] = resolved
```

Note `figures` is still imported in `generation.py` (used by `_IMAGES_BLOCK`'s `+ figures.DRAWN_FIGURE_GUIDANCE`), even though `_process_local_slots` — the only OTHER user of `figures` in that file — is gone.

- [ ] **Step 10: Run it to verify it passes**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass — this includes every Task 1 hook test (`test_ensure_lesson_splits_mixed_type_slots_preserving_original_n`, `test_ensure_lesson_svg_rejection_strips_only_its_own_token`, `test_ensure_lesson_mermaid_only_never_calls_resolver`) passing UNMODIFIED against the refactored hook — proving the extraction into `images.process_slots` is behavior-preserving.

- [ ] **Step 11: Commit**

```bash
git add frontend/vendor/mermaid.min.js frontend/vendor/purify.min.js frontend/vendor/VERSIONS.md \
        backend/app.py backend/images.py backend/generation.py \
        tests/test_static.py tests/test_images.py
git commit -m "$(cat <<'EOF'
feat(images): vendor mermaid/DOMPurify + shared typed-slot backfill

Commit pinned mermaid.min.js (11.16.0) and purify.min.js (DOMPurify
3.4.12) under frontend/vendor/, served via a new /vendor route.
Extract the generation hook's mermaid/svg-vs-web-image slot
splitting into a shared images.process_slots, reused by both
_generate_and_store_lesson and the backfill CLI so the logic lives
in exactly one place; the backfill proposal prompt and validator
now accept all three slot types.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend rendering (`frontend/src/views/lesson.js`, `frontend/src/app.js`, `styles.css`)

**Files:**
- Modify: `frontend/src/views/lesson.js` — `figureHTML`/`expandFigureTokens` (lines 88-137)
- Modify: `frontend/src/app.js` — `paintLesson` (line 969) and its surrounding closure
- Modify: `frontend/styles.css` — after the existing `.lesson-figures{...}` rule (line 175)
- Test: `frontend/tests/views.test.js` (modify one existing test, append new ones)

**Interfaces:**
- Consumes: lesson `images` entries as stored by Task 1/2's backend hook: `{"n": <int>, "type": "svg"|"mermaid", "code": <str>, "caption": <str>}` for drawn figures (no `credit`/`license`/`file` — those are web-image-only fields), alongside the unchanged slice-1 web-image entry shape.
- Produces: `hydrateFigures(view, lesson)` in `app.js` (not exported — called only from `paintLesson`); `.lesson-fig-svg` / `.lesson-fig-mermaid` CSS classes; DOM placeholders `<figure ... data-fig-svg="n">` / `<figure ... data-fig-mermaid="n">` that `hydrateFigures` targets via `[data-fig-svg]` / `[data-fig-mermaid]`.

- [ ] **Step 1: Write the failing `lesson.js` tests**

In `frontend/tests/views.test.js`, replace the existing test (it used `type: "mermaid"` as an example of an "unknown" type, which is no longer true — Ambiguity Resolution 9):

```javascript
test("expandFigureTokens renders nothing for an unknown figure type", () => {
  const lesson = { images: [{ n: 1, type: "carousel", code: "x", caption: "c" }] };
  const { html, figuresBlock } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.equal(html, "");
  assert.equal(figuresBlock, "");
});
```

Then append these new tests immediately after it:

```javascript
// ---- drawn diagrams (slice 2): svg/mermaid arms render a placeholder, never raw code ----

test("expandFigureTokens renders an svg figure as a placeholder, never the raw code", () => {
  const lesson = { images: [{ n: 1, type: "svg", code: '<svg viewBox="0 0 800 500"><script>alert(1)</script></svg>', caption: "Pump schematic" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig lesson-fig-svg" data-fig-svg="1">/);
  assert.match(html, /Pump schematic/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<svg viewBox/); // the raw code string never appears in the template
});

test("expandFigureTokens renders a mermaid figure as a placeholder with caption", () => {
  const lesson = { images: [{ n: 1, type: "mermaid", code: "graph TD; A-->B;", caption: "Water flow" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig lesson-fig-mermaid" data-fig-mermaid="1">/);
  assert.match(html, /Water flow/);
  assert.doesNotMatch(html, /graph TD/); // raw mermaid source never appears in the template
});

test("drawn figures (svg and mermaid) carry the exact credit 'Drawn by Claude'", () => {
  const svgLesson = { images: [{ n: 1, type: "svg", code: "<svg></svg>", caption: "c" }] };
  const mermaidLesson = { images: [{ n: 1, type: "mermaid", code: "pie", caption: "c" }] };
  const { html: svgHtml } = expandFigureTokens("[[figure:1]]", svgLesson, "demo");
  const { html: mermaidHtml } = expandFigureTokens("[[figure:1]]", mermaidLesson, "demo");
  assert.match(svgHtml, /<span class="fig-credit">Drawn by Claude<\/span>/);
  assert.match(mermaidHtml, /<span class="fig-credit">Drawn by Claude<\/span>/);
});

test("expandFigureTokens escapes the caption on svg/mermaid placeholders", () => {
  const lesson = { images: [{ n: 1, type: "svg", code: "<svg></svg>", caption: "<script>alert(1)</script>" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
});

test("expandFigureTokens web-image arm is unaffected by the svg/mermaid arms (regression)", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "c",
    credit: "cred", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig">/); // NOT lesson-fig-svg/lesson-fig-mermaid
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
  assert.doesNotMatch(html, /Drawn by Claude/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test frontend/tests/views.test.js`
Expected: the modified "unknown figure type" test PASSES (type `"carousel"` already renders nothing today — the web-image-only check already excludes it), but all 5 new svg/mermaid tests FAIL (svg/mermaid entries currently render nothing at all, not a placeholder).

- [ ] **Step 3: Implement the svg/mermaid arms in `frontend/src/views/lesson.js`**

Replace lines 92-121 (the `figureHTML` function and the start of `expandFigureTokens`) with:

```javascript
function webImageFigureHTML(entry, courseId) {
  const src = `/api/courses/${esc(courseId)}/images/${esc(entry.file)}`;
  const licenseHref = entry.licenseUrl || entry.sourceUrl || "";
  // Only render an <a> if the href is a valid http(s) URL; otherwise show text
  const licenseLink = SAFE_HREF_RE.test(licenseHref)
    ? `<a href="${esc(licenseHref)}" target="_blank" rel="noopener noreferrer">${esc(entry.license)}</a>`
    : esc(entry.license);
  return (
    `<figure class="lesson-fig"><img src="${src}" alt="${esc(entry.caption)}" loading="lazy">` +
    `<figcaption>${esc(entry.caption)} <span class="fig-credit">${esc(entry.credit)} ` +
    `${licenseLink}` +
    `</span></figcaption></figure>`
  );
}

// svg/mermaid figures are Claude-drawn diagrams (slice 2). The template NEVER
// string-interpolates entry.code — it has no DOMPurify here, so raw code (which could
// carry a <script> if a cached lesson were hand-edited) must never reach this string.
// A placeholder is emitted instead; app.js's hydrateFigures() sanitizes/renders the
// code and injects it into the placeholder (before the figcaption) after paint.
function drawnFigurePlaceholderHTML(entry, dataAttr) {
  return (
    `<figure class="lesson-fig lesson-fig-${esc(entry.type)}" data-${dataAttr}="${entry.n}">` +
    `<figcaption>${esc(entry.caption)} <span class="fig-credit">Drawn by Claude</span></figcaption>` +
    `</figure>`
  );
}

function figureHTML(entry, courseId) {
  if (entry.type === "svg") return drawnFigurePlaceholderHTML(entry, "fig-svg");
  if (entry.type === "mermaid") return drawnFigurePlaceholderHTML(entry, "fig-mermaid");
  return webImageFigureHTML(entry, courseId);
}

function isValidFigureEntry(entry) {
  if (!entry || typeof entry.n !== "number") return false;
  if (entry.type === "web-image") {
    return typeof entry.file === "string" && FIGURE_FILENAME_RE.test(entry.file);
  }
  if (entry.type === "svg" || entry.type === "mermaid") {
    return typeof entry.code === "string" && entry.code.length > 0;
  }
  return false;
}

// Pure pre-render transform: expands [[figure:n]] tokens ONLY against this lesson's
// OWN backend-written images array, and ONLY for entries of a KNOWN type (web-image,
// svg, mermaid — an unrecognized type renders nothing here, so a future new type stays
// inert until its own slice ships). Returns the expanded promptHtml plus a separate
// trailing block for entries whose token never appeared in the prose (the
// retrofit/backfill case).
export function expandFigureTokens(promptHtml, lesson, courseId) {
  const entries = Array.isArray(lesson.images) ? lesson.images : [];
  const byN = new Map();
  for (const entry of entries) {
    if (isValidFigureEntry(entry) && !byN.has(entry.n)) {
      byN.set(entry.n, entry);
    }
  }
```

The remainder of `expandFigureTokens` (the token-replace loop, trailing-block assembly, and return statement — lines 122-137 in the original) is unchanged.

- [ ] **Step 4: Run it to verify it passes**

Run: `node --test frontend/tests/views.test.js`
Expected: all tests pass (verified: 265 total, up from the pre-existing 259).

- [ ] **Step 5: Add `hydrateFigures` and the vendored-library loaders to `frontend/src/app.js`**

In `frontend/src/app.js`, insert immediately before the `paintLesson` function definition (currently at line 969, right after the `explainTeaching`/similar handler ends):

```javascript
  // ---- drawn diagrams (slice 2): lazy-loaded vendored renderers, cached for the
  // session so a lesson with no drawn figures never pays the cost.
  let _purifyPromise = null;
  let _mermaidPromise = null;

  function loadScript(src, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    return new Promise((resolve, reject) => {
      const el = doc.createElement("script");
      el.src = src;
      el.onload = () => resolve(window[globalName]);
      el.onerror = () => reject(new Error(`failed to load ${src}`));
      doc.head.appendChild(el);
    });
  }

  function loadPurify() {
    if (!_purifyPromise) _purifyPromise = loadScript("/vendor/purify.min.js", "DOMPurify");
    return _purifyPromise;
  }

  function loadMermaidLib() {
    if (!_mermaidPromise) {
      _mermaidPromise = loadScript("/vendor/mermaid.min.js", "mermaid").then((m) => {
        m.initialize({ startOnLoad: false, securityLevel: "strict" });
        return m;
      });
    }
    return _mermaidPromise;
  }

  // Hydrates every svg/mermaid figure placeholder currently painted in `view`. Called
  // once at the end of every paintLesson() repaint. lesson.js never string-interpolates
  // figure code into the template (see its comment on drawnFigurePlaceholderHTML), so
  // this is the ONLY place svg code is sanitized-again (DOMPurify, defense in depth over
  // the server-side allowlist) and mermaid code is rendered. `lesson` is captured by
  // value so a slow lazy-load that resolves after the learner has navigated away can
  // never inject into a detached node (mirrors the onScreen staleness guard used by
  // seedWorkspace/explain-grade elsewhere in this file) — repaints rebuild placeholders
  // from scratch, so a fresh hydration on a fresh node is naturally idempotent.
  function hydrateFigures(view, lesson) {
    const entries = Array.isArray(lesson.images) ? lesson.images : [];
    const byN = new Map(entries.map((e) => [e.n, e]));
    const stillFresh = () => ui.screen === "lesson" && ui.lesson === lesson;

    view.querySelectorAll("[data-fig-svg]").forEach((fig) => {
      const entry = byN.get(Number(fig.dataset.figSvg));
      if (!entry || typeof entry.code !== "string") return;
      loadPurify()
        .then((DOMPurify) => {
          if (!stillFresh() || !fig.isConnected) return;
          const clean = DOMPurify.sanitize(entry.code, { USE_PROFILES: { svg: true, svgFilters: true } });
          fig.insertAdjacentHTML("afterbegin", clean);
        })
        .catch(() => {}); // lazy-load/sanitize failure -> the caption already shown is the fallback
    });

    view.querySelectorAll("[data-fig-mermaid]").forEach((fig) => {
      const entry = byN.get(Number(fig.dataset.figMermaid));
      if (!entry || typeof entry.code !== "string") return;
      const renderId = `mermaid-fig-${entry.n}-${Math.random().toString(36).slice(2)}`;
      loadMermaidLib()
        .then((mermaid) => mermaid.render(renderId, entry.code))
        .then(({ svg }) => {
          if (!stillFresh() || !fig.isConnected) return;
          fig.insertAdjacentHTML("afterbegin", svg);
        })
        .catch(() => {}); // parse/render failure -> caption-as-text fallback (nothing injected)
    });
  }

```

Then change the start of `paintLesson` to call it right after the paint:

```javascript
  function paintLesson() {
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    hydrateFigures(view, ui.lesson);
    const curBtn = view.querySelector('[data-action="curriculum"]');
```

(The rest of `paintLesson` is unchanged — `hydrateFigures` runs unconditionally on every repaint, including the prequiz stage, which is harmless: `querySelectorAll` simply finds no `[data-fig-svg]`/`[data-fig-mermaid]` nodes there.)

- [ ] **Step 6: Run the import-resolution check**

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: `imports ok`.

- [ ] **Step 7: Add the CSS**

In `frontend/styles.css`, insert immediately after the existing `.lesson-figures{padding:16px 18px}` line (line 175):

```css
.lesson-fig-svg svg,.lesson-fig-mermaid svg{display:block; width:100%; max-width:100%; height:auto; margin:0 0 6px}
```

- [ ] **Step 8: Run the full frontend test suite once more**

Run: `node --test frontend/tests/*.test.js`
Expected: all pass (265 tests).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/lesson.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js
git commit -m "$(cat <<'EOF'
feat(lesson): render Claude-drawn svg/mermaid diagrams

lesson.js gains svg/mermaid placeholder arms (never string-
interpolating figure code, so no DOMPurify-less template can leak
raw markup); app.js hydrates them after each lesson paint via two
lazy-loaded, vendored, pinned libraries — DOMPurify re-sanitizes SVG
client-side, mermaid renders under securityLevel "strict" with a
caption-as-text fallback on any render error.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```
