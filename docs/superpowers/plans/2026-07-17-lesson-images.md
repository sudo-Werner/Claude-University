# Lesson Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lessons carry real, licensed figures — anatomy plates, diagrams, charts — as captioned, credited images the backend deterministically finds, license-checks, downloads, and caches on the Pi; Claude only writes a search query and caption per slot (never a URL) and makes one vision-assisted pick among the downloaded candidates.

**Architecture:** A new pure/injectable resolver module (`backend/images.py`) does Commons-first/Openverse-fallback search, fail-closed license filtering, magic-byte-verified downloads, and a vision-assisted pick — orchestrated by one function, `resolve_images`. `backend/generation.py`'s `lesson_prompt` asks for 0-3 `{query, caption}` slots plus `[[figure:n]]` placement tokens; the resolver hooks into `_generate_and_store_lesson` (the single choke point that covers both cache-miss generation and deepen) right after validation and before the cache write. A new Flask route serves cached image bytes from `content/courses/<id>/images/`. The frontend (`lesson.js`) expands `[[figure:n]]` tokens into `<figure>` markup purely from the lesson's own backend-written `images` array, never trusting anything else. A one-off CLI backfills the ~25 existing cached lessons.

**Spec:** `docs/superpowers/specs/2026-07-17-lesson-images-design.md` — the single source of requirements (context: `docs/superpowers/specs/2026-07-17-drawn-diagrams-design.md` is the follow-up slice that shares this pipeline via a `type` field seam; it is NOT implemented here — the `type: "web-image"` tag on every resolved entry and the unknown-type-renders-nothing rule in the frontend are the only things this plan does for it). Research: `docs/research/2026-07-17-lesson-images-deep-dive.md`. Implement exactly what the design spec says, nothing extra.

## Ambiguity resolutions

Details the spec left to this plan, resolved by reading the real code and by closest precedent in this codebase:

1. **`license_allowed(value)` is a single function checking BOTH rulesets**, not two functions or a `source` parameter. Verified by construction: Commons values (`"Public domain"`, `"CC BY-SA 3.0"`, ...) and Openverse slugs (`"cc0"`, `"by-sa"`, ...) never collide — no Openverse slug starts with `"cc by "`/`"cc by-sa "` or equals `"public domain"`/`"cc0"` in a way that would leak an NC/ND license through, and no Commons string exactly equals an Openverse slug except the harmless, correctly-allowed `"cc0"`. One function, one place to test both edge-case tables from the spec.
2. **The real HTTP implementation is named `_http_get`** (private, mirrors the existing `_run_cli`/`_spawn_cli` naming convention), exposed as the default value of every function's public `http_get` keyword parameter. It enforces HTTP 200 (raises `HTTPError(code)` — a small local exception class — for anything else, including via `urllib.error.HTTPError` for 4xx/5xx) and returns raw bytes.
3. **`commons_search` and `openverse_search` never raise** — both wrap their `http_get` + `json.loads` calls in a blanket `except Exception: return []`. This is how "skip Openverse entirely on 429" is implemented: `_http_get` raises `HTTPError(429)`, `openverse_search` catches it and returns `[]`, so `resolve_images` sees zero Openverse candidates and never retries — no separate 429 branch is needed in the orchestrator. Same fail-open pattern already used by `generation._reviewed_lesson`.
4. **"≤8 results examined" is enforced by each source's own request parameter** (Commons `gsrlimit=8`, Openverse `page_size=8`) — these are literally the code-enforced values the spec gives, not a separate combined-pool budget across both sources. **"≤4 candidates downloaded" IS a combined cap** (stated as a single number in the spec, applied to the license-valid pool from Commons+Openverse combined, in order).
5. **`vision_pick`'s `topic` argument is fed the slot's own `query` string.** `resolve_images`'s signature is fixed by the spec/task text with no separate lesson-topic parameter (`resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=..., structured=..., deadline_seconds=120)`); the search query already names the subject the figure depicts, which is exactly what orients the vision prompt before it reads the caption and files.
6. **The resolver deadline (120s) uses `time.monotonic()` directly, not an injectable clock** — `resolve_images`'s signature has no `now=` parameter, so a fake-clock test isn't possible without violating the given signature. Per this task's own instruction ("deadline exceeded via injected clock if cheap else omit"), that specific test is **omitted**; the check is still implemented and checked once per slot (between per-slot resolution attempts — the coarsest "between operations" reading that fits a ≤3-slot loop).
7. **`strip_unresolved_figure_tokens` and the token regex live in `backend/images.py`, not `backend/generation.py`.** `generation.py` already imports `backend.images` for `resolve_images`; adding the regex there too (as a public `images.FIGURE_TOKEN_RE` / `images.strip_unresolved_figure_tokens`) keeps one source of truth and avoids `images.py` ever needing to import `generation.py` (which would risk circularity since `generation.py` imports `images.py`). The same compiled regex (with a capture group) is reused unmodified for the backfill validator's "strip all tokens, compare to original" check.
8. **`build_credit`'s exact TASL string format** is not given verbatim by the spec (only "TASL line — Title, Author, Source, License"), so this plan fixes it as `"<title> — <author> — <source> — <license>"` (an em-dash-joined line, source/license segments omitted if empty) and copies it verbatim into every step that builds one — this is the one non-literal string in the plan, called out explicitly here.
9. **The retrofit "Figures" trailing block renders as a sibling `<section class="card lesson-figures">` immediately after the `.lesson` card**, reusing the existing `.ls-head` heading class (already defined for `lessonSourcesHTML`'s "Sources" heading) — this matches the codebase's existing pattern of post-prose supplementary content being a sibling section, not nested inside `.prompt`, and is the most literal reading of "render in a 'Figures' block after the prose."
10. **`resolve_images`'s `structured` default is a small named wrapper, `_default_structured`**, not `claude_client.run_structured` directly, so its call shape (`structured(prompt, validate=..., tools=...)`) is guaranteed to match what `vision_pick` calls regardless of `run_structured`'s own default-argument order.
11. **Backend test files live in `tests/` at the repo root** (`tests/test_images.py` is new; `tests/test_fsutil.py`, `tests/test_claude_client.py`, `tests/test_generation.py`, `tests/test_courses_api.py` get appended to) — there is no `backend/tests/`.

## Global Constraints

Every task's requirements implicitly include this section. Every value below is copied verbatim from the binding spec.

- User-Agent on EVERY HTTP request (search AND download), exactly: `ClaudeUniversity/1.0 (personal learning app; wernerpvanellewee@gmail.com)`.
- Timeout on EVERY HTTP request: `timeout=10` (10 seconds).
- Commons request: `action=query&generator=search&gsrsearch=<query> filetype:bitmap|drawing&gsrnamespace=6&gsrlimit=8&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=800&iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|AttributionRequired|Credit|UsageTerms&format=json` against `https://commons.wikimedia.org/w/api.php`. Use `thumburl` from the response, NEVER `url` (originals are often SVG).
- Openverse request: `GET https://api.openverse.org/v1/images/?q=<query>&license=by,by-sa,cc0,pdm&page_size=8`. On HTTP 429: skip Openverse for this slot, no retry loop.
- License allowlist (fail closed): Commons `LicenseShortName` case-insensitive equals `"public domain"` or `"cc0"`, OR starts with `"cc by "` / `"cc by-sa "` (space-terminated, so `CC BY-NC…`/`CC BY-ND…` can never pass). Openverse `license` value in `{cc0, pdm, by, by-sa}`. Everything else (every NC and ND variant) is rejected.
- Download verification: response body must be HTTP 200 AND match magic bytes — JPEG `\xff\xd8\xff`, PNG `\x89PNG\r\n\x1a\n`, WEBP `RIFF` at bytes 0-3 AND `WEBP` at bytes 8-12. SVG (and anything else) is rejected outright regardless of extension or Content-Type. Size cap: ≤400 KB.
- Thumbnail width requested from Commons: 800px (`iiurlwidth=800`).
- Per-slot caps: ≤8 search results examined per source (enforced by `gsrlimit=8` / `page_size=8`), ≤4 candidates downloaded (combined, across sources).
- Lesson-level cap: ≤3 figure slots (`images` list length ≤3).
- Resolver deadline: ≤120 seconds total per lesson (`deadline_seconds=120` default), checked between per-slot operations; on overrun, fail open (stop resolving further slots, return what's resolved so far).
- Storage path: `content/courses/<course_id>/images/<lesson_id>-<n>.<jpg|png|webp>`, written via `fsutil.write_bytes_atomic` (never the text-only helper — it would corrupt bytes).
- Resolved image entry shape, exactly: `{"n": <int>, "type": "web-image", "file": "<lesson_id>-<n>.<ext>", "caption": <str>, "credit": <str>, "license": "<short name>", "licenseUrl": <str|null>, "sourceUrl": <str>}`.
- Figure placement tokens, plain text in `promptHtml`, exactly: `[[figure:1]]`, `[[figure:2]]`, `[[figure:3]]`.
- Serving route filename regex, exactly, both backend and frontend: `^[a-z0-9-]+-\d\.(jpg|png|webp)$`.
- Serving route: `GET /api/courses/<course_id>/images/<filename>` — `_ID_RE` on `course_id`, filename regex above, `send_from_directory(str(courses.CONTENT_DIR / course_id / "images"), filename)`, JSON `{"error": ...}` + 404 on any mismatch (matching sibling routes).
- Frontend figure markup, exactly: `<figure class="lesson-fig"><img src="/api/courses/<cid>/images/<file>" alt="<esc(caption)>" loading="lazy"><figcaption>${esc(caption)} <span class="fig-credit">${esc(credit)} <a href="${esc(licenseUrl or sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(license)}</a></span></figcaption></figure>`.
- Vision pick reply shape, exactly: `{"pick": <1-based int or null>, "reason": "<one sentence>"}`. Semantics: valid pick → that candidate; explicit `null` → drop the figure; ANY exception or invalid reply → the first candidate (fail open).
- `claude_client.run_structured` gains a keyword-only `tools=None` parameter that appends `["--allowedTools", *tools]` to the CLI args (mirrors `stream()`'s existing `tools` handling); the retry call inside `run_structured` carries the same `tools`.
- Backend tests: `.venv/bin/pytest -q` from repo root (tests live in `tests/`). Frontend tests: `node --test frontend/tests/*.test.js` — the explicit glob is required, a bare directory silently runs nothing.
- After any `frontend/src/app.js`-adjacent change, run the import-resolution check: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` (app.js is not unit-tested by repo convention).
- Tests NEVER call live archive APIs or the real Claude CLI — every network/Claude call is injectable (`http_get`, `structured`, `runner`, `generate`).
- No new pip dependencies — stdlib `urllib` only.
- SVG is never accepted anywhere on this path (backend magic-byte rejection; the frontend never renders SVG figure code — that is slice 2's job, out of scope here).
- Every cap above is code-enforced, not left to prompt-only convention.
- `apply_revision` is NOT touched — image files follow the existing `lessons/` keep-on-revision precedent.
- No emojis anywhere. No refactors or renames outside what this plan specifies.
- One commit per task. Commit messages follow this repo's existing style (`feat(images): ...` / `test(images): ...`), each ending with the line:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Pure resolver machinery — `backend/images.py` + `fsutil` + `claude_client`

**Files:**
- Modify: `backend/fsutil.py` (whole file, 11 lines — add a sibling function)
- Modify: `backend/claude_client.py` (`run_structured` at lines 170-182)
- Create: `backend/images.py`
- Test: `tests/test_fsutil.py` (append after the only existing test, ends line 10)
- Test: `tests/test_claude_client.py` (append after `test_run_structured_applies_validator`, ends line 47, before `test_env_strips_anthropic_credentials` at line 50)
- Test: `tests/test_images.py` (new file)

**Interfaces:**
- Consumes: `fsutil.write_text_atomic(path, text)` idiom (backend/fsutil.py:5-11 — same-dir `.tmp` + `os.replace`); `claude_client.run_structured(prompt, *, model=DEFAULT_MODEL, validate=None, runner=_run_cli)` (backend/claude_client.py:170) and `claude_client.stream(...)`'s existing `tools` handling (backend/claude_client.py:196-200) as the pattern to mirror; `claude_client.ClaudeError`.
- Produces (all in `backend/images.py` unless noted): `fsutil.write_bytes_atomic(path, data)`; `claude_client.run_structured(..., tools=None)` (tools kwarg added, backward compatible); `USER_AGENT` (str constant); `HTTPError(code)` (exception with `.code`); `_http_get(url) -> bytes`; `commons_search(query, *, http_get) -> list[dict]`; `openverse_search(query, *, http_get) -> list[dict]`; `license_allowed(value) -> bool`; `download_verified(url, *, http_get) -> (bytes, ext) | None`; `strip_html(text) -> str`; `build_credit(candidate) -> str`; `FIGURE_TOKEN_RE` (compiled regex, capture group on the digit); `strip_unresolved_figure_tokens(html, resolved_ns) -> str`; `vision_pick(candidates, topic, caption, *, structured, workdir) -> int | None`; `_default_structured(prompt, *, validate=None, tools=None)`; `resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=_http_get, structured=_default_structured, deadline_seconds=120) -> list[dict]`. Task 2 relies on `resolve_images`'s exact signature, `strip_unresolved_figure_tokens`, and the resolved-entry shape above.

- [ ] **Step 1: Write the failing `write_bytes_atomic` test**

Append to `tests/test_fsutil.py`:

```python
def test_write_bytes_atomic_creates_and_replaces(tmp_path):
    target = tmp_path / "img.jpg"
    fsutil.write_bytes_atomic(target, b"\xff\xd8\xffabc")
    assert target.read_bytes() == b"\xff\xd8\xffabc"
    fsutil.write_bytes_atomic(target, b"\x89PNGxyz")
    assert target.read_bytes() == b"\x89PNGxyz"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["img.jpg"]  # no .tmp leftover
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_fsutil.py -q`
Expected: FAIL — `AttributeError: module 'backend.fsutil' has no attribute 'write_bytes_atomic'`

- [ ] **Step 3: Implement `write_bytes_atomic`**

Edit `backend/fsutil.py` — append after `write_text_atomic`:

```python
def write_bytes_atomic(path, data):
    """Write bytes via a same-directory temp file + os.replace — the byte-safe
    sibling of write_text_atomic (that one is text-only and would corrupt
    binary content like a downloaded image)."""
    path = Path(path)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_fsutil.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing `run_structured` tools-param tests**

Append to `tests/test_claude_client.py`, directly after `test_run_structured_applies_validator` (ends line 47) and before `test_env_strips_anthropic_credentials` (line 50):

```python
def test_run_structured_passes_tools_as_allowed_tools():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": '{"ok": true}'})
    out = cc.run_structured("x", runner=runner, tools=["Read"])
    assert out == {"ok": True}
    assert calls[0][:2] == ["-p", "x"]
    i = calls[0].index("--allowedTools")
    assert calls[0][i + 1] == "Read"
    assert "--output-format" in calls[0]


def test_run_structured_without_tools_omits_allowed_tools_flag():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": '{"ok": true}'})
    cc.run_structured("x", runner=runner)
    assert "--allowedTools" not in calls[0]


def test_run_structured_retry_carries_same_tools():
    calls = []
    outputs = iter([
        json.dumps({"result": "sorry no json"}),
        json.dumps({"result": '{"ok": true}'}),
    ])
    def runner(args):
        calls.append(args)
        return next(outputs)
    cc.run_structured("x", runner=runner, tools=["Read"])
    assert len(calls) == 2
    for c in calls:
        assert "--allowedTools" in c
        assert c[c.index("--allowedTools") + 1] == "Read"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_claude_client.py -q -k run_structured`
Expected: FAIL — `TypeError: run_structured() got an unexpected keyword argument 'tools'`

- [ ] **Step 7: Implement the `tools` param on `run_structured`**

Edit `backend/claude_client.py` — replace the `run_structured` function (lines 170-182):

```python
def run_structured(prompt, *, model=DEFAULT_MODEL, validate=None, runner=_run_cli, tools=None):
    def args_for(p):
        args = ["-p", p]
        if tools:
            args += ["--allowedTools", *tools]  # variadic; terminated by the next --flag below
        args += ["--output-format", "json", "--model", model]
        return args
    for attempt in range(2):
        text = _result_text(runner(args_for(prompt)))
        obj = extract_json(text)
        if obj is not None and (validate is None or validate(obj)):
            return obj
        prompt = (
            prompt
            + "\n\nYour previous reply was not valid JSON matching the required shape. "
            "Reply again with ONLY the JSON object, no prose, no code fence."
        )
    raise ClaudeError("structured generation failed after retry")
```

- [ ] **Step 8: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_claude_client.py -q`
Expected: PASS (all tests in the file, including the pre-existing ones — the change is additive)

- [ ] **Step 9: Write the failing `backend/images.py` test suite**

Create `tests/test_images.py`:

```python
import json

from backend import images


_JPEG_BYTES = b"\xff\xd8\xff" + b"0" * 50
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 50
_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 50
_SVG_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


# ---- write_bytes_atomic already covered in tests/test_fsutil.py ----


# ---- license_allowed: fail-closed allowlist edge cases ----

def test_license_allowed_commons_edge_cases():
    assert images.license_allowed("Public domain") is True
    assert images.license_allowed("public domain") is True
    assert images.license_allowed("CC0") is True
    assert images.license_allowed("CC BY 4.0") is True
    assert images.license_allowed("CC BY-SA 3.0") is True
    assert images.license_allowed("CC BY-NC-SA 4.0") is False
    assert images.license_allowed("CC BY-ND 4.0") is False
    assert images.license_allowed("CC BY-NC 4.0") is False


def test_license_allowed_openverse_slugs():
    for ok in ("cc0", "pdm", "by", "by-sa"):
        assert images.license_allowed(ok) is True
    for bad in ("by-nc", "by-nd", "by-nc-sa", "by-nc-nd"):
        assert images.license_allowed(bad) is False


def test_license_allowed_rejects_non_string_and_empty():
    assert images.license_allowed(None) is False
    assert images.license_allowed("") is False
    assert images.license_allowed("   ") is False


# ---- strip_html / build_credit ----

def test_strip_html_removes_tags_and_trims():
    assert images.strip_html('<a href="//x">Jane Doe</a>') == "Jane Doe"
    assert images.strip_html("Plain text") == "Plain text"
    assert images.strip_html(None) == ""


def test_build_credit_uses_artist_html_for_commons_candidates():
    candidate = {"title": "File:Heart.png", "artistHtml": '<a href="//x">Jane Doe</a>',
                 "sourceUrl": "https://commons.wikimedia.org/wiki/File:Heart.png",
                 "licenseShort": "CC BY-SA 4.0"}
    credit = images.build_credit(candidate)
    assert "Jane Doe" in credit
    assert "<a" not in credit
    assert "File:Heart.png" in credit
    assert "CC BY-SA 4.0" in credit


def test_build_credit_uses_creator_for_openverse_candidates():
    candidate = {"title": "Cells photo", "creator": "Cara", "sourceUrl": "https://flickr.com/x",
                 "licenseShort": "by"}
    credit = images.build_credit(candidate)
    assert "Cara" in credit
    assert "Cells photo" in credit


# ---- download_verified: HTTP 200 + magic bytes + size cap ----

def test_download_verified_accepts_jpeg_png_webp():
    for data, ext in ((_JPEG_BYTES, "jpg"), (_PNG_BYTES, "png"), (_WEBP_BYTES, "webp")):
        result = images.download_verified("https://x/img", http_get=lambda url: data)
        assert result == (data, ext)


def test_download_verified_rejects_svg_named_png():
    result = images.download_verified("https://x/img.png", http_get=lambda url: _SVG_BYTES)
    assert result is None


def test_download_verified_rejects_oversize():
    big = _JPEG_BYTES + b"0" * (400 * 1024)
    result = images.download_verified("https://x/img", http_get=lambda url: big)
    assert result is None


def test_download_verified_returns_none_on_http_error():
    def boom(url):
        raise images.HTTPError(404)
    assert images.download_verified("https://x/img", http_get=boom) is None


# ---- _http_get: real implementation — User-Agent + timeout ----

def test_http_get_sends_required_user_agent_and_timeout(monkeypatch):
    import urllib.request
    captured = {}

    class FakeResponse:
        status = 200
        def read(self):
            return b"body"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = images._http_get("https://example.org/x.jpg")
    assert data == b"body"
    assert captured["timeout"] == 10
    # urllib.request.Request stores header keys via str.capitalize() ("User-agent",
    # not "User-Agent") and get_header() does a literal dict lookup with NO
    # normalization of its own — the stored casing must be used here.
    assert captured["req"].get_header("User-agent") == (
        "ClaudeUniversity/1.0 (personal learning app; wernerpvanellewee@gmail.com)")


def test_http_get_raises_http_error_on_non_200(monkeypatch):
    import urllib.request

    class FakeResponse:
        status = 500
        def read(self):
            return b""
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
    try:
        images._http_get("https://example.org/x.jpg")
        assert False, "expected HTTPError"
    except images.HTTPError as e:
        assert e.code == 500


# ---- commons_search: request shape + response parsing ----

def test_commons_search_builds_correct_request():
    import urllib.parse
    captured = {}
    def fake_http_get(url):
        captured["url"] = url
        return json.dumps({"query": {"pages": {}}}).encode()
    images.commons_search("heart anatomy", http_get=fake_http_get)
    url = captured["url"]
    assert url.startswith("https://commons.wikimedia.org/w/api.php?")
    decoded = urllib.parse.unquote_plus(url)
    assert "action=query" in decoded
    assert "generator=search" in decoded
    assert "gsrsearch=heart anatomy filetype:bitmap|drawing" in decoded
    assert "gsrnamespace=6" in decoded
    assert "gsrlimit=8" in decoded
    assert "prop=imageinfo" in decoded
    assert "iiprop=url|extmetadata" in decoded
    assert "iiurlwidth=800" in decoded
    assert "iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|AttributionRequired|Credit|UsageTerms" in decoded
    assert "format=json" in decoded


_COMMONS_FIXTURE = {
    "query": {
        "pages": {
            "111": {
                "title": "File:Heart diagram.png",
                "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/thumb/heart.png/800px-heart.png",
                    "url": "https://upload.wikimedia.org/heart.svg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Heart_diagram.png",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                        "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:Jane">Jane Doe</a>'},
                        "AttributionRequired": {"value": "true"},
                    },
                }],
            },
            "222": {
                "title": "File:Heart photo.jpg",
                "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/thumb/heart.jpg/800px-heart.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Heart_photo.jpg",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-NC-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-nc-sa/4.0"},
                        "Artist": {"value": "John Roe"},
                        "AttributionRequired": {"value": "true"},
                    },
                }],
            },
        },
    },
}


def test_commons_search_parses_candidates():
    def fake_http_get(url):
        return json.dumps(_COMMONS_FIXTURE).encode()
    candidates = images.commons_search("heart anatomy", http_get=fake_http_get)
    assert len(candidates) == 2
    diagram = next(c for c in candidates if "diagram" in c["title"].lower())
    assert diagram["thumbUrl"] == "https://upload.wikimedia.org/thumb/heart.png/800px-heart.png"
    assert diagram["licenseShort"] == "CC BY-SA 4.0"
    assert diagram["artistHtml"] == '<a href="//commons.wikimedia.org/wiki/User:Jane">Jane Doe</a>'
    assert diagram["attributionRequired"] is True
    assert diagram["sourceUrl"] == "https://commons.wikimedia.org/wiki/File:Heart_diagram.png"
    photo = next(c for c in candidates if "photo" in c["title"].lower())
    assert photo["licenseShort"] == "CC BY-NC-SA 4.0"  # normalized, NOT filtered here — filtering is the caller's job


def test_commons_search_returns_empty_on_http_error():
    def boom(url):
        raise images.HTTPError(503)
    assert images.commons_search("q", http_get=boom) == []


def test_commons_search_returns_empty_on_malformed_json():
    assert images.commons_search("q", http_get=lambda url: b"not json") == []


# ---- openverse_search: request shape + response parsing ----

def test_openverse_search_builds_correct_request():
    captured = {}
    def fake_http_get(url):
        captured["url"] = url
        return json.dumps({"results": []}).encode()
    images.openverse_search("cells dividing", http_get=fake_http_get)
    url = captured["url"]
    assert url.startswith("https://api.openverse.org/v1/images/?q=")
    assert "license=by,by-sa,cc0,pdm" in url
    assert "page_size=8" in url


_OPENVERSE_FIXTURE = {"results": [
    {"title": "Cells photo", "creator": "Cara", "thumbnail": "https://api.openverse.org/thumb/x",
     "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
     "foreign_landing_url": "https://flickr.com/x"},
]}


def test_openverse_search_parses_candidates():
    candidates = images.openverse_search("cells", http_get=lambda url: json.dumps(_OPENVERSE_FIXTURE).encode())
    assert len(candidates) == 1
    c = candidates[0]
    assert c["thumbUrl"] == "https://api.openverse.org/thumb/x"
    assert c["creator"] == "Cara"
    assert c["licenseShort"] == "by"
    assert c["sourceUrl"] == "https://flickr.com/x"


def test_openverse_search_returns_empty_on_429():
    def boom(url):
        raise images.HTTPError(429)
    assert images.openverse_search("q", http_get=boom) == []


# ---- strip_unresolved_figure_tokens ----

def test_strip_unresolved_figure_tokens_keeps_resolved_strips_rest():
    html = "<p>a</p>[[figure:1]]<p>b</p>[[figure:2]]<p>c</p>[[figure:3]]"
    out = images.strip_unresolved_figure_tokens(html, {1, 3})
    assert "[[figure:1]]" in out
    assert "[[figure:2]]" not in out
    assert "[[figure:3]]" in out


def test_strip_unresolved_figure_tokens_no_resolved_strips_all():
    html = "<p>a</p>[[figure:1]]"
    assert images.strip_unresolved_figure_tokens(html, set()) == "<p>a</p>"


# ---- vision_pick: pick / null / failure semantics ----

def test_vision_pick_returns_zero_based_index_for_valid_pick(tmp_path):
    def fake_workdir():
        d = tmp_path / "vp1"; d.mkdir(); return str(d)
    def fake_structured(prompt, *, validate, tools):
        assert tools == ["Read"]
        obj = {"pick": 2, "reason": "clearer labels"}
        assert validate(obj)
        return obj
    candidates = [(_JPEG_BYTES, "jpg"), (_PNG_BYTES, "png")]
    idx = images.vision_pick(candidates, "Heart anatomy", "Notice the valves",
                             structured=fake_structured, workdir=fake_workdir)
    assert idx == 1
    assert not (tmp_path / "vp1").exists()  # cleaned up


def test_vision_pick_null_pick_drops_figure(tmp_path):
    def fake_workdir():
        d = tmp_path / "vp2"; d.mkdir(); return str(d)
    def fake_structured(prompt, *, validate, tools):
        obj = {"pick": None, "reason": "none fit"}
        assert validate(obj)
        return obj
    idx = images.vision_pick([(_JPEG_BYTES, "jpg")], "T", "C",
                             structured=fake_structured, workdir=fake_workdir)
    assert idx is None


def test_vision_pick_failure_falls_back_to_first_candidate(tmp_path):
    def fake_workdir():
        d = tmp_path / "vp3"; d.mkdir(); return str(d)
    def boom(prompt, *, validate, tools):
        raise Exception("claude down")
    idx = images.vision_pick([(_JPEG_BYTES, "jpg"), (_PNG_BYTES, "png")], "T", "C",
                             structured=boom, workdir=fake_workdir)
    assert idx == 0
    assert not (tmp_path / "vp3").exists()  # cleaned up even on failure


def test_vision_pick_empty_candidates_returns_none(tmp_path):
    idx = images.vision_pick([], "T", "C", structured=lambda *a, **k: {}, workdir=lambda: str(tmp_path))
    assert idx is None


# ---- resolve_images: end-to-end orchestration ----

def test_resolve_images_happy_path(tmp_path):
    content_dir = tmp_path / "courses"
    commons_json = json.dumps({"query": {"pages": {
        "1": {"title": "File:A.png", "imageinfo": [{
            "thumburl": "https://upload.wikimedia.org/a.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.png",
            "extmetadata": {"LicenseShortName": {"value": "CC0"}, "Artist": {"value": "Ann"},
                            "AttributionRequired": {"value": "false"}}}]},
        "2": {"title": "File:B.png", "imageinfo": [{
            "thumburl": "https://upload.wikimedia.org/b.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:B.png",
            "extmetadata": {"LicenseShortName": {"value": "CC BY 4.0"}, "Artist": {"value": "Bob"},
                            "AttributionRequired": {"value": "true"}}}]},
    }}}).encode()

    def fake_http_get(url):
        if "commons.wikimedia.org" in url:
            return commons_json
        if url == "https://upload.wikimedia.org/a.png":
            return _PNG_BYTES
        if url == "https://upload.wikimedia.org/b.png":
            return _PNG_BYTES
        raise AssertionError(f"unexpected url {url}")  # Openverse must NOT be called: Commons gave 2 valid

    def fake_structured(prompt, *, validate=None, tools=None):
        obj = {"pick": 1, "reason": "clearest"}
        if validate:
            assert validate(obj)
        return obj

    slots = [{"query": "cells", "caption": "Notice the nucleus"}]
    resolved = images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                                     http_get=fake_http_get, structured=fake_structured)
    assert len(resolved) == 1
    entry = resolved[0]
    assert entry["n"] == 1
    assert entry["type"] == "web-image"
    assert entry["file"] == "demo-l1-1.png"
    assert entry["caption"] == "Notice the nucleus"
    assert (content_dir / "demo" / "images" / "demo-l1-1.png").read_bytes() == _PNG_BYTES


def test_resolve_images_no_candidates_drops_slot(tmp_path):
    content_dir = tmp_path / "courses"
    def fake_http_get(url):
        if "commons.wikimedia.org" in url:
            return json.dumps({"query": {"pages": {}}}).encode()
        if "api.openverse.org" in url:
            return json.dumps({"results": []}).encode()
        raise AssertionError(url)
    resolved = images.resolve_images("demo", "demo-l1", [{"query": "q", "caption": "c"}],
                                     content_dir=content_dir, http_get=fake_http_get,
                                     structured=lambda *a, **k: {"pick": 1})
    assert resolved == []
    assert not (content_dir / "demo" / "images").exists()


def test_resolve_images_openverse_429_skips_without_retry(tmp_path):
    content_dir = tmp_path / "courses"
    calls = {"openverse": 0}
    def fake_http_get(url):
        if "commons.wikimedia.org" in url:
            return json.dumps({"query": {"pages": {}}}).encode()  # 0 commons candidates
        if "api.openverse.org" in url:
            calls["openverse"] += 1
            raise images.HTTPError(429)
        raise AssertionError(url)
    resolved = images.resolve_images("demo", "demo-l1", [{"query": "q", "caption": "c"}],
                                     content_dir=content_dir, http_get=fake_http_get,
                                     structured=lambda *a, **k: {"pick": 1})
    assert resolved == []
    assert calls["openverse"] == 1  # tried once, no retry loop


def test_resolve_images_tops_up_from_openverse_when_commons_insufficient(tmp_path):
    content_dir = tmp_path / "courses"
    commons_json = json.dumps({"query": {"pages": {
        "1": {"title": "File:A.png", "imageinfo": [{
            "thumburl": "https://upload.wikimedia.org/a.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.png",
            "extmetadata": {"LicenseShortName": {"value": "CC0"}, "Artist": {"value": "Ann"},
                            "AttributionRequired": {"value": "false"}}}]},
    }}}).encode()
    openverse_json = json.dumps({"results": [
        {"title": "Cells photo", "creator": "Cara", "thumbnail": "https://api.openverse.org/thumb/x",
         "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
         "foreign_landing_url": "https://flickr.com/x"},
    ]}).encode()
    def fake_http_get(url):
        if "commons.wikimedia.org" in url:
            return commons_json
        if "api.openverse.org" in url:
            return openverse_json
        if url == "https://upload.wikimedia.org/a.png":
            return _PNG_BYTES
        if url == "https://api.openverse.org/thumb/x":
            return _JPEG_BYTES
        raise AssertionError(url)
    resolved = images.resolve_images("demo", "demo-l1", [{"query": "cells", "caption": "c"}],
                                     content_dir=content_dir, http_get=fake_http_get,
                                     structured=lambda *a, **k: {"pick": 1})
    assert len(resolved) == 1  # Commons(1 valid) + Openverse(1 valid) = 2 valid, downloads, picks


def test_resolve_images_resolver_exception_never_raises(tmp_path):
    content_dir = tmp_path / "courses"
    def boom(url):
        raise RuntimeError("network is down")
    resolved = images.resolve_images("demo", "demo-l1", [{"query": "q", "caption": "c"}],
                                     content_dir=content_dir, http_get=boom,
                                     structured=lambda *a, **k: {"pick": 1})
    assert resolved == []


def test_resolve_images_caps_at_three_slots(tmp_path):
    content_dir = tmp_path / "courses"
    slots = [{"query": f"q{i}", "caption": f"c{i}"} for i in range(5)]
    seen_ns = []
    def fake_http_get(url):
        return json.dumps({"query": {"pages": {}}}).encode() if "commons" in url \
            else json.dumps({"results": []}).encode()
    resolved = images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                                     http_get=fake_http_get, structured=lambda *a, **k: {"pick": 1})
    assert resolved == []  # no candidates either way, but this proves slots[3:] are never touched:
    # (deadline note: resolve_images has no injectable clock in this signature, so a
    # deadline-exceeded test is omitted per this plan's Ambiguity Resolution 6.)
```

- [ ] **Step 10: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_images.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.images'`

- [ ] **Step 11: Implement `backend/images.py`**

Create `backend/images.py`:

```python
"""Deterministic, license-checked figure resolver for lessons.

The model never picks image URLs — it writes a search query and a caption per
slot; every byte served to the browser was fetched, license-checked, magic-byte
verified, and cached by THIS module. Every function fails open: a bad query, a
network outage, an unlicensed result, or a broken candidate drops the figure —
it never blocks or fails a lesson.
"""

import json
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from backend import claude_client, fsutil

USER_AGENT = "ClaudeUniversity/1.0 (personal learning app; wernerpvanellewee@gmail.com)"

MAX_BYTES = 400 * 1024
MAX_DOWNLOADS_PER_SLOT = 4
MAX_SLOTS = 3

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"

_OPENVERSE_ALLOWED = {"cc0", "pdm", "by", "by-sa"}

FIGURE_TOKEN_RE = re.compile(r"\[\[figure:(\d+)\]\]")
_TAG_RE = re.compile(r"<[^>]+>")


class HTTPError(Exception):
    """Raised by _http_get (and any http_get implementation) for a non-200 response."""
    def __init__(self, code):
        self.code = code
        super().__init__(f"HTTP {code}")


def _http_get(url):
    """Real network fetch used by search and downloads alike: urllib.request with
    the mandatory descriptive User-Agent and a 10s timeout on EVERY request.
    Returns the raw response body bytes on HTTP 200; raises HTTPError(code)
    otherwise (including via urllib.error.HTTPError for a non-2xx response)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise HTTPError(e.code) from e
    if status != 200:
        raise HTTPError(status)
    return body


def commons_search(query, *, http_get):
    """Wikimedia Commons image search. Returns normalized candidate dicts:
    {thumbUrl, title, artistHtml, licenseShort, licenseUrl, sourceUrl,
    attributionRequired} — unfiltered by license (the caller filters via
    license_allowed). Never raises: any network/parse failure yields []."""
    params = [
        ("action", "query"),
        ("generator", "search"),
        ("gsrsearch", f"{query} filetype:bitmap|drawing"),
        ("gsrnamespace", "6"),
        ("gsrlimit", "8"),
        ("prop", "imageinfo"),
        ("iiprop", "url|extmetadata"),
        ("iiurlwidth", "800"),
        ("iiextmetadatafilter",
         "LicenseShortName|LicenseUrl|Artist|AttributionRequired|Credit|UsageTerms"),
        ("format", "json"),
    ]
    url = COMMONS_API + "?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(http_get(url))
    except Exception:
        return []
    pages = data.get("query", {}).get("pages", {}) if isinstance(data, dict) else {}
    if not isinstance(pages, dict):
        return []
    candidates = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        infos = page.get("imageinfo")
        if not isinstance(infos, list) or not infos or not isinstance(infos[0], dict):
            continue
        info = infos[0]
        thumb = info.get("thumburl")
        if not isinstance(thumb, str) or not thumb:
            continue
        meta = info.get("extmetadata")
        meta = meta if isinstance(meta, dict) else {}

        def _mv(key):
            v = meta.get(key)
            return v.get("value") if isinstance(v, dict) else None

        candidates.append({
            "thumbUrl": thumb,
            "title": page.get("title") or "",
            "artistHtml": _mv("Artist") or "",
            "licenseShort": _mv("LicenseShortName") or "",
            "licenseUrl": _mv("LicenseUrl"),
            "sourceUrl": info.get("descriptionurl") or "",
            "attributionRequired": str(_mv("AttributionRequired") or "").strip().lower() == "true",
        })
    return candidates


def openverse_search(query, *, http_get):
    """Openverse image search (fallback). Returns normalized candidate dicts:
    {thumbUrl, title, creator, licenseShort, licenseUrl, sourceUrl,
    attributionRequired}. Never raises: any network/parse failure — including a
    429 rate-limit — yields [] (the caller never retries)."""
    url = f"{OPENVERSE_API}?q={urllib.parse.quote(query)}&license=by,by-sa,cc0,pdm&page_size=8"
    try:
        data = json.loads(http_get(url))
    except Exception:
        return []
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    candidates = []
    for r in results:
        if not isinstance(r, dict):
            continue
        thumb = r.get("thumbnail")
        if not isinstance(thumb, str) or not thumb:
            continue
        candidates.append({
            "thumbUrl": thumb,
            "title": r.get("title") or "",
            "creator": r.get("creator") or "",
            "licenseShort": r.get("license") or "",
            "licenseUrl": r.get("license_url"),
            "sourceUrl": r.get("foreign_landing_url") or "",
            "attributionRequired": True,
        })
    return candidates


def license_allowed(value):
    """Fail-closed allowlist covering BOTH sources' license vocabularies (they
    never collide): Commons LicenseShortName case-insensitive equals "public
    domain"/"cc0", or starts with "cc by " / "cc by-sa " (space-terminated so
    NC/ND variants can never pass); Openverse license slug in
    {cc0, pdm, by, by-sa}."""
    if not isinstance(value, str) or not value.strip():
        return False
    lowered = value.strip().lower()
    if lowered in ("public domain", "cc0"):
        return True
    if lowered.startswith("cc by ") or lowered.startswith("cc by-sa "):
        return True
    return lowered in _OPENVERSE_ALLOWED


def strip_html(text):
    if not isinstance(text, str):
        return ""
    return _TAG_RE.sub("", text).strip()


def build_credit(candidate):
    """A plain-text TASL (Title, Author, Source, License) line. Commons
    candidates carry HTML in `artistHtml` (stripped here); Openverse candidates
    already carry a plain-text `creator`."""
    title = (candidate.get("title") or "Untitled").strip()
    if "artistHtml" in candidate:
        author = strip_html(candidate.get("artistHtml") or "") or "Unknown"
    else:
        author = (candidate.get("creator") or "").strip() or "Unknown"
    source = candidate.get("sourceUrl") or ""
    license_short = candidate.get("licenseShort") or ""
    parts = [title, author]
    if source:
        parts.append(source)
    if license_short:
        parts.append(license_short)
    return " — ".join(parts)


def download_verified(url, *, http_get):
    """Fetch + verify one candidate: HTTP 200 (enforced by http_get), magic
    bytes (jpeg/png/webp ONLY — SVG and anything else rejected regardless of
    extension/Content-Type), size <=400KB. Returns (bytes, ext) or None on ANY
    failure — never raises."""
    try:
        data = http_get(url)
    except Exception:
        return None
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_BYTES:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return bytes(data), "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return bytes(data), "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return bytes(data), "webp"
    return None


def strip_unresolved_figure_tokens(html, resolved_ns):
    """Remove [[figure:n]] tokens whose n is NOT in resolved_ns; tokens for
    resolved slots are left in place for the frontend to expand. Shared by the
    generation hook (Task 2) and the backfill validator (also Task 2)."""
    def repl(m):
        return m.group(0) if int(m.group(1)) in resolved_ns else ""
    return FIGURE_TOKEN_RE.sub(repl, html)


def _valid_pick_reply(n):
    def check(obj):
        if not isinstance(obj, dict) or "pick" not in obj:
            return False
        pick = obj["pick"]
        if pick is None:
            return True
        return isinstance(pick, int) and not isinstance(pick, bool) and 1 <= pick <= n
    return check


def _vision_prompt(topic, caption, paths):
    listed = "\n".join(f"{i}. {p}" for i, p in enumerate(paths, start=1))
    return (
        "You are picking the best candidate image for one figure in a personalized lesson.\n"
        f"Lesson topic: {topic}\n"
        f"Figure caption (what the learner should notice): {caption}\n"
        "Read each candidate image file below, then judge which one best matches the topic "
        "and lets the learner actually see what the caption describes. Candidate files:\n"
        f"{listed}\n"
        "Reply with ONLY a JSON object (no prose, no code fence): "
        '{"pick": <1-based index of the best candidate, or null if NONE of them genuinely fit>, '
        '"reason": "<one sentence>"}.'
    )


def vision_pick(candidates, topic, caption, *, structured, workdir):
    """One vision-assisted pick among downloaded candidates. candidates is a
    list of (bytes, ext) tuples (download_verified's return shape). Writes them
    to a scratch dir (workdir(), mirroring tempfile.mkdtemp's contract: creates
    the dir, returns its path) and calls structured(prompt, validate=...,
    tools=["Read"]) — signature-compatible with claude_client.run_structured.
    Returns a 0-based index into candidates, or None. Semantics: valid pick ->
    that index; explicit null -> None (drop the figure); ANY exception or
    invalid reply -> 0 (first candidate, fail open). Always cleans up the
    scratch dir."""
    if not candidates:
        return None
    tmpdir = Path(workdir())
    try:
        paths = []
        for i, (data, ext) in enumerate(candidates, start=1):
            p = tmpdir / f"candidate-{i}.{ext}"
            p.write_bytes(data)
            paths.append(str(p))
        prompt = _vision_prompt(topic, caption, paths)
        try:
            result = structured(prompt, validate=_valid_pick_reply(len(candidates)), tools=["Read"])
        except Exception:
            return 0
        if not isinstance(result, dict):
            return 0
        pick = result.get("pick")
        if pick is None:
            return None
        return pick - 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _resolve_one_slot(n, slot, course_id, lesson_id, *, images_dir, http_get, structured):
    query = slot.get("query")
    caption = slot.get("caption")
    if not (isinstance(query, str) and query.strip() and isinstance(caption, str) and caption.strip()):
        return None
    commons = commons_search(query, http_get=http_get)
    valid = [c for c in commons if license_allowed(c.get("licenseShort"))]
    if len(valid) < 2:
        openverse = openverse_search(query, http_get=http_get)
        valid = valid + [c for c in openverse if license_allowed(c.get("licenseShort"))]
    downloaded = []
    for candidate in valid:
        if len(downloaded) >= MAX_DOWNLOADS_PER_SLOT:
            break
        result = download_verified(candidate["thumbUrl"], http_get=http_get)
        if result is None:
            continue
        data, ext = result
        downloaded.append((candidate, data, ext))
    if not downloaded:
        return None
    pick = vision_pick(
        [(data, ext) for _, data, ext in downloaded], query, caption,
        structured=structured, workdir=tempfile.mkdtemp,
    )
    if pick is None:
        return None
    candidate, data, ext = downloaded[pick]
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{lesson_id}-{n}.{ext}"
    fsutil.write_bytes_atomic(images_dir / filename, data)
    return {
        "n": n,
        "type": "web-image",
        "file": filename,
        "caption": caption,
        "credit": build_credit(candidate),
        "license": candidate.get("licenseShort") or "",
        "licenseUrl": candidate.get("licenseUrl"),
        "sourceUrl": candidate.get("sourceUrl") or "",
    }


def _default_structured(prompt, *, validate=None, tools=None):
    return claude_client.run_structured(prompt, validate=validate, tools=tools)


def resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=_http_get,
                    structured=_default_structured, deadline_seconds=120):
    """Orchestrate the whole resolver for one lesson's image slots (0-3
    {query, caption} dicts). Per slot: Commons-first, top up from Openverse
    only if Commons yields <2 license-valid candidates (skipped entirely on a
    429), download+verify up to 4 candidates combined, one vision pick, atomic
    write to content_dir/course_id/images/<lesson_id>-<n>.<ext>. Returns the
    resolved entries list. Every failure path — network, license, download,
    vision, filesystem — drops that slot; this function never raises. The
    120s deadline is checked once per slot (between per-slot operations); on
    overrun, remaining slots are skipped (fail open)."""
    if not isinstance(slots, list):
        return []
    start = time.monotonic()
    images_dir = Path(content_dir) / course_id / "images"
    resolved = []
    for i, slot in enumerate(slots[:MAX_SLOTS], start=1):
        if time.monotonic() - start > deadline_seconds:
            break
        if not isinstance(slot, dict):
            continue
        try:
            entry = _resolve_one_slot(
                i, slot, course_id, lesson_id, images_dir=images_dir,
                http_get=http_get, structured=structured,
            )
        except Exception:
            entry = None
        if entry is not None:
            resolved.append(entry)
    return resolved
```

- [ ] **Step 12: Run the full backend test suite to verify it passes**

Run: `.venv/bin/pytest tests/test_images.py tests/test_fsutil.py tests/test_claude_client.py -q`
Expected: PASS (all tests). Then run the whole backend suite once to confirm nothing else broke:

Run: `.venv/bin/pytest -q`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add backend/fsutil.py backend/claude_client.py backend/images.py tests/test_fsutil.py tests/test_claude_client.py tests/test_images.py
git commit -m "$(cat <<'EOF'
feat(images): add the pure/injectable image resolver (backend/images.py)

Commons-first/Openverse-fallback search, fail-closed license allowlist,
magic-byte-verified downloads, and a vision-assisted pick — all injectable
and fail-open. Sibling fsutil.write_bytes_atomic and a run_structured
tools= param (for the vision Read call) support it.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Generation + routes integration — `backend/generation.py`, `backend/app.py`, backfill CLI

**Files:**
- Modify: `backend/generation.py` (imports at line 7; `valid_check`/`valid_lesson` at lines 191-221; `lesson_prompt` at lines 271-402; `_generate_and_store_lesson` at lines 1153-1237; `ensure_lesson` at lines 1240-1253; `deepen_lesson` at lines 1267-1273)
- Modify: `backend/app.py` (module-level `_ID_RE` at line 8; new route inserted between `post_apply_revision`, ending line 773, and `frontend_dir = ...` at line 775)
- Modify: `backend/images.py` (append the backfill CLI)
- Test: `tests/test_generation.py` (append near related tests; exact anchors given per step; the file currently ends at line 1781)
- Test: `tests/test_courses_api.py` (append after `_fixture_course`'s existing usages — new tests are self-contained, no fixed anchor needed)
- Test: `tests/test_images.py` (append backfill tests)

**Interfaces:**
- Consumes: `images.resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=..., structured=..., deadline_seconds=120) -> list[dict]` and `images.strip_unresolved_figure_tokens(html, resolved_ns) -> str` (Task 1); `generation.valid_lesson`, `generation.LESSON_KEYS`, `generation._generate_and_store_lesson`, `generation.ensure_lesson`, `generation.deepen_lesson` (existing); `app.py`'s `_ID_RE`, `courses.CONTENT_DIR`, `send_from_directory`, `jsonify` (existing).
- Produces: `generation.valid_images(images)`; `generation.valid_lesson` (now also enforces the if-present images shape); `lesson_prompt(...)` (additive `_IMAGES_BLOCK`, all existing substrings unchanged); `generation._generate_and_store_lesson(..., resolve_images=None)`; `generation.ensure_lesson(..., resolve_images=None)`; `generation.deepen_lesson(..., resolve_images=None)`; the lesson JSON's `images` field, post-resolution, exactly `[{n, type:"web-image", file, caption, credit, license, licenseUrl, sourceUrl}, ...]`; route `GET /api/courses/<course_id>/images/<filename>`; `images.backfill_prompt(lesson)`, `images._valid_backfill_proposal(obj, original_prompt_html)`, `images.backfill_course(content_dir, course_id, *, generate) -> int`, CLI `python -m backend.images <course_id>|--all`. Task 3 relies on the `images` field shape and the serving route contract above.

- [ ] **Step 1: Write the failing `lesson_prompt` and `valid_lesson` tests**

Append to `tests/test_generation.py`, directly after `test_lesson_prompt_has_creative_teaching_guidance` (search for it; it is the last `lesson_prompt`-focused test before the sources-grounding section) — placement is not line-critical, append anywhere below the existing `lesson_prompt`/`valid_lesson` tests and above `test_lesson_chat_prompt_includes_lesson_context`:

```python
def test_lesson_prompt_includes_images_slot_instructions():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    assert "[[figure:1]]" in p
    assert "[[figure:2]]" in p
    assert "images" in p and "query" in p and "caption" in p
    assert "NEVER decorative" in p
    assert "zero images is often correct" in p


def test_valid_lesson_images_absent_stays_valid():
    good = {k: "x" for k in gen.LESSON_KEYS}
    good["checks"] = [dict(_OK_CHECK)]
    good["preQuiz"] = dict(_OK_PREQUIZ)
    good["spine"] = _ok_spine()
    assert gen.valid_lesson(good) is True  # no "images" key at all


def test_valid_lesson_images_shape_when_present():
    base = {k: "x" for k in gen.LESSON_KEYS}
    base["checks"] = [dict(_OK_CHECK)]
    base["preQuiz"] = dict(_OK_PREQUIZ)
    base["spine"] = _ok_spine()
    base["images"] = [{"query": "q1", "caption": "c1"}]
    assert gen.valid_lesson(base) is True
    base["images"] = [{"query": "q1", "caption": "c1"}] * 4
    assert gen.valid_lesson(base) is False  # >3
    base["images"] = [{"query": "", "caption": "c1"}]
    assert gen.valid_lesson(base) is False  # blank query
    base["images"] = [{"query": "q1"}]
    assert gen.valid_lesson(base) is False  # missing caption
    base["images"] = "not a list"
    assert gen.valid_lesson(base) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -q -k "images_slot_instructions or valid_lesson_images"`
Expected: FAIL — the substring assertions fail (no images block yet) and `valid_lesson` accepts/rejects incorrectly (no images check yet)

- [ ] **Step 3: Add `_IMAGES_BLOCK` and wire it into `lesson_prompt`; add `valid_images` and wire it into `valid_lesson`**

Edit `backend/generation.py` — insert `_IMAGES_BLOCK` right before `def lesson_prompt(`:

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
)


def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
```

Edit the end of `lesson_prompt`'s return statement — change:

```python
        "specific and high-quality turns up, include NO video rather than a loose match."
        + spine_context + obj_block + directive_line
    )
```

to:

```python
        "specific and high-quality turns up, include NO video rather than a loose match."
        + _IMAGES_BLOCK
        + spine_context + obj_block + directive_line
    )
```

Add `valid_images` right before `def valid_lesson(obj):`:

```python
def valid_images(images_val):
    """If-present shape check for the raw generator output's images slots
    ({query, caption} dicts). Absent (None) stays valid — cached lessons
    without the field, and lessons that legitimately have zero figures, are
    unaffected. Parameter is NOT named `images` — that name is now the
    imported backend.images module in this file's global scope."""
    if images_val is None:
        return True
    if not (isinstance(images_val, list) and len(images_val) <= 3):
        return False
    for slot in images_val:
        if not isinstance(slot, dict):
            return False
        for field in ("query", "caption"):
            if not (isinstance(slot.get(field), str) and slot[field].strip()):
                return False
    return True
```

Edit `valid_lesson` — add the images check:

```python
def valid_lesson(obj):
    if not (isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)):
        return False
    for field in ("promptHtml", "hintHtml", "solutionAns", "solutionNote"):
        if not (isinstance(obj.get(field), str) and obj[field].strip()):
            return False
    checks = obj.get("checks")
    if not (isinstance(checks, list) and 1 <= len(checks) <= 3):
        return False
    if not valid_check(obj.get("preQuiz")):
        return False
    if not spine.valid_spine_entry(obj.get("spine")):
        return False
    if not valid_images(obj.get("images")):
        return False
    return all(valid_check(c) for c in checks)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -q -k "images_slot_instructions or valid_lesson_images"`
Expected: PASS

Then run the whole file to confirm no existing substring test broke:

Run: `.venv/bin/pytest tests/test_generation.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing `_generate_and_store_lesson`/`ensure_lesson`/`deepen_lesson` integration tests**

Append to `tests/test_generation.py` (anywhere after `_course` is defined, e.g. right after `test_ensure_lesson_reconciles_ids_and_step`):

```python
def test_ensure_lesson_resolves_images_and_strips_unresolved_tokens(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["promptHtml"] = "<p>Intro.</p>[[figure:1]]<p>More.</p>[[figure:2]]"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["images"] = [{"query": "q1", "caption": "c1"}, {"query": "q2", "caption": "c2"}]

    def fake_resolver(course_id, lesson_id, slots, *, content_dir):
        return [{"n": 1, "type": "web-image", "file": "demo-l1-1.jpg", "caption": "c1",
                 "credit": "cred", "license": "CC BY 4.0", "licenseUrl": "https://x",
                 "sourceUrl": "https://y"}]

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=fake_resolver)
    assert out["images"] == [{"n": 1, "type": "web-image", "file": "demo-l1-1.jpg", "caption": "c1",
                               "credit": "cred", "license": "CC BY 4.0", "licenseUrl": "https://x",
                               "sourceUrl": "https://y"}]
    assert "[[figure:1]]" in out["promptHtml"]
    assert "[[figure:2]]" not in out["promptHtml"]


def test_ensure_lesson_resolver_exception_stores_lesson_without_figures(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["promptHtml"] = "<p>Intro.</p>[[figure:1]]"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["images"] = [{"query": "q1", "caption": "c1"}]

    def boom(course_id, lesson_id, slots, *, content_dir):
        raise RuntimeError("archive outage")

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=boom)
    assert out["images"] == []
    assert "[[figure:1]]" not in out["promptHtml"]
    assert "<p>Intro.</p>" in out["promptHtml"]


def test_ensure_lesson_without_images_slots_never_calls_resolver(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()

    def boom(*a, **kw):
        raise AssertionError("resolver should not be called")

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made),
                            resolve_images=boom)
    assert out["images"] == []


def test_deepen_lesson_re_resolves_images(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
                                "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    original = {"id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
               "eyebrow": "EXERCISE", "promptHtml": "<p>shallow</p>", "hintHtml": "h",
               "solutionAns": "a", "solutionNote": "n", "checks": [dict(_OK_CHECK)],
               "images": [{"n": 1, "type": "web-image", "file": f"{lid}-1.jpg", "caption": "old",
                           "credit": "c", "license": "CC0", "licenseUrl": None, "sourceUrl": "https://z"}]}
    path = root / cid / "lessons" / f"{lid}.json"
    path.write_text(_json.dumps(original))

    calls = []
    def fake_resolver(course_id, lesson_id, slots, *, content_dir):
        calls.append(slots)
        return [{"n": 1, "type": "web-image", "file": f"{lid}-1.jpg", "caption": "new",
                 "credit": "c2", "license": "CC0", "licenseUrl": None, "sourceUrl": "https://z2"}]

    def fake_generate(prompt):
        return {"id": "wrong", "courseId": "wrong", "topic": "deeper", "step": 9, "totalSteps": 9,
                "eyebrow": "EXERCISE", "promptHtml": "<p>deeper</p>[[figure:1]]",
                "hintHtml": "h2", "solutionAns": "a2", "solutionNote": "n2", "checks": [dict(_OK_CHECK)],
                "preQuiz": dict(_OK_PREQUIZ), "spine": _ok_spine(),
                "images": [{"query": "q", "caption": "new"}]}

    lesson = gen.deepen_lesson(root, cid, lid, {}, generate=fake_generate, resolve_images=fake_resolver)
    assert len(calls) == 1
    assert lesson["images"][0]["caption"] == "new"
    on_disk = _json.loads(path.read_text())
    assert on_disk["images"][0]["caption"] == "new"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -q -k "resolves_images or resolver_exception or without_images_slots or re_resolves_images"`
Expected: FAIL — `TypeError: ensure_lesson() got an unexpected keyword argument 'resolve_images'` (and `deepen_lesson` likewise)

- [ ] **Step 7: Wire the resolver hook into `_generate_and_store_lesson`, `ensure_lesson`, `deepen_lesson`**

Edit `backend/generation.py` — add `images` to the top import (line 7):

```python
from backend import claude_client, courses, fsutil, images, spine
```

Edit `_generate_and_store_lesson`'s signature and body — insert the hook right after the `valid_lesson` check and before the spine-entry pop:

```python
def _generate_and_store_lesson(content_dir, course_id, lesson_id, profile, *, generate,
                               performance="", directive="", verify_generate=None,
                               prior_knowledge="", resolve_images=None):
```

(only the trailing `resolve_images=None` parameter is new; everything else in the signature is unchanged)

```python
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    # Image resolution: the ONLY hook point that covers both cache-miss generation
    # AND deepen (deepen overwrites the lesson file wholesale). Fails open: any
    # exception here means the lesson ships with zero figures, never a blocked lesson.
    slots = lesson.pop("images", None)
    resolver = resolve_images or images.resolve_images
    resolved = []
    if isinstance(slots, list) and slots:
        try:
            resolved = resolver(course_id, lesson_id, slots, content_dir=content_dir)
        except Exception:
            resolved = []
    lesson["images"] = resolved
    resolved_ns = {e["n"] for e in resolved if isinstance(e, dict) and isinstance(e.get("n"), int)}
    lesson["promptHtml"] = images.strip_unresolved_figure_tokens(lesson["promptHtml"], resolved_ns)
    # The spine entry is generation-side state, not lesson content: pop it before
```

(the comment line `# The spine entry is generation-side state...` and everything below it, i.e. `spine_entry = lesson.pop("spine")` onward, is UNCHANGED — the hook is inserted directly above it)

Edit `ensure_lesson`:

```python
def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance="",
                  verify_generate=None, prior_knowledge="", resolve_images=None):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    with _gen_lock(("lesson", course_id, lesson_id)):
        existing = courses.load_lesson(content_dir, course_id, lesson_id)
        if existing is not None:
            return existing  # a concurrent request generated it while we waited
        return _generate_and_store_lesson(
            content_dir, course_id, lesson_id, profile, generate=generate,
            performance=performance, verify_generate=verify_generate,
            prior_knowledge=prior_knowledge, resolve_images=resolve_images,
        )
```

Edit `deepen_lesson`:

```python
def deepen_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance="",
                  verify_generate=None, prior_knowledge="", resolve_images=None):
    return _generate_and_store_lesson(
        content_dir, course_id, lesson_id, profile, generate=generate,
        performance=performance, directive=_DEEPEN_DIRECTIVE, verify_generate=verify_generate,
        prior_knowledge=prior_knowledge, resolve_images=resolve_images,
    )
```

- [ ] **Step 8: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -q`
Expected: PASS (all tests in the file)

- [ ] **Step 9: Write the failing image-serving route tests**

Append to `tests/test_courses_api.py` (anywhere after `_client` is defined, e.g. near the end of the file):

```python
def test_course_image_route_serves_file(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-1.jpg").write_bytes(b"\xff\xd8\xffjpegdata")
    resp = client.get("/api/courses/demo/images/demo-l1-1.jpg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"
    assert resp.data == b"\xff\xd8\xffjpegdata"


def test_course_image_route_serves_webp(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-2.webp").write_bytes(b"RIFF0000WEBPdata")
    resp = client.get("/api/courses/demo/images/demo-l1-2.webp")
    assert resp.status_code == 200
    assert resp.mimetype == "image/webp"


def test_course_image_route_404s_on_bad_extension(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "demo-l1-1.svg").write_bytes(b"<svg></svg>")
    resp = client.get("/api/courses/demo/images/demo-l1-1.svg")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_course_image_route_404s_on_uppercase_filename(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "demo" / "images").mkdir(parents=True)
    (tmp_path / "demo" / "images" / "DEMO-L1-1.jpg").write_bytes(b"\xff\xd8\xff")
    resp = client.get("/api/courses/demo/images/DEMO-L1-1.jpg")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_course_image_route_404s_on_bad_course_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/courses/UPPER_CASE/images/demo-l1-1.jpg")
    assert resp.status_code == 404


def test_course_image_route_404s_on_path_traversal_attempt(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    # A traversal payload passed as the filename segment either fails routing
    # entirely (extra path segments) or reaches the view and fails the strict
    # filename regex — both outcomes are a 404, which is the only property
    # this test needs to prove (no traversal ever serves a file).
    resp = client.get("/api/courses/demo/images/..%2f..%2fapp.py")
    assert resp.status_code == 404
```

- [ ] **Step 10: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_courses_api.py -q -k course_image_route`
Expected: FAIL — 404 for all (no route exists yet) is close but the 200 tests fail with 404 too

- [ ] **Step 11: Add the image-serving route**

Edit `backend/app.py` — add a second module-level regex right after `_ID_RE` (line 8):

```python
_ID_RE = _re.compile(r"^[a-z0-9-]+$")
_IMAGE_FILENAME_RE = _re.compile(r"^[a-z0-9-]+-\d\.(jpg|png|webp)$")
```

Insert the new route between `post_apply_revision` (ends line 773) and `frontend_dir = ...` (line 775):

```python
    @app.post("/api/courses/<course_id>/apply-revision")
    def post_apply_revision(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        revised = body.get("course")
        written = courses.apply_revision(courses.CONTENT_DIR, course_id, revised)
        if written is None:
            return jsonify({"error": "invalid revision"}), 400
        return jsonify({"course": written})

    @app.get("/api/courses/<course_id>/images/<filename>")
    def course_image(course_id, filename):
        if not _ID_RE.match(course_id) or not _IMAGE_FILENAME_RE.match(filename):
            return jsonify({"error": "image not found"}), 404
        return send_from_directory(str(courses.CONTENT_DIR / course_id / "images"), filename)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
```

(the `post_apply_revision` function body above the new route is UNCHANGED — shown only for anchoring)

- [ ] **Step 12: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_courses_api.py -q -k course_image_route`
Expected: PASS

Then run the whole file:

Run: `.venv/bin/pytest tests/test_courses_api.py -q`
Expected: PASS

- [ ] **Step 13: Write the failing backfill CLI tests**

Append to `tests/test_images.py`:

```python
def test_backfill_prompt_includes_lesson_body_and_shape_instructions():
    lesson = {"topic": "Cells", "promptHtml": "<p>Cells divide.</p>"}
    p = images.backfill_prompt(lesson)
    assert "Cells divide." in p
    assert "[[figure:1]]" in p
    assert "images" in p and "promptHtml" in p


def test_valid_backfill_proposal_rejects_rewritten_prose():
    original = "<p>Cells divide.</p>"
    good = {"images": [{"query": "q", "caption": "c"}], "promptHtml": "<p>Cells divide.</p>[[figure:1]]"}
    bad = {"images": [{"query": "q", "caption": "c"}], "promptHtml": "<p>Cells split apart.</p>[[figure:1]]"}
    assert images._valid_backfill_proposal(good, original) is True
    assert images._valid_backfill_proposal(bad, original) is False


def test_valid_backfill_proposal_rejects_bad_images_shape():
    original = "<p>x</p>"
    bad = {"images": [{"query": "q"}], "promptHtml": "<p>x</p>"}
    assert images._valid_backfill_proposal(bad, original) is False
    ok_empty = {"images": [], "promptHtml": "<p>x</p>"}
    assert images._valid_backfill_proposal(ok_empty, original) is True


def test_backfill_course_skips_lessons_already_carrying_images(tmp_path):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    already = {"id": "demo-l1", "promptHtml": "<p>x</p>", "images": []}
    (root / "demo" / "lessons" / "demo-l1.json").write_text(json.dumps(already))
    calls = []
    def generate(prompt, validate):
        calls.append(prompt)
        return {"images": [], "promptHtml": "<p>x</p>"}
    count = images.backfill_course(root, "demo", generate=generate)
    assert count == 0
    assert calls == []


def test_backfill_course_resolves_and_rewrites_pending_lesson(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    pending = {"id": "demo-l1", "topic": "t", "promptHtml": "<p>Cells divide.</p>"}
    path = root / "demo" / "lessons" / "demo-l1.json"
    path.write_text(json.dumps(pending))

    def generate(prompt, validate):
        obj = {"images": [{"query": "q", "caption": "c"}],
               "promptHtml": "<p>Cells divide.</p>[[figure:1]]"}
        assert validate(obj)
        return obj

    def fake_resolve(course_id, lesson_id, slots, *, content_dir):
        return [{"n": 1, "type": "web-image", "file": "demo-l1-1.jpg", "caption": "c",
                 "credit": "cred", "license": "CC0", "licenseUrl": None, "sourceUrl": "https://x"}]
    monkeypatch.setattr(images, "resolve_images", fake_resolve)

    count = images.backfill_course(root, "demo", generate=generate)
    assert count == 1
    on_disk = json.loads(path.read_text())
    assert on_disk["images"][0]["file"] == "demo-l1-1.jpg"
    assert "[[figure:1]]" in on_disk["promptHtml"]


def test_backfill_course_resolver_exception_still_writes_lesson_without_figures(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    pending = {"id": "demo-l1", "topic": "t", "promptHtml": "<p>Cells divide.</p>"}
    path = root / "demo" / "lessons" / "demo-l1.json"
    path.write_text(json.dumps(pending))

    def generate(prompt, validate):
        return {"images": [{"query": "q", "caption": "c"}],
                "promptHtml": "<p>Cells divide.</p>[[figure:1]]"}

    def boom(*a, **kw):
        raise RuntimeError("archive outage")
    monkeypatch.setattr(images, "resolve_images", boom)

    count = images.backfill_course(root, "demo", generate=generate)
    assert count == 1
    on_disk = json.loads(path.read_text())
    assert on_disk["images"] == []
    assert "[[figure:1]]" not in on_disk["promptHtml"]


def test_backfill_course_missing_course_returns_zero(tmp_path):
    assert images.backfill_course(tmp_path / "courses", "no-such-course", generate=lambda p, v: {}) == 0
```

- [ ] **Step 14: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_images.py -q -k backfill`
Expected: FAIL — `AttributeError: module 'backend.images' has no attribute 'backfill_prompt'`

- [ ] **Step 15: Implement the backfill CLI**

Edit `backend/images.py` — append at the end of the file (after `resolve_images`):

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
    )


def _valid_images_slots(images_val):
    """Backfill-specific images-shape check: unlike generation.valid_images,
    the key must ALWAYS be a list (possibly empty) — the proposal always states
    a decision, it never omits the field."""
    if not (isinstance(images_val, list) and len(images_val) <= MAX_SLOTS):
        return False
    for slot in images_val:
        if not isinstance(slot, dict):
            return False
        for field in ("query", "caption"):
            if not (isinstance(slot.get(field), str) and slot[field].strip()):
                return False
    return True


def _valid_backfill_proposal(obj, original_prompt_html):
    if not isinstance(obj, dict):
        return False
    if not _valid_images_slots(obj.get("images")):
        return False
    proposed_html = obj.get("promptHtml")
    if not isinstance(proposed_html, str):
        return False
    return FIGURE_TOKEN_RE.sub("", proposed_html) == original_prompt_html


def backfill_course(content_dir, course_id, *, generate):
    """One-off retrofit: propose figure placements for every cached lesson in
    course_id that doesn't carry an images field yet, resolve them, and rewrite
    the lesson JSON. generate(prompt, validate) -> validated dict (the
    run_structured convention). Idempotent — already-retrofitted lessons are
    skipped, so re-running is safe. A flaky single lesson never blocks the
    batch. Returns the number of lessons updated."""
    lessons_dir = Path(content_dir) / course_id / "lessons"
    if not lessons_dir.is_dir():
        return 0
    updated = 0
    for path in sorted(lessons_dir.glob("*.json")):
        try:
            lesson = json.loads(path.read_text())
        except ValueError:
            continue
        if not isinstance(lesson, dict) or "images" in lesson:
            continue
        lesson_id = path.stem
        original_html = lesson.get("promptHtml", "")
        try:
            proposal = generate(
                backfill_prompt(lesson),
                lambda o: _valid_backfill_proposal(o, original_html),
            )
        except claude_client.ClaudeError:
            continue  # never block the batch on one flaky lesson
        lesson["promptHtml"] = proposal["promptHtml"]
        try:
            resolved = resolve_images(course_id, lesson_id, proposal["images"], content_dir=content_dir)
        except Exception:
            resolved = []
        lesson["images"] = resolved
        resolved_ns = {e["n"] for e in resolved if isinstance(e, dict) and isinstance(e.get("n"), int)}
        lesson["promptHtml"] = strip_unresolved_figure_tokens(lesson["promptHtml"], resolved_ns)
        fsutil.write_text_atomic(path, json.dumps(lesson, indent=2, ensure_ascii=False))
        updated += 1
    return updated


if __name__ == "__main__":
    import sys

    _content_dir = Path(__file__).resolve().parent.parent / "content" / "courses"
    _run = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
    if len(sys.argv) != 2 or (sys.argv[1] != "--all" and not re.match(r"^[a-z0-9-]+$", sys.argv[1])):
        print("usage: python -m backend.images <course_id>|--all")
        raise SystemExit(1)
    if sys.argv[1] == "--all":
        _course_ids = sorted(p.name for p in _content_dir.iterdir() if p.is_dir())
    else:
        _course_ids = [sys.argv[1]]
    for _cid in _course_ids:
        _count = backfill_course(_content_dir, _cid, generate=_run)
        print(f"{_cid}: {_count} lessons backfilled with images")
```

- [ ] **Step 16: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_images.py -q -k backfill`
Expected: PASS

Then run the full backend suite:

Run: `.venv/bin/pytest -q`
Expected: PASS

- [ ] **Step 17: Commit**

```bash
git add backend/generation.py backend/app.py backend/images.py tests/test_generation.py tests/test_courses_api.py tests/test_images.py
git commit -m "$(cat <<'EOF'
feat(images): hook the resolver into lesson generation + serve cached images

lesson_prompt asks for 0-3 image slots with placement tokens; the resolver
runs inside _generate_and_store_lesson (covers cache-miss AND deepen) and
fails open on any exception. New GET /api/courses/<id>/images/<file> route
serves cached bytes. A backfill CLI retrofits existing cached lessons.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend rendering — `frontend/src/views/lesson.js`, `styles.css`

**Files:**
- Modify: `frontend/src/views/lesson.js` (imports at lines 1-4; `lessonSourcesHTML` at lines 75-86 for the "Figures" block precedent; `lessonHTML` at lines 191-291, specifically the `<div class="prompt">` line at 252 and the `.lesson` card's closing `</section>` at line 264)
- Modify: `frontend/styles.css` (insert after the `.prompt .box{...}` rule, line 166-167)
- Test: `frontend/tests/views.test.js` (append after `test("workspace chat shows the socratic banner and Exit only when the mode is on")`, ends line 262, before `test("diagnostic renders all six questions and gates Continue")` at line 264)

**Interfaces:**
- Consumes: `esc(s)` from `frontend/src/escape.js:1`; the lesson JSON's `images` field shape from Task 2, exactly `[{n, type:"web-image", file, caption, credit, license, licenseUrl, sourceUrl}, ...]`; `lesson.courseId` (already set on every lesson object by `_generate_and_store_lesson`); the `GET /api/courses/<course_id>/images/<filename>` route from Task 2; the filename regex `^[a-z0-9-]+-\d\.(jpg|png|webp)$` (must match the backend's exactly).
- Produces: `expandFigureTokens(promptHtml, lesson, courseId) -> {html, figuresBlock}`, exported from `frontend/src/views/lesson.js`; `.lesson-fig`, `.fig-credit`, `.lesson-figures` CSS classes (reuses the existing `.ls-head` class for the "Figures" heading).

- [ ] **Step 1: Write the failing `expandFigureTokens` tests**

Append to `frontend/tests/views.test.js`, directly after `test("workspace chat shows the socratic banner and Exit only when the mode is on", ...)` (ends line 262) and before `test("diagnostic renders all six questions and gates Continue", ...)` (line 264). First, extend the import line at the top of the file (line 5):

```js
import { lessonHTML, ratingLocked, suggestedQuality, expandFigureTokens } from "../src/views/lesson.js";
```

Then append the new tests:

```js
test("expandFigureTokens renders a figure with caption, credit, and license link", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "Notice the valves",
    credit: "Heart diagram — Jane Doe — CC BY-SA 4.0", license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0", sourceUrl: "https://commons.wikimedia.org/x" }] };
  const { html, figuresBlock } = expandFigureTokens("<p>Intro.</p>[[figure:1]]<p>More.</p>", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig">/);
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
  assert.match(html, /loading="lazy"/);
  assert.match(html, /alt="Notice the valves"/);
  assert.match(html, /Notice the valves/);
  assert.match(html, /Heart diagram — Jane Doe — CC BY-SA 4\.0/);
  assert.match(html, /href="https:\/\/creativecommons\.org\/licenses\/by-sa\/4\.0"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, />CC BY-SA 4\.0<\/a>/);
  assert.equal(figuresBlock, "");
});

test("expandFigureTokens falls back to sourceUrl when licenseUrl is null", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "c",
    credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "https://commons.wikimedia.org/x" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /href="https:\/\/commons\.wikimedia\.org\/x"/);
});

test("expandFigureTokens escapes caption, credit, and license text (no raw HTML)", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "<script>alert(1)</script>",
    credit: '"><img src=x onerror=alert(1)>',
    license: "</a><b>x</b>", licenseUrl: "https://example.org", sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<\/a><b>/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /&quot;&gt;&lt;img/);
  assert.match(html, /&lt;\/a&gt;&lt;b&gt;x&lt;\/b&gt;/);
});

test("expandFigureTokens skips an entry whose filename fails the client-side regex", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "../evil.jpg",
    caption: "c", credit: "c", license: "CC0", licenseUrl: null, sourceUrl: "" }] };
  const { html, figuresBlock } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<figure/);
  assert.equal(html, "");
  assert.equal(figuresBlock, "");
});

test("expandFigureTokens strips a token with no matching images entry", () => {
  const lesson = { images: [] };
  const { html } = expandFigureTokens("<p>a</p>[[figure:1]]<p>b</p>", lesson, "demo");
  assert.equal(html, "<p>a</p><p>b</p>");
});

test("expandFigureTokens expands only the first occurrence of a duplicated token", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "c", credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]x[[figure:1]]", lesson, "demo");
  const count = (html.match(/<figure class="lesson-fig">/g) || []).length;
  assert.equal(count, 1);
});

test("expandFigureTokens renders a tokenless entry in a trailing Figures block", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "Retro caption", credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const { html, figuresBlock } = expandFigureTokens("<p>no tokens here</p>", lesson, "demo");
  assert.equal(html, "<p>no tokens here</p>");
  assert.match(figuresBlock, /<section class="card lesson-figures">/);
  assert.match(figuresBlock, />Figures</);
  assert.match(figuresBlock, /Retro caption/);
});

test("expandFigureTokens renders nothing for an unknown figure type", () => {
  const lesson = { images: [{ n: 1, type: "mermaid", code: "graph TD;", caption: "c" }] };
  const { html, figuresBlock } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.equal(html, "");
  assert.equal(figuresBlock, "");
});

test("expandFigureTokens with no images field leaves promptHtml untouched", () => {
  const { html, figuresBlock } = expandFigureTokens("<p>A weight <code>w</code>.</p>", SAMPLE_LESSON, "demo");
  assert.equal(html, "<p>A weight <code>w</code>.</p>");
  assert.equal(figuresBlock, "");
});

test("lesson renders an expanded figure from lesson.images at its token position", () => {
  const lesson = { ...SAMPLE_LESSON, courseId: "demo",
    promptHtml: "<p>A weight <code>w</code> has gradient.</p>[[figure:1]]",
    images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "See the slope",
               credit: "cred", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const html = lessonHTML(lesson, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /<figure class="lesson-fig">/);
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
});

test("lesson renders SAMPLE_LESSON (no images field) unaffected by figure expansion", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(html, /lesson-fig/);
});

test("a figure token typed in a chat message is not expanded (chat stays plain esc'd text)", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "[[figure:1]] test" }],
          pending: false, saveStatus: "" } });
  assert.match(html, /\[\[figure:1\]\] test/);
  assert.doesNotMatch(html, /<figure class="lesson-fig">/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test frontend/tests/*.test.js`
Expected: FAIL — `SyntaxError`/import error, `expandFigureTokens` is not exported from `../src/views/lesson.js`

- [ ] **Step 3: Implement `expandFigureTokens` and wire it into `lessonHTML`**

Edit `frontend/src/views/lesson.js` — add the token/regex constants and helper functions right after `lessonSourcesHTML` (ends line 86) and before the `conceptChipsHTML` comment (line 88):

```js
const FIGURE_TOKEN_RE = /\[\[figure:(\d+)\]\]/g;
const FIGURE_FILENAME_RE = /^[a-z0-9-]+-\d\.(jpg|png|webp)$/;

function figureHTML(entry, courseId) {
  const src = `/api/courses/${esc(courseId)}/images/${esc(entry.file)}`;
  const licenseHref = entry.licenseUrl || entry.sourceUrl || "";
  return (
    `<figure class="lesson-fig"><img src="${src}" alt="${esc(entry.caption)}" loading="lazy">` +
    `<figcaption>${esc(entry.caption)} <span class="fig-credit">${esc(entry.credit)} ` +
    `<a href="${esc(licenseHref)}" target="_blank" rel="noopener noreferrer">${esc(entry.license)}</a>` +
    `</span></figcaption></figure>`
  );
}

// Pure pre-render transform: expands [[figure:n]] tokens ONLY against this lesson's
// OWN backend-written images array, and ONLY for type:"web-image" entries (unknown
// types — e.g. a future slice-2 "mermaid"/"svg" — render nothing here). Returns the
// expanded promptHtml plus a separate trailing block for entries whose token never
// appeared in the prose (the retrofit/backfill case).
export function expandFigureTokens(promptHtml, lesson, courseId) {
  const entries = Array.isArray(lesson.images) ? lesson.images : [];
  const byN = new Map();
  for (const entry of entries) {
    if (entry && entry.type === "web-image" && typeof entry.n === "number"
        && typeof entry.file === "string" && FIGURE_FILENAME_RE.test(entry.file)
        && !byN.has(entry.n)) {
      byN.set(entry.n, entry);
    }
  }
  const used = new Set();
  const html = promptHtml.replace(FIGURE_TOKEN_RE, (match, nStr) => {
    const n = Number(nStr);
    if (used.has(n) || !byN.has(n)) return "";
    used.add(n);
    return figureHTML(byN.get(n), courseId);
  });
  const trailing = Array.from(byN.entries())
    .filter(([n]) => !used.has(n))
    .map(([, entry]) => figureHTML(entry, courseId))
    .join("");
  const figuresBlock = trailing
    ? `<section class="card lesson-figures"><div class="ls-head">Figures</div>${trailing}</section>`
    : "";
  return { html, figuresBlock };
}
```

Edit `lessonHTML` — compute the expansion before the final `return`, right after the `rateBtn` helper (just before `return \`` at line 233):

```js
  const rateBtn = (quality, label) =>
    `<button class="rate-btn${suggested === quality ? " suggested" : ""}" data-quality="${quality}"${locked ? " disabled" : ""}>${label}</button>`;

  const { html: expandedPrompt, figuresBlock } = expandFigureTokens(lesson.promptHtml, lesson, lesson.courseId);

  return `
```

Change the prompt div (line 252) from:

```js
      <div class="prompt">${lesson.promptHtml}</div>
```

to:

```js
      <div class="prompt">${expandedPrompt}</div>
```

Insert `${figuresBlock}` right after the `.lesson` card's closing `</section>` (line 264) and before the checks conditional:

```js
    </section>
    ${figuresBlock}
    ${state.solutionRevealed
      ? (state.isReview && state.freshPending
          ? '<p class="checks-pending">Preparing fresh review questions…</p>'
          : checksHTML(lesson.checks || [], state))
      : ""}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `node --test frontend/tests/*.test.js`
Expected: PASS (all tests in `views.test.js` and every other frontend test file)

- [ ] **Step 5: Add the CSS**

Edit `frontend/styles.css` — insert right after the `.prompt .box{...}` rule (line 166-167) and before the `/* quiz option row */` comment (line 169):

```css
.prompt .box{background:var(--glass-inner); border:1px solid var(--border-field);
  border-radius:10px; padding:11px 13px; margin:0 0 12px; font-size:14px; line-height:1.55; color:var(--read)}

/* Lesson images — real figures resolved by backend/images.py */
.lesson-fig{margin:0 0 14px}
.lesson-fig img{display:block; width:100%; max-width:100%; border-radius:12px; margin:0 0 6px}
.lesson-fig figcaption{font-size:13px; line-height:1.45; color:var(--text-2)}
.fig-credit{display:block; font-size:11.5px; color:var(--text-faint); margin-top:2px}
.fig-credit a{color:var(--text-faint); text-decoration:underline; text-underline-offset:2px}
.lesson-figures{padding:16px 18px}
```

(the `.prompt .box{...}` rule itself is UNCHANGED — shown only for anchoring; only the new block below it is added)

- [ ] **Step 6: Run the import-resolution check**

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: `imports ok` (app.js itself is untouched by this task, but this is the repo's standing regression habit for any frontend change)

- [ ] **Step 7: Run the full frontend test suite once more**

Run: `node --test frontend/tests/*.test.js`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/lesson.js frontend/styles.css frontend/tests/views.test.js
git commit -m "$(cat <<'EOF'
feat(images): render [[figure:n]] tokens as captioned, credited figures

expandFigureTokens is a pure transform: expands tokens only against the
lesson's own backend-written images array, only for type:"web-image"
entries; unmatched/duplicate tokens are stripped; tokenless entries render
in a trailing Figures block. Chat text is never token-expanded.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```
