# Lesson Visuals — Richer, On-Brand, Animated + Interactive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each lesson the right *kind* of figure (real photo / drawn schematic / animated diagram), rendered in the app's warm frosted-glass design language, with app-owned interactivity for animated figures — all measured by new telemetry so we can prove it worked.

**Architecture:** Every change lands in the existing symmetrical six-touchpoint figure seam (authoring prompt → shape validation → server processing → server sanitizer → frontend render → client hydration). A new `svg-animated` figure type flows through that same seam. The two-layer security model (server allowlist sanitizer + client DOMPurify) is preserved and extended in lockstep; interactivity lives entirely in trusted app code (a figure player), never in model-generated markup.

**Tech Stack:** Python 3 / Flask (waitress) backend, `xml.etree.ElementTree` SVG sanitizer, SQLite events table; vanilla ES-module frontend (`node --test`, no jsdom/bundler), DOMPurify 3.4.12 + mermaid (both self-hosted, lazily loaded), SMIL animation (native, no new vendor lib).

## Global Constraints

These bind every task. Values are copied verbatim from the spec (`docs/superpowers/specs/2026-07-23-lesson-visuals-design.md`).

- **Two-layer security is never weakened.** Server sanitizer (`backend/figures.py` `sanitize_svg`) is authoritative; client DOMPurify is defense-in-depth. Both extend together for animation.
- **Never-repair sanitizer.** Any forbidden element/attribute/value drops the *whole* figure (returns `None`); no partial cleaning, ever.
- **Fail-open pipeline.** A dropped figure never blocks or fails a lesson. All new drop points keep this.
- **No behavior change from telemetry.** The telemetry additions must not change which figures render; with no sink wired, the pipeline behaves byte-identically (all existing tests pass unchanged).
- **Release-1 animation subset = `animateTransform` + `animateMotion` ONLY.** Never `animate`, `set`, `animateColor`, `mpath`, `discard`. camelCase is load-bearing.
- **`href`/`xlink:href` stay fully banned** on the model-generated (untrusted) path, server and client.
- **Static-`svg` path is untouched.** Animation is enabled only via the new `svg-animated` type and an explicit `allow_animation=True` flag; the default static path is byte-identical (zero regression).
- **No executable code in figure markup, ever.** Interactivity is the trusted app player only. `<style>` and `<script>` remain banned in figures.
- **Figure budgets:** SVG size cap `MAX_INPUT_BYTES = 8192` (8 KB) reused for `svg-animated`; ≤ 30 drawn elements and ≤ 8 animation elements; every `dur` 1–20 s. (Tier-B hand-built showcases are exempt from these budgets — they are trusted-by-review, not model output.)
- **No new figures-per-lesson.** "Richer" = correct-type + on-brand, never higher frequency. At most ONE animated figure per lesson. The regression gate on figure frequency (Task 12) enforces this.
- **web-image rendition = 1600px Commons width + ~2 MB byte cap** (`iiurlwidth="1600"`, `MAX_BYTES = 2*1024*1024`).
- **Colour convention overrides brand palette when colour IS the information** (arterial-red vs venous-blue, etc.); brand tokens set surrounding non-semantic ink/stroke.
- **Test suites that must stay green:** backend `.venv/bin/python -m pytest tests/ -q` (966 passing at plan start); frontend `cd frontend && node --test` (371 passing); frontend import check `cd frontend && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})"`.
- **The Pi is production and the only data copy.** Backfill / regeneration on live courses is a Werner-gated deploy step with backups (see the Verification & Deploy section). Never run it as part of implementation.

## Decisions that refine the spec (surfaced by recon — flag for Werner at plan review)

Writing this plan against the real code surfaced facts the spec author did not have. Three refinements; none changes the feature's intent, each is called out so Werner can veto:

1. **Telemetry sink = append-only JSONL, not the events table (overrides §5A / §9).** *Why:* the generation hook (`generation._generate_and_store_lesson`) and the backfill CLI (`images.backfill_course`) are **filesystem-only — neither has a DB connection in scope**, and `generation.py` is deliberately DB-agnostic. `events.insert_events` needs a `conn`. Threading a DB connection down the pure filesystem pipeline (or opening ad-hoc connections in a CLI) is more coupling than the linchpin warrants. Instead the pipeline emits records through an injected `on_event` callback (pure, fully unit-testable), and the default sink appends one JSON line per slot to `content/courses/figure-telemetry.jsonl` — identical for live-gen and backfill, zero new plumbing. The §5D metrics (Task 12) read this file. If SQL queryability is later wanted, a tiny ingest can load the JSONL into `events`; not needed for anything this plan measures. **This is a technical trade-off, reversible — Werner may insist on the events table and accept the plumbing.**
2. **The style contract reaches existing mermaid figures at *render* time, not via a backfill re-run (refines §5C / §9 "backfill = yes").** *Why:* `backfill_course` skips any lesson that already has an `images` key, so it cannot re-theme the 6 existing figures anyway; and re-theming is purely presentational. Prepending the mermaid `%%{init}%%` directive in `hydrateFigures` (Task 5) re-themes all existing mermaid figures instantly, no model calls, no cache rewrite, no data-loss surface. Re-*resolving* existing lessons to swap mermaid→photos (the riskier half of "backfill = yes") is deferred to a Werner-gated deploy decision (Verification & Deploy section), not built here — it overwrites cached content on the only data copy for optional polish, and the highest-value part (on-brand existing figures) is already covered for free.
3. **The control-chip uses the glass tokens that actually exist in `styles.css`.** *Why:* recon found `tokens.md` documents `--glass-soft` / `--tab-pill` / `--tab-track` but **none of them exist in `frontend/styles.css`** (which defines `--glass-inner`, `--glass-field`, `--glass-card`, `--glass-stat`, `--border-field`). Rather than introduce tokens Werner's uncommitted Golden-Hour reskin chose not to add, the chip is built from `--glass-inner` + `--glass-field` + `--border-field`, which are present. Same frosted look, no token conflict.

---

## Phase A — Figure telemetry (the linchpin, build first)

The pipeline gains one optional `on_event(record)` callback threaded through `download_verified` → `_resolve_one_slot` → `resolve_images` → `process_slots`. Default `None` means no call and byte-identical behavior. Each drop/render point emits exactly one record per web-image/svg/mermaid/svg-animated slot, keyed by `(course_id, lesson_id, n)`. Persistence is a thin JSONL adapter wired only at the two real entry points.

### Task 1: `download_verified` names its failure gate

**Files:**
- Modify: `backend/images.py:200-217` (`download_verified`)
- Test: `tests/test_images.py` (append to the `download_verified` section)

**Interfaces:**
- Produces: `download_verified(url, *, http_get, on_fail=None)` — `on_fail`, if given, is called once with a reason string (`"download-too-big"`, `"download-bad-magic"`, or `"http-error"`) immediately before any `return None`. Return contract (`(bytes, ext)` on success, `None` on failure) is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_download_verified_reports_too_big(monkeypatch):
    reasons = []
    big = b"\xff\xd8\xff" + b"x" * (images.MAX_BYTES + 1)
    out = images.download_verified("http://x/y.jpg", http_get=lambda u: big,
                                   on_fail=reasons.append)
    assert out is None
    assert reasons == ["download-too-big"]


def test_download_verified_reports_bad_magic(monkeypatch):
    reasons = []
    out = images.download_verified("http://x/y", http_get=lambda u: b"not-an-image",
                                   on_fail=reasons.append)
    assert out is None
    assert reasons == ["download-bad-magic"]


def test_download_verified_reports_http_error(monkeypatch):
    reasons = []
    def boom(u):
        raise images.HTTPError(404)
    out = images.download_verified("http://x/y", http_get=boom, on_fail=reasons.append)
    assert out is None
    assert reasons == ["http-error"]


def test_download_verified_on_fail_optional_and_silent_on_success():
    out = images.download_verified("http://x/y.png", http_get=lambda u: b"\x89PNG\r\n\x1a\n" + b"d")
    assert out == (b"\x89PNG\r\n\x1a\n" + b"d", "png")  # no on_fail passed -> no crash
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k download_verified -q`
Expected: FAIL (`on_fail` unexpected keyword / reasons empty).

- [ ] **Step 3: Implement**

Replace `download_verified` (lines 200-217) with:

```python
def download_verified(url, *, http_get, on_fail=None):
    """Fetch + verify one candidate: HTTP 200 (enforced by http_get), magic
    bytes (jpeg/png/webp ONLY — SVG and anything else rejected regardless of
    extension/Content-Type), size <=MAX_BYTES. Returns (bytes, ext) or None on
    ANY failure — never raises. `on_fail`, if given, is called once with the
    reason string ('download-too-big' | 'download-bad-magic' | 'http-error')
    before returning None (observational only — does not change the result)."""
    try:
        data = http_get(url)
    except Exception:
        if on_fail:
            on_fail("http-error")
        return None
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_BYTES:
        if on_fail:
            on_fail("download-too-big")
        return None
    if data[:3] == b"\xff\xd8\xff":
        return bytes(data), "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return bytes(data), "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return bytes(data), "webp"
    if on_fail:
        on_fail("download-bad-magic")
    return None
```

- [ ] **Step 4: Run to verify they pass, plus no regression**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS (all existing `download_verified` tests still pass — they pass no `on_fail`).

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): download_verified names its failure gate via on_fail hook"
```

---

### Task 2: `resolve_images` / `_resolve_one_slot` emit one record per web-image slot

**Files:**
- Modify: `backend/images.py:289-368` (`_resolve_one_slot`, `resolve_images`)
- Test: `tests/test_images.py` (append to the `resolve_images` section)

**Interfaces:**
- Consumes: `download_verified(..., on_fail=)` (Task 1).
- Produces:
  - `_resolve_one_slot(n, slot, course_id, lesson_id, *, images_dir, http_get, structured, on_event=None)`
  - `resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=_http_get, structured=_default_structured, deadline_seconds=120, on_event=None)`
  - `on_event(record: dict)` receives, per slot, exactly one dict: `{"course_id", "lesson_id", "n", "requested_type": "web-image", "outcome": "rendered"|"dropped", "drop_reason": <str|None>, "query": <str|None>}`. `drop_reason` values: `"malformed-slot"`, `"no-candidates"`, `"license-filtered"`, `"download-too-big"`, `"download-bad-magic"`, `"http-error"`, `"vision-rejected"`, `"deadline"`, `"error"`. `on_event=None` → never called (unchanged behavior).

- [ ] **Step 1: Write the failing tests**

```python
def _events_capture():
    evs = []
    return evs, evs.append


def test_resolve_images_records_rendered(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "human heart", "caption": "notice the four chambers"}]

    def http_get(url):
        if "commons" in url:
            return json.dumps({"query": {"pages": {"1": {"title": "File:Heart.jpg",
                "imageinfo": [{"thumburl": "http://img/heart.jpg",
                "descriptionurl": "http://src", "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}}).encode()
        return b"\xff\xd8\xff" + b"jpegbytes"

    images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                          http_get=http_get, structured=lambda *a, **k: {"pick": 1},
                          on_event=on_event)
    assert len(evs) == 1
    assert evs[0]["outcome"] == "rendered"
    assert evs[0]["requested_type"] == "web-image"
    assert evs[0]["n"] == 1 and evs[0]["query"] == "human heart"


def test_resolve_images_records_license_filtered(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "q", "caption": "c"}]

    def http_get(url):
        # one candidate, but NC license -> filtered out, none valid
        return json.dumps({"query": {"pages": {"1": {"title": "t",
            "imageinfo": [{"thumburl": "http://img/x.jpg", "descriptionurl": "http://s",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}}}]}}}}).encode()

    images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                          http_get=http_get, structured=lambda *a, **k: {"pick": 1},
                          on_event=on_event)
    assert evs[0]["outcome"] == "dropped"
    assert evs[0]["drop_reason"] == "license-filtered"


def test_resolve_images_records_vision_rejected(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "q", "caption": "c"}]

    def http_get(url):
        if "commons" in url:
            return json.dumps({"query": {"pages": {"1": {"title": "t",
                "imageinfo": [{"thumburl": "http://img/x.jpg", "descriptionurl": "http://s",
                "extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}}}}).encode()
        return b"\xff\xd8\xffjpeg"

    images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                          http_get=http_get, structured=lambda *a, **k: {"pick": None},
                          on_event=on_event)
    assert evs[0]["drop_reason"] == "vision-rejected"


def test_resolve_images_records_deadline_for_all_remaining(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "a", "caption": "c"}, {"query": "b", "caption": "c"}]
    images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                          http_get=lambda u: b"", structured=lambda *a, **k: {"pick": 1},
                          deadline_seconds=-1, on_event=on_event)
    assert [e["drop_reason"] for e in evs] == ["deadline", "deadline"]
    assert [e["n"] for e in evs] == [1, 2]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k "resolve_images_records" -q`
Expected: FAIL (`on_event` unexpected keyword).

- [ ] **Step 3: Implement**

Replace `_resolve_one_slot` (lines 289-331) with a version that emits one record. Add a private helper `_emit` at the top of the function and call it at every exit:

```python
def _resolve_one_slot(n, slot, course_id, lesson_id, *, images_dir, http_get,
                      structured, on_event=None):
    query = slot.get("query")
    caption = slot.get("caption")

    def drop(reason):
        if on_event:
            on_event({"course_id": course_id, "lesson_id": lesson_id, "n": n,
                      "requested_type": "web-image", "outcome": "dropped",
                      "drop_reason": reason,
                      "query": query if isinstance(query, str) else None})
        return None

    if not (isinstance(query, str) and query.strip() and isinstance(caption, str) and caption.strip()):
        return drop("malformed-slot")
    commons = commons_search(query, http_get=http_get)
    valid = [c for c in commons if license_allowed(c.get("licenseShort"))]
    openverse = []
    if len(valid) < 2:
        openverse = openverse_search(query, http_get=http_get)
        valid = valid + [c for c in openverse if license_allowed(c.get("licenseShort"))]
    if not valid:
        # distinguish "search found nothing" from "found but all filtered out"
        return drop("no-candidates" if not (commons or openverse) else "license-filtered")
    downloaded = []
    attempts = 0
    last_fail = ["download-bad-magic"]
    for candidate in valid:
        if attempts >= MAX_DOWNLOADS_PER_SLOT:
            break
        attempts += 1
        result = download_verified(candidate["thumbUrl"], http_get=http_get,
                                   on_fail=lambda r: last_fail.__setitem__(0, r))
        if result is None:
            continue
        data, ext = result
        downloaded.append((candidate, data, ext))
    if not downloaded:
        return drop(last_fail[0])
    pick = vision_pick(
        [(data, ext) for _, data, ext in downloaded], query, caption,
        structured=structured, workdir=tempfile.mkdtemp,
    )
    if pick is None:
        return drop("vision-rejected")
    candidate, data, ext = downloaded[pick]
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{lesson_id}-{n}.{ext}"
    fsutil.write_bytes_atomic(images_dir / filename, data)
    if on_event:
        on_event({"course_id": course_id, "lesson_id": lesson_id, "n": n,
                  "requested_type": "web-image", "outcome": "rendered",
                  "drop_reason": None, "query": query})
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
```

Replace `resolve_images` (lines 338-368) with a version that threads `on_event` and emits `deadline`/`error` records:

```python
def resolve_images(course_id, lesson_id, slots, *, content_dir, http_get=_http_get,
                   structured=_default_structured, deadline_seconds=120, on_event=None):
    """Orchestrate the whole resolver for one lesson's image slots (0-3
    {query, caption} dicts). See module docstring for the fail-open contract.
    `on_event`, if given, receives exactly one record per web-image slot (see
    _resolve_one_slot); remaining slots skipped by the deadline each emit a
    'deadline' drop record so population metrics see them."""
    if not isinstance(slots, list):
        return []
    start = time.monotonic()
    images_dir = Path(content_dir) / course_id / "images"
    resolved = []
    slice_ = slots[:MAX_SLOTS]
    for i, slot in enumerate(slice_, start=1):
        if time.monotonic() - start > deadline_seconds:
            if on_event:
                for j, rem in enumerate(slice_[i - 1:], start=i):
                    if isinstance(rem, dict):
                        on_event({"course_id": course_id, "lesson_id": lesson_id, "n": j,
                                  "requested_type": "web-image", "outcome": "dropped",
                                  "drop_reason": "deadline",
                                  "query": rem.get("query") if isinstance(rem.get("query"), str) else None})
            break
        if not isinstance(slot, dict):
            continue
        try:
            entry = _resolve_one_slot(
                i, slot, course_id, lesson_id, images_dir=images_dir,
                http_get=http_get, structured=structured, on_event=on_event,
            )
        except Exception:
            entry = None
            if on_event:
                on_event({"course_id": course_id, "lesson_id": lesson_id, "n": i,
                          "requested_type": "web-image", "outcome": "dropped",
                          "drop_reason": "error",
                          "query": slot.get("query") if isinstance(slot.get("query"), str) else None})
        if entry is not None:
            resolved.append(entry)
    return resolved
```

- [ ] **Step 4: Run to verify pass + no regression**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS (all existing `resolve_images`/`_resolve_one_slot` tests still pass — none passes `on_event`).

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): resolve_images emits one telemetry record per web-image slot"
```

---

### Task 3: `process_slots` emits records for local (svg/mermaid) slots and threads `on_event`

**Files:**
- Modify: `backend/images.py:371-413` (`process_slots`)
- Test: `tests/test_images.py` (append to the `process_slots` section)

**Interfaces:**
- Consumes: `resolve_images(..., on_event=)` (Task 2).
- Produces: `process_slots(course_id, lesson_id, slots, *, content_dir, resolve_images_fn=None, on_event=None)`. Emits, per non-web slot: svg → `{"requested_type":"svg","outcome":"rendered"|"dropped","drop_reason":None|"sanitizer-rejected"}`; mermaid → `{"requested_type":"mermaid","outcome":"rendered"}`; non-dict slot → `{"requested_type":"web-image","outcome":"dropped","drop_reason":"malformed-slot"}`. web-image records come from the resolver. Return value (sorted entries list) is **unchanged**.

- [ ] **Step 1: Write the failing tests**

```python
def test_process_slots_records_svg_rendered_and_rejected(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [
        {"type": "svg", "code": '<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>', "caption": "s"},
        {"type": "svg", "code": '<svg viewBox="0 0 800 500"><script>x</script></svg>', "caption": "bad"},
        {"type": "mermaid", "code": "pie", "caption": "m"},
    ]
    images.process_slots("demo", "demo-l1", slots, content_dir=content_dir,
                         resolve_images_fn=lambda *a, **k: [], on_event=on_event)
    by_n = {e["n"]: e for e in evs}
    assert by_n[1]["requested_type"] == "svg" and by_n[1]["outcome"] == "rendered"
    assert by_n[2]["outcome"] == "dropped" and by_n[2]["drop_reason"] == "sanitizer-rejected"
    assert by_n[3]["requested_type"] == "mermaid" and by_n[3]["outcome"] == "rendered"


def test_process_slots_threads_on_event_to_resolver(tmp_path):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "q", "caption": "c"}]

    def fake_resolver(course_id, lesson_id, slots_arg, *, content_dir, on_event=None):
        if on_event:
            on_event({"course_id": course_id, "lesson_id": lesson_id, "n": 1,
                      "requested_type": "web-image", "outcome": "rendered",
                      "drop_reason": None, "query": "q"})
        return []

    images.process_slots("demo", "demo-l1", slots, content_dir=content_dir,
                         resolve_images_fn=fake_resolver, on_event=on_event)
    assert evs and evs[0]["requested_type"] == "web-image"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k "process_slots_records or threads_on_event" -q`
Expected: FAIL (`on_event` unexpected keyword).

- [ ] **Step 3: Implement**

Replace `process_slots` (lines 371-413). Add `on_event=None` to the signature, a local `_emit` helper, emit at the svg/mermaid/non-dict branches, and pass `on_event` into the resolver call. Keep the return value identical:

```python
def process_slots(course_id, lesson_id, slots, *, content_dir, resolve_images_fn=None,
                  on_event=None):
    """Split typed image slots by type; mermaid/svg processed locally (svg
    sanitized, dropped on rejection; mermaid verbatim), only web-image slots hit
    the resolver. Returns the combined entries list sorted by n; never raises.
    `on_event`, if given, receives exactly one record per slot (see Task A) —
    local svg/mermaid records emitted here, web-image records from the resolver."""

    def emit(n, requested_type, outcome, drop_reason=None):
        if on_event:
            on_event({"course_id": course_id, "lesson_id": lesson_id, "n": n,
                      "requested_type": requested_type, "outcome": outcome,
                      "drop_reason": drop_reason, "query": None})

    if not isinstance(slots, list):
        return []
    local_entries = []
    web_image_slots = []
    for i, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            web_image_slots.append(None)
            emit(i, "web-image", "dropped", "malformed-slot")
            continue
        kind = slot.get("type", "web-image")
        if kind == "svg":
            sanitized = figures.sanitize_svg(slot.get("code", ""))
            if sanitized is not None:
                local_entries.append({"n": i, "type": "svg", "code": sanitized,
                                       "caption": slot.get("caption", "")})
                emit(i, "svg", "rendered")
            else:
                emit(i, "svg", "dropped", "sanitizer-rejected")
            web_image_slots.append(None)
        elif kind == "mermaid":
            local_entries.append({"n": i, "type": "mermaid", "code": slot.get("code", ""),
                                   "caption": slot.get("caption", "")})
            emit(i, "mermaid", "rendered")
            web_image_slots.append(None)
        else:
            web_image_slots.append(slot)
    resolver = resolve_images_fn or resolve_images
    web_resolved = []
    if any(s is not None for s in web_image_slots):
        try:
            web_resolved = resolver(course_id, lesson_id, web_image_slots,
                                    content_dir=content_dir, on_event=on_event)
        except Exception:
            web_resolved = []
    return sorted(local_entries + web_resolved, key=lambda e: e["n"])
```

Note the resolver call now passes `on_event=on_event`. The default module-level `resolve_images` (Task 2) accepts it. **The existing test `test_process_slots_mixed_types` uses a `fake_resolver` whose signature is `(course_id, lesson_id, slots_arg, *, content_dir)`** — it will now receive an unexpected `on_event` kwarg and break. Update that one fixture (and `test_process_slots_never_raises_on_resolver_exception`'s `boom`) to accept `**kwargs` — this is a test-fixture signature update, not a behavior change:

```python
    def fake_resolver(course_id, lesson_id, slots_arg, *, content_dir, **kwargs):
        ...
```

- [ ] **Step 4: Run to verify pass + no regression**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): process_slots emits telemetry for svg/mermaid slots and threads on_event"
```

---

### Task 4: JSONL sink + wire telemetry at the generation hook and backfill

**Files:**
- Create: `backend/figure_telemetry.py`
- Create: `tests/test_figure_telemetry.py`
- Modify: `backend/generation.py:1355-1362` (the `process_slots` call in `_generate_and_store_lesson`)
- Modify: `backend/images.py:503-511` (the `process_slots` call in `backfill_course`)
- Test: `tests/test_images.py` (one backfill telemetry test)

**Interfaces:**
- Produces: `figure_telemetry.record(content_dir, event) -> None` — appends one JSON line (the event dict plus an ISO-8601 `"ts"`) to `Path(content_dir) / "figure-telemetry.jsonl"`. Never raises. And `figure_telemetry.read(content_dir) -> list[dict]` — parses that file (missing file → `[]`, malformed lines skipped).
- Consumes: `process_slots(..., on_event=)` (Task 3).

- [ ] **Step 1: Write the failing test for the sink**

`tests/test_figure_telemetry.py`:

```python
from backend import figure_telemetry


def test_record_appends_jsonl_with_timestamp(tmp_path):
    ev = {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
          "requested_type": "web-image", "outcome": "rendered",
          "drop_reason": None, "query": "q"}
    figure_telemetry.record(tmp_path, ev)
    figure_telemetry.record(tmp_path, {**ev, "n": 2, "outcome": "dropped",
                                       "drop_reason": "vision-rejected"})
    rows = figure_telemetry.read(tmp_path)
    assert len(rows) == 2
    assert rows[0]["n"] == 1 and "ts" in rows[0]
    assert rows[1]["drop_reason"] == "vision-rejected"


def test_read_missing_file_is_empty(tmp_path):
    assert figure_telemetry.read(tmp_path) == []


def test_record_never_raises_on_bad_dir():
    figure_telemetry.record("/nonexistent/deeply/nested", {"n": 1})  # no exception
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_figure_telemetry.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the sink**

`backend/figure_telemetry.py`:

```python
"""Append-only JSONL sink for figure-selection telemetry. One line per figure
slot at generation/backfill time. Filesystem-only (the generation hook and the
backfill CLI have no DB connection), never raises — a telemetry failure must
never affect a lesson."""

import json
from datetime import datetime, timezone
from pathlib import Path

TELEMETRY_FILENAME = "figure-telemetry.jsonl"


def record(content_dir, event):
    """Append one figure-selection record (event dict + ISO 'ts') as a JSON line."""
    try:
        path = Path(content_dir) / TELEMETRY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({**event, "ts": datetime.now(timezone.utc).isoformat()},
                          ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read(content_dir):
    """Parse the JSONL back into a list of dicts. Missing file -> []; malformed
    lines skipped."""
    path = Path(content_dir) / TELEMETRY_FILENAME
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_figure_telemetry.py -q`
Expected: PASS.

- [ ] **Step 5: Wire the generation hook**

In `backend/generation.py`, add the import near the other `from backend import ...` lines: `from backend import figure_telemetry`. Then change the `process_slots` call (lines 1358-1360) to pass an `on_event` that writes to the JSONL:

```python
    if isinstance(slots, list) and slots:
        try:
            resolved = images.process_slots(
                course_id, lesson_id, slots, content_dir=content_dir,
                resolve_images_fn=resolve_images,
                on_event=lambda ev: figure_telemetry.record(content_dir, ev),
            )
        except Exception:
            resolved = []
```

- [ ] **Step 6: Wire the backfill call + write its failing test**

Add to `tests/test_images.py`:

```python
def test_backfill_course_writes_figure_telemetry(tmp_path):
    from backend import figure_telemetry
    content_dir = tmp_path / "courses"
    lessons_dir = content_dir / "demo" / "lessons"
    lessons_dir.mkdir(parents=True)
    (lessons_dir / "demo-l1.json").write_text(json.dumps(
        {"promptHtml": "<p>Body</p>", "title": "L1"}))

    def fake_generate(prompt, validate):
        return {"promptHtml": "<p>Body</p>[[figure:1]]",
                "images": [{"type": "mermaid", "code": "pie", "caption": "m"}]}

    images.backfill_course(content_dir, "demo", generate=fake_generate)
    rows = figure_telemetry.read(content_dir)
    assert any(r["requested_type"] == "mermaid" and r["outcome"] == "rendered" for r in rows)
```

Then in `backend/images.py` add the import `from backend import ... figure_telemetry` (extend the existing `from backend import claude_client, figures, fsutil` line to include `figure_telemetry`) and change the `process_slots` call inside `backfill_course` (line ~508):

```python
        try:
            resolved = process_slots(course_id, lesson_id, proposal["images"],
                                     content_dir=content_dir,
                                     on_event=lambda ev: figure_telemetry.record(content_dir, ev))
        except Exception:
            resolved = []
```

- [ ] **Step 7: Run the full suite + import check**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (966 prior + new tests).

- [ ] **Step 8: Commit**

```bash
git add backend/figure_telemetry.py tests/test_figure_telemetry.py backend/generation.py backend/images.py tests/test_images.py
git commit -m "feat(telemetry): JSONL figure-selection sink wired at generation + backfill"
```

---

## Phase C — On-brand style contract

Independent, pure-win, and it fixes figures already live. Mermaid is re-themed at render time (covers the 6 existing figures for free); the SVG contract is prompt guidance verified through the sanitizer; CSS gives drawn figures a glass tile.

### Task 5: Mermaid on-brand theme at render time

**Files:**
- Modify: `frontend/src/app.js:1895-1949` (add a `MERMAID_INIT` constant near `SVG_SANITIZE_CONFIG`; prepend it in the mermaid branch of `hydrateFigures`)
- Test: `frontend/tests/genfeed.test.js` is the wrong home; create `frontend/tests/figures.test.js` for a pure exported helper.

**Interfaces:**
- Produces: an exported pure helper `themedMermaid(code)` in a small module `frontend/src/figuretheme.js` (so it is unit-testable without a browser), imported by `app.js`. `themedMermaid(code)` prepends the brand `%%{init}%%` directive unless `code` already starts with `%%{init` (idempotent, future-proof).

- [ ] **Step 1: Write the failing test**

`frontend/tests/figures.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { themedMermaid, MERMAID_INIT } from "../src/figuretheme.js";

test("themedMermaid prepends the brand init directive", () => {
  const out = themedMermaid("flowchart TD\n A-->B");
  assert.ok(out.startsWith(MERMAID_INIT));
  assert.ok(out.includes("flowchart TD"));
});

test("themedMermaid is idempotent when an init directive is already present", () => {
  const already = '%%{init: {"theme":"dark"}}%%\nflowchart TD';
  assert.equal(themedMermaid(already), already);
});

test("MERMAID_INIT carries the brand purple and transparent background", () => {
  assert.ok(MERMAID_INIT.includes("#7c6aff"));
  assert.ok(MERMAID_INIT.includes("transparent"));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && node --test tests/figures.test.js`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the theme module**

`frontend/src/figuretheme.js`:

```javascript
// Brand mermaid theme, prepended at render time so it also re-themes figures
// already cached on disk (no backfill needed). Maps mermaid's base theme to the
// design tokens (content/design/tokens.md): brand purple nodes on a transparent
// ground so the glass card shows through. Safe under securityLevel:"strict"
// (themeVariables is not in mermaid's secure lock-list).
export const MERMAID_INIT =
  '%%{init: {"theme":"base","themeVariables":{' +
  '"primaryColor":"#ece7ff","primaryBorderColor":"#7c6aff","primaryTextColor":"#241f1a",' +
  '"lineColor":"#7c6aff","secondaryColor":"#e8f2fb","tertiaryColor":"#fbf7ee",' +
  '"fontFamily":"system-ui, -apple-system, Segoe UI, Roboto, sans-serif",' +
  '"background":"transparent"}}}%%\n';

export function themedMermaid(code) {
  const src = typeof code === "string" ? code : "";
  if (src.trimStart().startsWith("%%{init")) return src; // already themed
  return MERMAID_INIT + src;
}
```

- [ ] **Step 4: Wire it into `hydrateFigures`**

In `frontend/src/app.js`, add to the import block at the top: `import { themedMermaid } from "./figuretheme.js";`. In the mermaid branch of `hydrateFigures` (line 1942), change the render call to theme the code first:

```javascript
      loadMermaidLib()
        .then((mermaid) => mermaid.render(renderId, themedMermaid(entry.code)))
```

- [ ] **Step 5: Run tests + import check**

Run: `cd frontend && node --test tests/figures.test.js && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})"`
Expected: PASS + `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/figuretheme.js frontend/src/app.js frontend/tests/figures.test.js
git commit -m "feat(figures): on-brand mermaid theme applied at render time"
```

---

### Task 6: SVG style guide in the authoring prompt

**Files:**
- Modify: `backend/figures.py:36-53` (`DRAWN_FIGURE_GUIDANCE` — the SVG-authoring-rules sentence)
- Test: `tests/test_figures.py` (a must-survive style-guide exemplar)

**Interfaces:** none (prompt text). The test proves a figure authored to the new rules survives `sanitize_svg`.

- [ ] **Step 1: Write the failing test**

The new guidance tells the model to draw arrowheads as `<polygon>` triangles and use flat `fill`/`fill-opacity`. Add a test that a figure using exactly those constructs sanitizes clean (it will pass today too — that is fine; it locks the contract as sanitizer-legal so a future allowlist change can't silently break the documented style):

```python
def test_sanitize_svg_accepts_style_guide_exemplar():
    src = (
        '<svg viewBox="0 0 800 500">'
        '<rect x="40" y="40" width="200" height="120" fill="#7c6aff" fill-opacity="0.14" '
        'stroke="#7c6aff" stroke-width="2"/>'
        '<polygon points="300,90 340,100 300,110" fill="#241f1a"/>'
        '<line x1="240" y1="100" x2="300" y2="100" stroke="#241f1a" stroke-width="2"/>'
        '<text x="60" y="105" font-size="16" fill="#241f1a">Left atrium</text>'
        '</svg>'
    )
    assert figures.sanitize_svg(src) is not None
```

- [ ] **Step 2: Run to verify it passes already**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k style_guide_exemplar -q`
Expected: PASS (this test guards the contract; it passes before and after the prompt edit).

- [ ] **Step 3: Rewrite the SVG-authoring-rules portion of `DRAWN_FIGURE_GUIDANCE`**

Replace the SVG-rules sentence (lines 47-50, from `'sentence saying what to NOTICE>"}. SVG authoring rules:'` through `'on a light card.\n"'`) with:

```python
    '  An svg slot: {"type": "svg", "code": "<svg ...>...</svg>", "caption": "<one '
    'sentence saying what to NOTICE>"}. SVG style contract (stay inside the sanitizer '
    'allowlist): fixed viewBox="0 0 800 500"; NO gradients, NO filter/blur/shadow, NO '
    '<style> (all banned) — use flat fill plus fill-opacity tints for depth; draw '
    'arrowheads as <polygon> triangles (marker sizing attrs are not allowed); label '
    'every part with a <text> element (font-size at least 14px) ON the drawing, never a '
    'separate legend. Use the brand palette — ink #241f1a for labels/strokes, purple '
    '#7c6aff and its soft tint for structure — EXCEPT where a colour itself carries the '
    'meaning (arterial-red vs venous-blue, hot vs cold, acid vs base): there use the '
    'established domain convention, not the brand colour.\n"'
```

- [ ] **Step 4: Run the figures suite**

Run: `.venv/bin/python -m pytest tests/test_figures.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/figures.py tests/test_figures.py
git commit -m "feat(figures): on-brand SVG style contract in the authoring prompt"
```

---

### Task 7: Glass tile + de-stretch CSS for drawn figures

**Files:**
- Modify: `frontend/styles.css:262-269` (the `.lesson-fig*` block — **note this file has uncommitted Golden-Hour changes; edit the on-disk file, append within the existing block**)
- No unit test (CSS); verified in the Pi live-verification step.

**Interfaces:** none. Adds container-level rules for `.lesson-fig-svg` / `.lesson-fig-mermaid` (there are none today — only a child-`svg` selector) so drawn figures sit on a `--glass-inner` tile and small mermaid diagrams are no longer force-stretched to 100%.

- [ ] **Step 1: Add the rules**

After line 269 (`.lesson-fig-svg svg,.lesson-fig-mermaid svg{...}`) in `frontend/styles.css`, add:

```css
/* Drawn figures sit on a soft inner-glass tile (the app's blur/shadow depth is
   impossible inside sanitized SVG, so the tile supplies the surrounding depth). */
.lesson-fig-svg,.lesson-fig-mermaid{
  background:var(--glass-inner); border:1px solid var(--border-field);
  border-radius:14px; padding:14px 16px;
}
/* Stop force-stretching a small diagram edge-to-edge: cap width, centre it. */
.lesson-fig-mermaid svg{width:auto; max-width:100%; margin-inline:auto}
```

Note: line 269 already sets `.lesson-fig-svg svg,.lesson-fig-mermaid svg{...width:100%...}`. The new `.lesson-fig-mermaid svg` rule is more specific-per-property and appears later, so `width:auto` wins for mermaid; the compound rule still governs `.lesson-fig-svg svg` (schematics that genuinely want full width). This is intentional — verify visually on the Pi.

- [ ] **Step 2: Verify the stylesheet still parses**

Run: `cd frontend && node -e "const c=require('fs').readFileSync('styles.css','utf8'); const o=(c.match(/{/g)||[]).length, x=(c.match(/}/g)||[]).length; if(o!==x){console.error('brace mismatch',o,x);process.exit(1)} console.log('css braces balanced', o)"`
Expected: `css braces balanced <n>`.

- [ ] **Step 3: Commit**

```bash
git add frontend/styles.css
git commit -m "feat(figures): glass tile and de-stretch CSS for drawn figures"
```

Note for the implementer: `git add frontend/styles.css` will stage Werner's uncommitted Golden-Hour reskin *together with* this change. **Do not** `git add` the file if the reskin should stay separate — instead surface this to the controller, who flags it for Werner. (See Phase-review note: styles.css touched by both Task 7 and Task 20.)

---

## Phase B — Drop-point fixes (revive web-image + svg)

Guided by what the telemetry (Phase A) shows actually fires. Two isolated gate fixes.

### Task 8: 1600px rendition + ~2 MB byte cap

**Files:**
- Modify: `backend/images.py:24` (`MAX_BYTES`) and `backend/images.py:84` (`iiurlwidth`)
- Test: `tests/test_images.py` (append)

**Interfaces:** `MAX_BYTES = 2 * 1024 * 1024`; `commons_search` requests `iiurlwidth="1600"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_download_verified_accepts_1_5mb_png():
    data = b"\x89PNG\r\n\x1a\n" + b"x" * (1_500_000)
    assert len(data) > 400 * 1024  # would have failed under the old 400KB cap
    out = images.download_verified("http://x/y.png", http_get=lambda u: data)
    assert out is not None and out[1] == "png"


def test_download_verified_still_rejects_over_2mb():
    data = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1)
    assert images.download_verified("http://x/y.png", http_get=lambda u: data) is None


def test_commons_search_requests_1600px_rendition():
    seen = {}
    def http_get(url):
        seen["url"] = url
        return b"{}"
    images.commons_search("heart", http_get=http_get)
    assert "iiurlwidth=1600" in seen["url"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k "1_5mb or over_2mb or 1600px" -q`
Expected: FAIL (cap 400 KB rejects the 1.5 MB png; url has `iiurlwidth=800`).

- [ ] **Step 3: Implement**

`backend/images.py` line 24:
```python
MAX_BYTES = 2 * 1024 * 1024
```
`backend/images.py` line 84:
```python
        ("iiurlwidth", "1600"),
```

- [ ] **Step 4: Run + no regression**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS. (Check: any existing test asserting the old 400 KB boundary or `iiurlwidth=800` must be updated to the new values — search `tests/test_images.py` for `400` and `800` and adjust the two boundary assertions if present.)

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): 1600px Commons rendition and 2MB byte cap for crisp photos"
```

---

### Task 9: Broaden the license matcher to real CC spellings

**Files:**
- Modify: `backend/images.py:159-172` (`license_allowed`)
- Test: `tests/test_images.py` (append to the `license_allowed` section)

**Interfaces:** `license_allowed(value) -> bool` — now accepts hyphenated/suffixed permissive CC forms (`CC-BY-SA-4.0`, `CC BY-SA 3.0 Migrated`) while still rejecting NC/ND. Same signature.

- [ ] **Step 1: Write the failing tests**

```python
def test_license_allowed_accepts_hyphenated_and_migrated_forms():
    assert images.license_allowed("CC-BY-SA-4.0") is True
    assert images.license_allowed("CC BY-SA 3.0 Migrated") is True
    assert images.license_allowed("CC BY 2.0") is True
    assert images.license_allowed("CC-BY-4.0") is True


def test_license_allowed_still_rejects_nc_nd_and_junk():
    assert images.license_allowed("CC BY-NC 4.0") is False
    assert images.license_allowed("CC-BY-ND-4.0") is False
    assert images.license_allowed("CC BY-NC-SA 4.0") is False
    assert images.license_allowed("GFDL") is False
    assert images.license_allowed("") is False


def test_license_allowed_keeps_public_domain_cc0_and_openverse_slugs():
    assert images.license_allowed("Public Domain") is True
    assert images.license_allowed("CC0") is True
    assert images.license_allowed("pdm") is True
    assert images.license_allowed("by-sa") is True  # openverse slug
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k license_allowed -q`
Expected: FAIL on the hyphenated forms (old matcher needs a trailing space).

- [ ] **Step 3: Implement**

Replace `license_allowed` (lines 159-172) with:

```python
def license_allowed(value):
    """Fail-closed allowlist across BOTH sources' license vocabularies. Accepts
    public-domain / CC0 / PDM, Openverse slugs {cc0, pdm, by, by-sa}, and any
    CC-BY or CC-BY-SA spelling regardless of separators or version/'Migrated'
    suffix (Commons ships 'CC-BY-SA-4.0', 'CC BY-SA 3.0 Migrated', etc.). Any
    NC or ND term is rejected."""
    if not isinstance(value, str) or not value.strip():
        return False
    lowered = value.strip().lower()
    if lowered in ("public domain", "cc0", "pdm"):
        return True
    if lowered in _OPENVERSE_ALLOWED:
        return True
    # Normalise separators so 'cc-by-sa-4.0' and 'cc by-sa 4.0' compare alike.
    parts = re.sub(r"[-\s]+", " ", lowered).split()
    if "nc" in parts or "nd" in parts:
        return False
    if parts[:3] == ["cc", "by", "sa"]:
        return True
    if parts[:2] == ["cc", "by"]:
        return True
    return False
```

(`re` is already imported at `backend/images.py:11`.)

- [ ] **Step 4: Run + no regression**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): accept hyphenated CC-BY/BY-SA license spellings, still reject NC/ND"
```

---

### Task 10: Allow `stroke-linecap` / `stroke-linejoin` in the SVG sanitizer

**Files:**
- Modify: `backend/figures.py:23-29` (`ALLOWED_ATTRS`)
- Modify: `frontend/src/app.js:1906` (`SVG_SANITIZE_CONFIG.ALLOWED_ATTR` — keep server and client advisory lists in sync)
- Test: `tests/test_figures.py` (append)

**Interfaces:** the two attributes join `ALLOWED_ATTRS` (server) and the client advisory `ALLOWED_ATTR`. The app's own icons already use them, so a 95%-clean model SVG is no longer discarded whole.

- [ ] **Step 1: Write the failing test**

```python
def test_sanitize_svg_accepts_stroke_linecap_and_linejoin():
    src = ('<svg viewBox="0 0 800 500"><path d="M10 10 L90 90" stroke="#333" '
           'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>')
    out = figures.sanitize_svg(src)
    assert out is not None
    assert "stroke-linecap" in out and "stroke-linejoin" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k stroke_linecap -q`
Expected: FAIL (`None` — attributes not allowlisted).

- [ ] **Step 3: Implement**

In `backend/figures.py`, add to `ALLOWED_ATTRS` (line 26, in the `stroke-dasharray` area):
```python
    "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
```
In `frontend/src/app.js` line 1906, add `"stroke-linecap","stroke-linejoin"` to the `ALLOWED_ATTR` array (after `"stroke-dasharray"`).

- [ ] **Step 4: Run tests + frontend import check**

Run: `.venv/bin/python -m pytest tests/test_figures.py -q && cd frontend && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})"`
Expected: PASS + `imports ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/figures.py frontend/src/app.js tests/test_figures.py
git commit -m "feat(figures): allow stroke-linecap/stroke-linejoin so near-clean SVGs survive"
```

---

## Phase D — Type-selection tuning (quality, not quantity)

Consolidate the duplicated validator, rewrite the router to stop framing photos as a fallback, and add the metrics helper that computes the §5D distribution-health signals and the regression gate.

### Task 11: Consolidate the duplicated image-slot validator

**Files:**
- Modify: `backend/generation.py:208-241` (`valid_images`) and `backend/images.py:442-466` (`_valid_images_slots`)
- Test: `tests/test_generation.py`, `tests/test_images.py` (existing tests must stay green; add one shared-helper test)

**Interfaces:**
- Produces: a single shared `figures.valid_image_slot(slot) -> bool` in `backend/figures.py` (already the home of the shared `DRAWN_FIGURE_GUIDANCE`, and imported by both `generation.py` and `images.py`, so no new import cycle). Both `valid_images` and `_valid_images_slots` call it per-slot; each keeps its own list-level rule (`valid_images` allows absent/`None`; `_valid_images_slots` requires a list).

- [ ] **Step 1: Write the failing test**

```python
def test_valid_image_slot_shared_helper():
    from backend import figures
    assert figures.valid_image_slot({"query": "q", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "svg", "code": "<svg/>", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "mermaid", "code": "pie", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "svg", "code": "", "caption": "c"}) is False
    assert figures.valid_image_slot({"type": "web-image", "query": "", "caption": "c"}) is False
    assert figures.valid_image_slot({"type": "bogus", "code": "x", "caption": "c"}) is False
    assert figures.valid_image_slot("not a dict") is False
```

(Put this in `tests/test_figures.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k valid_image_slot -q`
Expected: FAIL (no such function).

- [ ] **Step 3: Implement the shared helper in `backend/figures.py`**

Add after `DRAWN_FIGURE_GUIDANCE` (after line 53):

```python
def valid_image_slot(slot):
    """Per-slot shape check shared by generation.valid_images and
    images._valid_images_slots (single source of truth). web-image (or no type):
    non-empty query + caption. mermaid/svg: non-empty code (<=8192 chars) +
    caption. Any other type is invalid."""
    if not isinstance(slot, dict):
        return False
    kind = slot.get("type", "web-image")
    if kind == "web-image":
        return all(isinstance(slot.get(f), str) and slot[f].strip() for f in ("query", "caption"))
    if kind in ("mermaid", "svg"):
        code = slot.get("code")
        if not (isinstance(code, str) and code.strip() and len(code) <= 8192):
            return False
        return isinstance(slot.get("caption"), str) and bool(slot["caption"].strip())
    return False
```

- [ ] **Step 4: Route both validators through it**

`backend/generation.py` `valid_images` (lines 224-240) — replace the per-slot loop body:
```python
    for slot in images_val:
        if not figures.valid_image_slot(slot):
            return False
    return True
```
(`figures` is already imported in `generation.py`.)

`backend/images.py` `_valid_images_slots` (lines 450-466) — replace the per-slot loop body:
```python
    for slot in images_val:
        if not figures.valid_image_slot(slot):
            return False
    return True
```
(`figures` is already imported in `images.py`.)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (the existing `valid_images` and `_valid_images_slots` tests exercise the same behavior through the new helper).

- [ ] **Step 6: Commit**

```bash
git add backend/figures.py backend/generation.py backend/images.py tests/test_figures.py
git commit -m "refactor(figures): single source of truth for image-slot shape validation"
```

---

### Task 12: Type-neutral router — photos first-class, no fallback framing

**Files:**
- Modify: `backend/figures.py:36-53` (`DRAWN_FIGURE_GUIDANCE` — the router sentence) and `backend/generation.py:308-322` (`_IMAGES_BLOCK` — the "prefer a real photo … a schematic … a chart" sentence)
- Test: none (prompt text). A grep-style assertion locks that the loser-framing is gone.

**Interfaces:** none. Deletes "when a diagram would be too complex to draw clearly in code, prefer a web-image slot instead" (photos-as-loser framing) and reframes the type router type-neutrally.

- [ ] **Step 1: Write the failing guard test**

`tests/test_figures.py`:
```python
def test_drawn_guidance_has_no_photo_as_fallback_framing():
    text = figures.DRAWN_FIGURE_GUIDANCE.lower()
    assert "too complex to draw" not in text  # the old loser-framing is gone
    assert "recognize a real thing" in text or "recognise a real thing" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k no_photo_as_fallback -q`
Expected: FAIL.

- [ ] **Step 3: Rewrite the router sentence in `DRAWN_FIGURE_GUIDANCE`**

Replace lines 37-43 (from `"\n\nA figure slot may also be a diagram…"` through `"…prefer a web-image slot instead.\n"`) with:

```python
    "\n\nChoose the figure TYPE by what the content needs (this is independent of "
    "how hard the content is):\n"
    "  - web-image (a real photo/plate) whenever the learner must recognize a real "
    "thing by appearance — anatomy, organisms, minerals, artefacts. A drawing cannot "
    "substitute; this is first-class, never a fallback.\n"
    "  - a static drawn diagram (mermaid for a process/flow/hierarchy/timeline or "
    "quantitative chart; svg for a labelled spatial schematic mermaid cannot express) "
    "when structure or relationships are the point and a still with arrows and labels "
    "reads at a glance.\n"
    "  - svg-animated ONLY when the meaning IS change over time (a flow, a cycle, a "
    "process in motion) and a static frame would genuinely lose the point.\n"
```

- [ ] **Step 4: Reframe the `_IMAGES_BLOCK` sentence**

In `backend/generation.py`, replace the sentence at lines 313-315 (`"Prefer a real photo or plate for concrete identification (anatomy, organisms, objects), a schematic for a process or abstract relation, and a chart for quantitative data. "`) with:

```python
    "Pick the figure type by what the content needs (see the type guide below); a real "
    "photo is first-class whenever the learner must recognize a real thing by appearance. "
```

- [ ] **Step 5: Run**

Run: `.venv/bin/python -m pytest tests/test_figures.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/figures.py backend/generation.py tests/test_figures.py
git commit -m "feat(prompt): type-neutral figure router, photos first-class not fallback"
```

---

### Task 13: Figure distribution-health metrics + regression gate

**Files:**
- Create: `backend/figure_metrics.py`
- Create: `tests/test_figure_metrics.py`

**Interfaces:**
- Produces: `figure_metrics.compute(content_dir, course_id) -> dict` with keys:
  - `id_alignment_rate` — of identification-stratum figure-bearing lessons (any objective with `knowledge == "factual"` AND `bloom in ("remember","understand")`), fraction requesting ≥1 `web-image`.
  - `mermaid_share` — fraction of all requested drawn slots that are mermaid (the >0.85 non-degeneracy alarm).
  - `web_image_realization_rate` — of requested `web-image` slots, fraction with `outcome == "rendered"`.
  - `figures_per_lesson` — mean requested slots per figure-bearing lesson.
  - `zero_figure_rate` — fraction of lessons with zero requested slots.
  - `regression_ok(baseline)` — a helper `figure_metrics.regression_ok(current, baseline)` returning `bool`: alignment not lower AND `figures_per_lesson` within ±10% of baseline AND `zero_figure_rate` not falling.

Reads figure telemetry (`figure_telemetry.read`) joined with objective strata (`courses.load_manifest` + `objectives.for_lesson`).

- [ ] **Step 1: Write the failing test**

`tests/test_figure_metrics.py`:
```python
import json
from backend import figure_metrics, figure_telemetry


def _seed(content_dir, course_id, lessons, events):
    cdir = content_dir / course_id
    (cdir / "lessons").mkdir(parents=True)
    manifest = {"schemaVersion": 3, "objectives": [], "modules": [{"title": "M",
                "lessons": []}]}
    for lid, objs in lessons.items():
        for i, o in enumerate(objs):
            o["id"] = f"{lid}-o{i}"
        manifest["objectives"].extend(objs)
        manifest["modules"][0]["lessons"].append(
            {"id": lid, "title": lid, "objectiveIds": [o["id"] for o in objs]})
    (cdir / "course.json").write_text(json.dumps(manifest))
    for ev in events:
        figure_telemetry.record(content_dir, ev)


def test_id_alignment_and_realization(tmp_path):
    content_dir = tmp_path / "courses"
    _seed(content_dir, "demo",
          lessons={"demo-l1": [{"text": "identify the bone", "bloom": "remember",
                                "knowledge": "factual"}],
                   "demo-l2": [{"text": "explain flow", "bloom": "analyze",
                                "knowledge": "conceptual"}]},
          events=[
            {"course_id": "demo", "lesson_id": "demo-l1", "n": 1,
             "requested_type": "web-image", "outcome": "rendered", "drop_reason": None},
            {"course_id": "demo", "lesson_id": "demo-l2", "n": 1,
             "requested_type": "mermaid", "outcome": "rendered", "drop_reason": None},
          ])
    m = figure_metrics.compute(content_dir, "demo")
    assert m["id_alignment_rate"] == 1.0            # the one ID lesson asked for a photo
    assert m["web_image_realization_rate"] == 1.0   # its photo resolved
    assert m["mermaid_share"] == 0.5                 # 1 of 2 drawn/photo slots is mermaid


def test_regression_ok_gate(tmp_path):
    base = {"id_alignment_rate": 0.6, "figures_per_lesson": 1.0, "zero_figure_rate": 0.3}
    good = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.05, "zero_figure_rate": 0.3}
    bad_freq = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.3, "zero_figure_rate": 0.3}
    bad_zero = {"id_alignment_rate": 0.7, "figures_per_lesson": 1.0, "zero_figure_rate": 0.1}
    assert figure_metrics.regression_ok(good, base) is True
    assert figure_metrics.regression_ok(bad_freq, base) is False
    assert figure_metrics.regression_ok(bad_zero, base) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_figure_metrics.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `backend/figure_metrics.py`**

```python
"""Population-level figure distribution-health metrics (spec §5D). Reads the
figure-telemetry JSONL, joins each lesson to its objective stratum via the
objective registry, and reports the signals the regression gate checks. Never a
per-lesson ground-truth label — only aggregate health."""

from collections import defaultdict

from backend import courses, figure_telemetry, objectives


def _lesson_strata(content_dir, course_id):
    """{lesson_id: True if any objective is identification-stratum} — factual
    knowledge at a low Bloom level (remember/understand)."""
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return {}
    strata = {}
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            objs = objectives.for_lesson(manifest, lesson)
            strata[lesson["id"]] = any(
                o.get("knowledge") == "factual" and o.get("bloom") in ("remember", "understand")
                for o in objs if isinstance(o, dict))
    return strata


def compute(content_dir, course_id):
    rows = [r for r in figure_telemetry.read(content_dir) if r.get("course_id") == course_id]
    strata = _lesson_strata(content_dir, course_id)
    by_lesson = defaultdict(list)
    for r in rows:
        by_lesson[r.get("lesson_id")].append(r)

    drawn = [r for r in rows if r.get("requested_type") in ("mermaid", "svg", "svg-animated")]
    photos = [r for r in rows if r.get("requested_type") == "web-image"]
    drawn_and_photo = len(drawn) + len(photos)

    id_lessons = [lid for lid, fig in by_lesson.items() if strata.get(lid)]
    id_with_photo = sum(
        1 for lid in id_lessons
        if any(r.get("requested_type") == "web-image" for r in by_lesson[lid]))

    total_lessons = len(strata) or 1
    fig_lessons = [lid for lid, fig in by_lesson.items() if fig]

    def rate(num, den):
        return round(num / den, 4) if den else 0.0

    return {
        "id_alignment_rate": rate(id_with_photo, len(id_lessons)),
        "mermaid_share": rate(sum(1 for r in drawn if r["requested_type"] == "mermaid"),
                              drawn_and_photo),
        "web_image_realization_rate": rate(
            sum(1 for r in photos if r.get("outcome") == "rendered"), len(photos)),
        "figures_per_lesson": rate(len(rows), len(fig_lessons)) if fig_lessons else 0.0,
        "zero_figure_rate": rate(total_lessons - len(fig_lessons), total_lessons),
    }


def regression_ok(current, baseline):
    """Gate: alignment not lower AND figures/lesson within +/-10% of baseline AND
    zero-figure rate not falling (spec §5D)."""
    if current["id_alignment_rate"] < baseline["id_alignment_rate"]:
        return False
    base_fpl = baseline["figures_per_lesson"] or 1e-9
    if abs(current["figures_per_lesson"] - baseline["figures_per_lesson"]) / base_fpl > 0.10:
        return False
    if current["zero_figure_rate"] < baseline["zero_figure_rate"]:
        return False
    return True
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/test_figure_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/figure_metrics.py tests/test_figure_metrics.py
git commit -m "feat(metrics): figure distribution-health metrics and regression gate"
```

---

## Phase E — Animated SVG figures (new `svg-animated` capability)

The security core. The sanitizer gains an opt-in `allow_animation` flag that unlocks exactly `animateTransform` + `animateMotion` with strict per-attribute value restrictions; the static path stays byte-identical. Then the new type flows through validation, processing, render, and client hydration.

### Task 14: `sanitize_svg(allow_animation=True)` — the SMIL subset with value restrictions

**Files:**
- Modify: `backend/figures.py` (constants block 13-29, `_check_element` 66-97, `sanitize_svg` 112-146; add helpers)
- Test: `tests/test_figures.py` (a malicious corpus + a must-pass corpus)

**Interfaces:**
- Produces: `sanitize_svg(code, *, allow_animation=False)`. Default `False` = current behavior exactly (animation elements rejected). `True` = additionally permit `animateTransform`/`animateMotion` with these hard value rules (any violation drops the whole figure):
  - `attributeName` must be exactly `"transform"` and only on `animateTransform`; **rejected on `animateMotion`**.
  - `type` enum `translate|scale|rotate|skewX|skewY` (no `matrix`), only on `animateTransform`.
  - `dur` a clock-value in **1–20 s**; `begin` any clock-value (may be negative/zero for pre-seeding); event syntax (`rect.click`, `anim.end`, `accessKey(x)`) rejected.
  - `values`/`keyPoints` numeric-list only; `path` path-grammar only; `repeatCount` `indefinite` or a positive number; `additive`/`accumulate`/`rotate` from a small enum.
  - Budget: ≤ 30 drawn elements and ≤ 8 animation elements.
- `href`/`xlink:href`/`on*`/`style` stay banned on animation elements too.

- [ ] **Step 1: Write the failing malicious-corpus + must-pass tests**

```python
# --- svg-animated: must be dropped (return None) under allow_animation=True ---
_MAL = '<svg viewBox="0 0 800 500">{}</svg>'

def _drop(inner):
    return figures.sanitize_svg(_MAL.format(inner), allow_animation=True) is None

def test_anim_rejects_set_and_animate_and_mpath():
    assert _drop('<set attributeName="href" to="javascript:alert(1)"/>')
    assert _drop('<animate attributeName="href" values="a;b" dur="2s"/>')
    assert _drop('<animateMotion><mpath xlink:href="#p"/></animateMotion>')

def test_anim_rejects_bad_attributename_and_type_and_events():
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="x" '
                 'type="translate" values="0 0;9 0" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="matrix" values="1 0 0 1 0 0" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="translate" values="0 0;9 0" begin="rect.click" dur="2s"/></rect>')
    assert _drop('<circle r="3"><animateMotion attributeName="transform" path="M0,0 L9,0" dur="2s"/></circle>')

def test_anim_rejects_nonnumeric_values_and_bad_dur():
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="translate" values="url(#x)" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="scale" values="1;2" dur="99s"/></rect>')  # dur > 20s

def test_anim_rejects_over_budget():
    dots = "".join('<circle r="1"><animateMotion path="M0,0 L9,0" dur="2s"/></circle>'
                   for _ in range(9))  # 9 animation elements > 8
    assert _drop(dots)

def test_anim_elements_still_rejected_without_flag():
    # default allow_animation=False -> animation is not permitted (static path unchanged)
    assert figures.sanitize_svg(_MAL.format(
        '<rect width="9" height="9"><animateTransform attributeName="transform" '
        'type="translate" values="0 0;9 0" dur="2s"/></rect>')) is None

# --- svg-animated: must survive and keep their animation elements ---
def test_anim_accepts_spin_slide_pulse_motion():
    spin = ('<rect x="10" y="10" width="80" height="40" fill="#7c6aff">'
            '<animateTransform attributeName="transform" type="rotate" '
            'values="0 50 30;360 50 30" dur="4s" repeatCount="indefinite"/></rect>')
    slide = ('<rect x="0" y="0" width="20" height="20" fill="#4fa3e8">'
             '<animateTransform attributeName="transform" type="translate" '
             'values="0 0;100 0" dur="2s" repeatCount="indefinite"/></rect>')
    motion = ('<circle r="4" fill="#d6557e"><animateMotion path="M0,0 L200,0" '
              'dur="3s" begin="-0.5s" repeatCount="indefinite"/></circle>')
    for inner in (spin, slide, motion):
        out = figures.sanitize_svg(_MAL.format(inner), allow_animation=True)
        assert out is not None
        assert "animate" in out.lower()

def test_anim_strip_leaves_valid_still_frame():
    # remove every animate* element -> the remainder must still sanitize (static fallback)
    import re as _re
    src = _MAL.format('<circle cx="40" cy="40" r="4" fill="#d6557e">'
                      '<animateMotion path="M0,0 L200,0" dur="3s"/></circle>'
                      '<text x="10" y="20" font-size="14">Blood cell</text>')
    assert figures.sanitize_svg(src, allow_animation=True) is not None
    still = _re.sub(r'<animate[A-Za-z]*\b[^>]*/>', '', src)
    out = figures.sanitize_svg(still)  # allow_animation defaults False
    assert out is not None and "Blood cell" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k anim -q`
Expected: FAIL (`allow_animation` unexpected / must-pass return None).

- [ ] **Step 3: Add the animation constants and value validators**

In `backend/figures.py`, after the `ALLOWED_ATTRS` block (line 29) add:

```python
ANIM_ELEMENTS = {"animateTransform", "animateMotion"}
ANIM_ATTRS = {
    "attributeName", "type", "dur", "begin", "repeatCount", "values",
    "additive", "accumulate", "path", "keyPoints", "rotate",
}
_TRANSFORM_TYPES = {"translate", "scale", "rotate", "skewX", "skewY"}
_MAX_DRAWN_ELEMENTS = 30
_MAX_ANIM_ELEMENTS = 8
_CLOCK_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(s|ms)?$")
_NUMLIST_RE = re.compile(r"^[\s\d.,;+\-eE]+$")
_PATH_RE = re.compile(r"^[\sMmLlHhVvCcSsQqTtAaZz0-9.,\-eE]+$")
_POSNUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _clock_seconds(value):
    """Parse an SMIL clock-value ('2s', '500ms', '1.5', '-0.5s') to float seconds,
    or None if it is not a bare clock-value (rejects all event syntax)."""
    m = _CLOCK_RE.match(value.strip())
    if not m:
        return None
    num = float(m.group(1))
    return num / 1000.0 if m.group(2) == "ms" else num


def _valid_anim_attr(el_local, name, value):
    """Value-restrict one animation attribute. Returns False -> whole figure dropped."""
    if name == "attributeName":
        return el_local == "animateTransform" and value == "transform"
    if name == "type":
        return el_local == "animateTransform" and value in _TRANSFORM_TYPES
    if name == "dur":
        secs = _clock_seconds(value)
        return secs is not None and 1.0 <= secs <= 20.0
    if name == "begin":
        return _clock_seconds(value) is not None
    if name == "repeatCount":
        return value == "indefinite" or bool(_POSNUM_RE.match(value.strip()))
    if name in ("values", "keyPoints"):
        return value.strip() != "" and bool(_NUMLIST_RE.match(value))
    if name == "path":
        return value.strip() != "" and bool(_PATH_RE.match(value))
    if name in ("additive", "accumulate"):
        return value in ("replace", "sum", "none")
    if name == "rotate":
        return value in ("auto", "auto-reverse") or _clock_seconds(value) is not None
    return False
```

- [ ] **Step 4: Extend `_check_element` for animation elements**

Replace `_check_element` (lines 66-97) with an `allow_animation`-aware version:

```python
def _check_element(el, is_root=False, allow_animation=False):
    """Recursively validate one element and its subtree. Returns True if the
    whole subtree is clean, False on the first violation (short-circuits)."""
    local, uri = _local_name(el.tag)
    if uri is not None and uri != _SVG_NS:
        return False
    if local in ANIM_ELEMENTS:
        if not allow_animation:
            return False
        for attr_name in el.attrib:
            attr_local, attr_uri = _local_name(attr_name)
            if attr_uri == _XLINK_NS:
                return False
            if attr_local.lower().startswith("on") or attr_local in ("href", "style"):
                return False
            if attr_local not in ANIM_ATTRS:
                return False
            if not _valid_anim_attr(local, attr_local, el.attrib[attr_name]):
                return False
        for _child in el:
            return False  # animation elements carry no children in this subset
        return True
    if local == "svg" and not is_root:
        return False  # nested svg elements not allowed
    if local not in ALLOWED_ELEMENTS:
        return False
    for attr_name in el.attrib:
        attr_local, attr_uri = _local_name(attr_name)
        if attr_uri == _XLINK_NS:
            return False
        if attr_local.lower().startswith("on"):
            return False
        if attr_local in ("href", "style"):
            return False
        if attr_local not in ALLOWED_ATTRS:
            return False
        if attr_local in ("fill", "stroke", "marker-start", "marker-end"):
            attr_value = el.attrib[attr_name]
            if "url(" in attr_value.lower():
                if not re.match(r'^\s*url\s*\(\s*#[\w-]+\s*\)\s*$', attr_value, re.IGNORECASE):
                    return False
    for child in el:
        if not _check_element(child, allow_animation=allow_animation):
            return False
    return True
```

- [ ] **Step 5: Thread the flag + budgets through `sanitize_svg`**

Replace `sanitize_svg` (lines 112-146). Add the `allow_animation` kwarg, pass it to `_check_element`, and enforce the element budgets when animation is allowed:

```python
def sanitize_svg(code, *, allow_animation=False):
    """Strict allowlist SVG sanitizer. Returns canonical sanitized SVG markup, or
    None on any violation (never repairs). allow_animation=False (default) is the
    static path, unchanged. allow_animation=True additionally permits the
    animateTransform/animateMotion subset with value restrictions and enforces
    the <=30 drawn / <=8 animation element budgets."""
    if not isinstance(code, str) or not code.strip():
        return None
    if len(code.encode("utf-8")) > MAX_INPUT_BYTES:
        return None
    lowered = code.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
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
    if "width" in root.attrib or "height" in root.attrib:
        return None
    if not _check_element(root, is_root=True, allow_animation=allow_animation):
        return None
    if allow_animation:
        all_els = list(root.iter())
        anim = sum(1 for e in all_els if _local_name(e.tag)[0] in ANIM_ELEMENTS)
        drawn = len(all_els) - anim - 1  # minus the root <svg>
        if anim > _MAX_ANIM_ELEMENTS or drawn > _MAX_DRAWN_ELEMENTS:
            return None
    _strip_namespace(root)
    return ET.tostring(root, encoding="unicode")
```

- [ ] **Step 6: Run the anim tests + full figures suite**

Run: `.venv/bin/python -m pytest tests/test_figures.py -q`
Expected: PASS (new anim tests + all 30 existing tests unchanged — the static path is byte-identical).

- [ ] **Step 7: Commit**

```bash
git add backend/figures.py tests/test_figures.py
git commit -m "feat(figures): sanitize_svg allow_animation — animateTransform/animateMotion subset with value restrictions"
```

---

### Task 15: Accept `svg-animated` in the shape validators

**Files:**
- Modify: `backend/figures.py` (`valid_image_slot` from Task 11 — one line)
- Test: `tests/test_figures.py`, `tests/test_generation.py` (append)

**Interfaces:** `valid_image_slot` accepts `type == "svg-animated"` with the same non-empty `code (<=8192)` + caption rule as svg/mermaid. This flows automatically into `generation.valid_images` and `images._valid_images_slots` (both route through the shared helper after Task 11).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_figures.py
def test_valid_image_slot_accepts_svg_animated():
    from backend import figures
    assert figures.valid_image_slot(
        {"type": "svg-animated", "code": "<svg/>", "caption": "watch the flow"}) is True
    assert figures.valid_image_slot(
        {"type": "svg-animated", "code": "", "caption": "c"}) is False
```

```python
# tests/test_generation.py — svg-animated slot passes lesson validation
def test_valid_lesson_accepts_svg_animated_image():
    base = {k: "x" for k in gen.LESSON_KEYS}
    base["checks"] = [dict(_OK_CHECK)]
    base["preQuiz"] = dict(_OK_PREQUIZ)
    base["spine"] = _ok_spine()
    base["images"] = [{"type": "svg-animated", "code": "<svg viewBox='0 0 8 8'/>",
                       "caption": "watch the flow"}]
    assert gen.valid_lesson(base) is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_figures.py tests/test_generation.py -k "svg_animated" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `backend/figures.py` `valid_image_slot`, change the type check:
```python
    if kind in ("mermaid", "svg", "svg-animated"):
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/figures.py tests/test_figures.py tests/test_generation.py
git commit -m "feat(figures): accept svg-animated in image-slot shape validation"
```

---

### Task 16: `process_slots` routes `svg-animated` through the animated sanitizer

**Files:**
- Modify: `backend/images.py` `process_slots` (the type dispatch)
- Test: `tests/test_images.py` (append)

**Interfaces:** a new branch `kind == "svg-animated"` sanitizes with `figures.sanitize_svg(code, allow_animation=True)`, emits an entry `{"n", "type": "svg-animated", "code", "caption"}` on success (telemetry `rendered`) or drops with `sanitizer-rejected`. Static `svg` path unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_process_slots_svg_animated_rendered(tmp_path):
    evs, on_event = _events_capture()
    code = ('<svg viewBox="0 0 800 500"><circle r="4" fill="#d6557e">'
            '<animateMotion path="M0,0 L200,0" dur="3s" repeatCount="indefinite"/></circle></svg>')
    result = images.process_slots("demo", "demo-l1",
        [{"type": "svg-animated", "code": code, "caption": "flow"}],
        content_dir=tmp_path / "courses", resolve_images_fn=lambda *a, **k: [],
        on_event=on_event)
    assert result[0]["type"] == "svg-animated" and "animateMotion" in result[0]["code"]
    assert evs[0]["requested_type"] == "svg-animated" and evs[0]["outcome"] == "rendered"


def test_process_slots_svg_animated_rejected_drops(tmp_path):
    evs, on_event = _events_capture()
    bad = '<svg viewBox="0 0 800 500"><animate attributeName="href" values="a;b" dur="2s"/></svg>'
    result = images.process_slots("demo", "demo-l1",
        [{"type": "svg-animated", "code": bad, "caption": "x"}],
        content_dir=tmp_path / "courses", resolve_images_fn=lambda *a, **k: [],
        on_event=on_event)
    assert result == []
    assert evs[0]["drop_reason"] == "sanitizer-rejected"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -k svg_animated -q`
Expected: FAIL (svg-animated falls through to the web resolver today).

- [ ] **Step 3: Implement**

In `process_slots` (Task 3 version), add a branch after the `kind == "svg"` branch and before `elif kind == "mermaid"`:

```python
        elif kind == "svg-animated":
            sanitized = figures.sanitize_svg(slot.get("code", ""), allow_animation=True)
            if sanitized is not None:
                local_entries.append({"n": i, "type": "svg-animated", "code": sanitized,
                                       "caption": slot.get("caption", "")})
                emit(i, "svg-animated", "rendered")
            else:
                emit(i, "svg-animated", "dropped", "sanitizer-rejected")
            web_image_slots.append(None)
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/test_images.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/images.py tests/test_images.py
git commit -m "feat(images): process_slots routes svg-animated through the animated sanitizer"
```

---

### Task 17: Authoring guidance for `svg-animated`

**Files:**
- Modify: `backend/figures.py` `DRAWN_FIGURE_GUIDANCE` (append the svg-animated slot spec)
- Test: `tests/test_figures.py` (a must-survive animated exemplar authored to the rules)

**Interfaces:** none (prompt). Teaches: still-frame-is-the-fallback (base positions = start state, motion relative from `M0,0`), prefer `animateMotion`, at most one animated figure per lesson, colours from tokens, only when meaning IS change.

- [ ] **Step 1: Write the failing test**

```python
def test_svg_animated_worked_example_survives_and_stills():
    import re as _re
    src = ('<svg viewBox="0 0 800 500">'
           '<path d="M100 50 Q 300 20 500 50" fill="none" stroke="#4fa3e8" stroke-width="6"/>'
           '<circle r="6" fill="#4fa3e8"><animateMotion path="M100,50 Q300,20 500,50" '
           'dur="3s" repeatCount="indefinite"/></circle>'
           '<text x="90" y="90" font-size="16" fill="#241f1a">Deoxygenated blood</text>'
           '</svg>')
    assert figures.sanitize_svg(src, allow_animation=True) is not None
    still = _re.sub(r'<animateMotion\b[^>]*/>', '', src)
    assert figures.sanitize_svg(still) is not None  # correct labelled still remains
```

- [ ] **Step 2: Run — passes already (locks the authoring contract as sanitizer-legal)**

Run: `.venv/bin/python -m pytest tests/test_figures.py -k worked_example -q`
Expected: PASS.

- [ ] **Step 3: Append the guidance**

Add to `DRAWN_FIGURE_GUIDANCE` before the closing web-image line (before line 51-52). Insert a new svg-animated paragraph:

```python
    '  An svg-animated slot: {"type": "svg-animated", "code": "<svg ...>...</svg>", '
    '"caption": "<one sentence saying what to NOTICE>"}. Use ONLY when the meaning IS '
    "change over time (a flow, cycle, or process in motion) — a static frame with arrows "
    "cannot carry it. Hard rules: the drawing must be a correct, fully-labelled diagram "
    "with the animation REMOVED — base positions equal the start state and motion is "
    "expressed relatively (paths from M0,0), so stripping the animation leaves a sensible "
    "still. Prefer animateMotion (a <circle> travelling a path). Allowed animation is "
    "animateTransform (attributeName=\"transform\", type translate/scale/rotate/skewX/skewY) "
    "and animateMotion only; no other animation elements, no <style>, no href. Keep it "
    "under 30 drawn and 8 animation elements, each dur 1-20s; at most ONE animated figure "
    "per lesson. Labels stay fixed. Colours from the brand palette, except where a colour "
    "carries meaning (arterial-red vs venous-blue).\n"
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/test_figures.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/figures.py tests/test_figures.py
git commit -m "feat(prompt): svg-animated authoring guidance with still-frame fallback rule"
```

---

### Task 18: Frontend render — `svg-animated` placeholder

**Files:**
- Modify: `frontend/src/views/lesson.js` (`figureHTML` line 98-102, `isValidFigureEntry` line 104-113)
- Test: `frontend/tests/figures.test.js` (append — exercises via the exported `expandFigureTokens`)

**Interfaces:**
- `isValidFigureEntry` accepts `entry.type === "svg-animated"` with the same non-empty-`code` check as svg/mermaid.
- `figureHTML` routes `svg-animated` to `drawnFigurePlaceholderHTML(entry, "fig-svg-anim")`, emitting `class="lesson-fig lesson-fig-svg-animated" data-fig-svg-anim="n"` + the caption (SVG body injected at hydration; controls added by the player).

- [ ] **Step 1: Write the failing test**

```javascript
import { expandFigureTokens } from "../src/views/lesson.js";

test("expandFigureTokens renders an svg-animated placeholder with the anim data attr", () => {
  const lesson = {
    images: [{ n: 1, type: "svg-animated", code: "<svg viewBox='0 0 8 8'/>", caption: "flow" }],
    promptHtml: "<p>Body</p>[[figure:1]]",
  };
  const { html } = expandFigureTokens(lesson.promptHtml, lesson, "demo");
  assert.ok(html.includes('data-fig-svg-anim="1"'));
  assert.ok(html.includes("lesson-fig-svg-animated"));
  assert.ok(html.includes("flow"));
});

test("expandFigureTokens drops an svg-animated entry with empty code", () => {
  const lesson = {
    images: [{ n: 1, type: "svg-animated", code: "", caption: "x" }],
    promptHtml: "[[figure:1]]",
  };
  const { html } = expandFigureTokens(lesson.promptHtml, lesson, "demo");
  assert.ok(!html.includes("lesson-fig-svg-animated"));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && node --test tests/figures.test.js`
Expected: FAIL (svg-animated invalidated → nothing rendered).

- [ ] **Step 3: Implement**

`frontend/src/views/lesson.js` — `figureHTML` (lines 98-102), add a branch:
```javascript
function figureHTML(entry, courseId) {
  if (entry.type === "svg") return drawnFigurePlaceholderHTML(entry, "fig-svg");
  if (entry.type === "svg-animated") return drawnFigurePlaceholderHTML(entry, "fig-svg-anim");
  if (entry.type === "mermaid") return drawnFigurePlaceholderHTML(entry, "fig-mermaid");
  return webImageFigureHTML(entry, courseId);
}
```
`isValidFigureEntry` (line 109), extend the code-bearing branch:
```javascript
  if (entry.type === "svg" || entry.type === "mermaid" || entry.type === "svg-animated") {
    return typeof entry.code === "string" && entry.code.length > 0;
  }
```

- [ ] **Step 4: Run tests + import check**

Run: `cd frontend && node --test tests/figures.test.js && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})"`
Expected: PASS + `imports ok`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/lesson.js frontend/tests/figures.test.js
git commit -m "feat(frontend): render svg-animated figure placeholder"
```

---

### Task 19: Animated DOMPurify config + paused hydration

**Files:**
- Modify: `frontend/src/app.js` (add `SVG_ANIM_SANITIZE_CONFIG` after `SVG_SANITIZE_CONFIG` line 1909; add a `[data-fig-svg-anim]` hydration branch in `hydrateFigures`)
- Test: verified by the client-layer harness in Task 22 (DOMPurify needs a DOM; not unit-testable in the node suite). The import-resolution check is the gate here.

**Interfaces:**
- `frontend/src/figureconfig.js` (new) exports `SVG_ANIM_SANITIZE_CONFIG` — the static allowlists plus `animateTransform`/`animateMotion` in `ALLOWED_TAGS`, the animation attrs in `ALLOWED_ATTR`, and explicit `FORBID_TAGS`/`FORBID_ATTR` per spec §5E. It lives in its own module (not inline in `app.js`) so the Task 22 client-layer harness imports the *real* config, not a copy.
- A new `hydrateFigures` branch: sanitize `entry.code` with the animated config, inject, then call `svg.pauseAnimations()` so the figure loads paused-on-still (the correct default even before the player attaches in Task 21).

- [ ] **Step 1: Create the animated sanitize config module**

`frontend/src/figureconfig.js`:

```javascript
// Animated-figure client DOMPurify config (defense in depth over
// backend/figures.py's allow_animation sanitizer). Its own module so the
// client-layer sanitizer harness can import the exact config the app uses.
// Adds only the animateTransform/animateMotion subset to the advisory
// allowlists; the FORBID lists are operative and kill the dangerous animation
// elements and href even if a future DOMPurify default promotes them.
export const SVG_ANIM_SANITIZE_CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ALLOWED_TAGS: ["svg","g","rect","circle","ellipse","line","polyline","polygon","path","text","tspan","title","defs","marker","animateTransform","animateMotion"],
  ALLOWED_ATTR: ["viewBox","x","y","x1","y1","x2","y2","cx","cy","r","rx","ry","width","height","d","points","transform","fill","stroke","stroke-width","stroke-dasharray","stroke-linecap","stroke-linejoin","font-size","font-family","font-weight","text-anchor","dominant-baseline","opacity","fill-opacity","marker-end","marker-start","id","class","attributeName","type","dur","begin","repeatCount","values","additive","accumulate","path","keyPoints","rotate"],
  FORBID_TAGS: ["animate","set","mpath","animateColor","discard","style","image","use","a","foreignObject","script"],
  FORBID_ATTR: ["href","xlink:href"],
};
```

Then in `frontend/src/app.js`, add to the import block: `import { SVG_ANIM_SANITIZE_CONFIG } from "./figureconfig.js";`.

- [ ] **Step 2: Add the paused hydration branch**

In `hydrateFigures`, after the `[data-fig-svg]` block (line 1935) add:

```javascript
    view.querySelectorAll("[data-fig-svg-anim]").forEach((fig) => {
      const entry = byN.get(Number(fig.dataset.figSvgAnim));
      if (!entry || typeof entry.code !== "string") return;
      loadPurify()
        .then((DOMPurify) => {
          if (!stillFresh() || !fig.isConnected) return;
          const clean = DOMPurify.sanitize(entry.code, SVG_ANIM_SANITIZE_CONFIG);
          fig.insertAdjacentHTML("afterbegin", clean);
          const svg = fig.querySelector("svg");
          if (svg && typeof svg.pauseAnimations === "function") svg.pauseAnimations();
        })
        .catch(() => {}); // caption already shown is the fallback
    });
```

- [ ] **Step 3: Import check**

Run: `cd frontend && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})"`
Expected: `imports ok`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/figureconfig.js frontend/src/app.js
git commit -m "feat(frontend): animated DOMPurify config + paused-on-still hydration for svg-animated"
```

---

## Phase G — Interactive figure player (Tier-A generic controls)

The controls belong to the trusted app, never the figure. A small player module owns all interactivity by driving the SVG's own SMIL clock — the exact mechanism verified in the 2026-07-23 heart mockup.

### Task 20: `figureplayer.js` module (clock driver + controls)

**Files:**
- Create: `frontend/src/figureplayer.js`
- Create: `frontend/tests/figureplayer.test.js` (pure-logic unit tests; DOM attach verified in Task 22)

**Interfaces:**
- Produces:
  - `clampSpeed(v) -> number` (clamped to `[SPEED_MIN, SPEED_MAX]` = `[0.25, 2.5]`; non-finite → 1).
  - `nextTime(t, dtSeconds, speed) -> number` (`t + max(0,dt)*clampSpeed(speed)`, never negative).
  - `attachFigurePlayer(fig, { reducedMotion=false, win=window } = {}) -> controller|null` — finds the injected `<svg>`, pauses its SMIL clock, injects a trusted control chip, and drives `svg.setCurrentTime(t += dt*speed)` via `requestAnimationFrame`. Returns a controller `{ isPlaying(), setPlaying(on), destroy() }`, or `null` if no `<svg>` present. Starts **paused** when `reducedMotion` is true.

- [ ] **Step 1: Write the failing pure-logic tests**

`frontend/tests/figureplayer.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { clampSpeed, nextTime, SPEED_MIN, SPEED_MAX } from "../src/figureplayer.js";

test("clampSpeed clamps to [0.25, 2.5] and defaults non-finite to 1", () => {
  assert.equal(clampSpeed(0.1), SPEED_MIN);
  assert.equal(clampSpeed(9), SPEED_MAX);
  assert.equal(clampSpeed(1.5), 1.5);
  assert.equal(clampSpeed("x"), 1);
});

test("nextTime advances by dt*speed and never goes negative", () => {
  assert.equal(nextTime(0, 1, 1), 1);
  assert.equal(nextTime(2, 0.5, 2.5), 2 + 0.5 * 2.5);
  assert.equal(nextTime(0, -1, 1), 0); // negative dt clamped
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && node --test tests/figureplayer.test.js`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `frontend/src/figureplayer.js`**

```javascript
// Trusted app-side figure player. The model-generated SVG stays pure declarative
// markup; the app pauses the SVG's own SMIL clock and advances it manually each
// frame at the chosen speed, so play/pause/replay/speed all ride one clock.
// (Mechanism verified in the 2026-07-23 heart mockup: rate 1.0 = true time,
// setCurrentTime advances the paused clock.) No executable code ever lives in a
// figure — this is why interactivity stays inside the sanitizer's security model.

export const SPEED_MIN = 0.25;
export const SPEED_MAX = 2.5;

export function clampSpeed(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 1;
  return Math.min(SPEED_MAX, Math.max(SPEED_MIN, n));
}

export function nextTime(t, dtSeconds, speed) {
  const nt = t + Math.max(0, dtSeconds) * clampSpeed(speed);
  return nt < 0 ? 0 : nt;
}

const CONTROLS_HTML =
  '<div class="fig-controls" role="group" aria-label="Figure playback controls">' +
  '<button type="button" data-fig-play aria-pressed="false">Play</button>' +
  '<button type="button" data-fig-replay>Replay</button>' +
  '<label class="fig-speed">Speed ' +
  '<input type="range" min="0.25" max="2.5" step="0.25" value="1" data-fig-speed ' +
  'aria-label="Playback speed"></label></div>';

export function attachFigurePlayer(fig, { reducedMotion = false, win = window } = {}) {
  const svg = fig.querySelector("svg");
  if (!svg || typeof svg.setCurrentTime !== "function") return null;
  if (typeof svg.pauseAnimations === "function") svg.pauseAnimations();

  let playing = false;
  let speed = 1;
  let t = 0;
  let last = null;
  let rafId = null;
  let onScreen = true;

  fig.insertAdjacentHTML("beforeend", CONTROLS_HTML);
  const playBtn = fig.querySelector("[data-fig-play]");
  const replayBtn = fig.querySelector("[data-fig-replay]");
  const speedInput = fig.querySelector("[data-fig-speed]");

  function render() {
    playBtn.textContent = playing ? "Pause" : "Play";
    playBtn.setAttribute("aria-pressed", String(playing));
  }
  function frame(ts) {
    if (last === null) last = ts;
    const dt = (ts - last) / 1000;
    last = ts;
    if (playing && onScreen) {
      t = nextTime(t, dt, speed);
      svg.setCurrentTime(t);
    }
    rafId = win.requestAnimationFrame(frame);
  }
  function setPlaying(on) {
    playing = on;
    last = null;
    render();
  }

  playBtn.addEventListener("click", () => setPlaying(!playing));
  replayBtn.addEventListener("click", () => {
    t = 0;
    svg.setCurrentTime(0);
    setPlaying(true);
  });
  speedInput.addEventListener("input", () => { speed = clampSpeed(speedInput.value); });

  // Pause off-screen figures; resume only if the learner had it playing.
  let observer = null;
  if (typeof win.IntersectionObserver === "function") {
    observer = new win.IntersectionObserver((entries) => {
      for (const e of entries) onScreen = e.isIntersecting;
    });
    observer.observe(fig);
  }

  setPlaying(!reducedMotion ? false : false); // default paused (read-first / reduced-motion)
  render();
  rafId = win.requestAnimationFrame(frame);

  return {
    isPlaying: () => playing,
    setPlaying,
    destroy() {
      if (rafId) win.cancelAnimationFrame(rafId);
      if (observer) observer.disconnect();
    },
  };
}
```

Note: default is **paused** for every figure (read-first / low-glare); `reducedMotion` is therefore already satisfied by the default and the parameter is retained for clarity and future use. Loop is inherent (figures are authored with `repeatCount="indefinite"`); a loop-*off* toggle needs cycle-duration detection and is deferred to v2 (documented divergence from the spec's Tier-A control list).

- [ ] **Step 4: Run tests + import check**

Run: `cd frontend && node --test tests/figureplayer.test.js && node -e "import('./src/figureplayer.js').then(()=>console.log('ok'))"`
Expected: PASS + `ok`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/figureplayer.js frontend/tests/figureplayer.test.js
git commit -m "feat(frontend): figure player module — SMIL clock driver + Tier-A controls"
```

---

### Task 21: Wire the player into hydration + control-chip CSS

**Files:**
- Modify: `frontend/src/app.js` (import `attachFigurePlayer`; call it in the `[data-fig-svg-anim]` hydration branch after inject; compute `reducedMotion`)
- Modify: `frontend/styles.css` (animated container + `.fig-controls` chip styling)
- Test: import check + Task 22 harness/MCP.

**Interfaces:** consumes `attachFigurePlayer` (Task 20). After the animated SVG is injected and paused (Task 19), attach the player so the control chip appears and drives the clock.

- [ ] **Step 1: Wire the attach call**

In `frontend/src/app.js`, add to the import block: `import { attachFigurePlayer } from "./figureplayer.js";`. In the `[data-fig-svg-anim]` hydration branch (Task 19), replace the `svg.pauseAnimations()` line with the player attach (which pauses internally):

```javascript
          const clean = DOMPurify.sanitize(entry.code, SVG_ANIM_SANITIZE_CONFIG);
          fig.insertAdjacentHTML("afterbegin", clean);
          const reduced = win.matchMedia
            && win.matchMedia("(prefers-reduced-motion: reduce)").matches;
          attachFigurePlayer(fig, { reducedMotion: !!reduced, win });
```

Confirm `win` is available in this scope (the app's window handle). If the local handle is named differently (e.g. `window` or a module `win`/`w`), use that name — check the top of `app.js` for how the injected window is referenced (the boot passes `{ window }` to `init`; recon shows `doc`/`window` usage). If only `window` (global) is available here, use `window`.

- [ ] **Step 2: Add the CSS**

In `frontend/styles.css`, after the Task 7 drawn-figure rules, add:

```css
/* Animated figures: same glass tile, centred SVG, plus the trusted control chip. */
.lesson-fig-svg-animated{
  background:var(--glass-inner); border:1px solid var(--border-field);
  border-radius:14px; padding:14px 16px;
}
.lesson-fig-svg-animated svg{display:block; width:auto; max-width:100%; height:auto; margin:0 auto 6px}
.fig-controls{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:8px 0 2px}
.fig-controls button{
  font:600 13px/1 var(--ui); color:var(--text); background:var(--glass-field);
  border:1px solid var(--border-field); border-radius:999px; padding:6px 14px; cursor:pointer;
}
.fig-controls button:hover{filter:brightness(0.98)}
.fig-controls button:focus-visible{outline:2px solid var(--purple); outline-offset:2px}
.fig-controls .fig-speed{display:flex; align-items:center; gap:6px; font:600 12px/1 var(--ui); color:var(--text-dim)}
.fig-controls input[type=range]{accent-color:var(--purple); cursor:pointer}
```

- [ ] **Step 3: Import check + brace check**

Run: `cd frontend && node -e "import('./src/app.js').then(()=>console.log('imports ok')).catch(e=>{console.error(e.message);process.exit(1)})" && node -e "const c=require('fs').readFileSync('styles.css','utf8'); const o=(c.match(/{/g)||[]).length, x=(c.match(/}/g)||[]).length; if(o!==x){console.error('brace mismatch',o,x);process.exit(1)} console.log('css ok',o)"`
Expected: `imports ok` + `css ok <n>`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "feat(frontend): attach figure player + control-chip styling for animated figures"
```

(Same styles.css / Werner-reskin caveat as Task 7 applies — see Phase-review note.)

---

### Task 22: Client-layer sanitizer + player verification (harness + MCP browser)

The repo has **no Playwright/jsdom test infra** (by design — `app.js` is verified by the import check + manual/MCP browser checks). DOMPurify and the player need a real DOM, so this is a committed HTML harness driven by the MCP browser tool, not a new automated framework.

**Files:**
- Create: `frontend/tests/figure-sanitize.harness.html` (imports the real `/vendor/purify.min.js` + `figureconfig.js`, runs the must-pass / must-strip corpus, writes PASS/FAIL to the DOM)

- [ ] **Step 1: Write the harness**

`frontend/tests/figure-sanitize.harness.html` — an HTML page that:
1. loads `/vendor/purify.min.js` via `<script src>`,
2. `import { SVG_ANIM_SANITIZE_CONFIG } from "/src/figureconfig.js"`,
3. for each corpus case, runs `DOMPurify.sanitize(code, SVG_ANIM_SANITIZE_CONFIG)` and asserts:
   - must-pass (spin/slide/motion): output still contains `animatetransform`/`animatemotion` (case-insensitive),
   - must-strip: `<animate>`, `<set>`, `<mpath>`, `<style>` removed; `from`/`to`/`calcMode` stripped (locks the `values`-only contract); `href`/`xlink:href` removed,
4. renders a `<ul id="results">` with `PASS`/`FAIL: <case>` lines and sets `document.title` to `ALL PASS` or `HAS FAIL`.

```html
<!doctype html>
<meta charset="utf-8">
<title>running…</title>
<script src="/vendor/purify.min.js"></script>
<ul id="results"></ul>
<script type="module">
  import { SVG_ANIM_SANITIZE_CONFIG } from "/src/figureconfig.js";
  const S = (c) => DOMPurify.sanitize(c, SVG_ANIM_SANITIZE_CONFIG).toLowerCase();
  const cases = [
    ["keeps animateTransform", '<svg viewBox="0 0 8 8"><rect width="4" height="4"><animateTransform attributeName="transform" type="translate" values="0 0;4 0" dur="2s"/></rect></svg>', o => o.includes("animatetransform")],
    ["keeps animateMotion", '<svg viewBox="0 0 8 8"><circle r="2"><animateMotion path="M0,0 L4,0" dur="2s"/></circle></svg>', o => o.includes("animatemotion")],
    ["strips animate", '<svg viewBox="0 0 8 8"><rect width="4" height="4"><animate attributeName="x" values="0;4" dur="2s"/></rect></svg>', o => !o.includes("<animate")],
    ["strips set", '<svg viewBox="0 0 8 8"><set attributeName="x" to="4"/></svg>', o => !o.includes("<set")],
    ["strips mpath", '<svg viewBox="0 0 8 8"><animateMotion><mpath xlink:href="#p"/></animateMotion></svg>', o => !o.includes("mpath")],
    ["strips style", '<svg viewBox="0 0 8 8"><style>*{fill:red}</style></svg>', o => !o.includes("<style")],
    ["strips from/to/calcMode", '<svg viewBox="0 0 8 8"><rect width="4" height="4"><animateTransform attributeName="transform" type="translate" from="0 0" to="4 0" calcMode="linear" dur="2s"/></rect></svg>', o => !o.includes("from=") && !o.includes(" to=") && !o.includes("calcmode")],
    ["strips href", '<svg viewBox="0 0 8 8"><a href="javascript:alert(1)"><rect width="4" height="4"/></a></svg>', o => !o.includes("javascript")],
  ];
  const ul = document.getElementById("results");
  let ok = true;
  for (const [name, code, check] of cases) {
    let pass;
    try { pass = check(S(code)); } catch (e) { pass = false; }
    ok = ok && pass;
    const li = document.createElement("li");
    li.textContent = (pass ? "PASS: " : "FAIL: ") + name;
    ul.appendChild(li);
  }
  document.title = ok ? "ALL PASS" : "HAS FAIL";
</script>
```

- [ ] **Step 2: Serve + verify with the MCP browser**

The app must be running (or serve the repo statically). Preferred: start the app (`.venv/bin/python -m backend.app` or the waitress command) so `/vendor/*` and `/src/*` resolve same-origin, then with the MCP Playwright browser tool navigate to `http://127.0.0.1:<port>/tests/figure-sanitize.harness.html` — **but** the harness is under `frontend/tests/`, which is not a served route. Instead copy the harness to a served location for the check, OR serve `frontend/` directly: `cd frontend && python3 -m http.server 8791 --bind 127.0.0.1`, then navigate to `http://127.0.0.1:8791/tests/figure-sanitize.harness.html` (this resolves `/vendor/` and `/src/` because the server root is `frontend/`).

Using the MCP browser tool: navigate to the harness URL, read `document.title`, assert it is `ALL PASS`, and snapshot the `#results` list. Record the result in the task report. Stop the http.server after.

- [ ] **Step 3: Verify the player interactively (same served harness or a live lesson)**

With the MCP browser, on a page containing an injected animated figure (either a small player harness or, post-deploy, a real lesson): confirm the SVG loads paused (`svg.animationsPaused()` true), clicking Play advances `svg.getCurrentTime()`, the speed slider changes the advance rate, Replay resets to 0, and `prefers-reduced-motion` keeps it paused. Record observations in the report (this mirrors the heart-mockup verification method).

- [ ] **Step 4: Commit the harness**

```bash
git add frontend/tests/figure-sanitize.harness.html
git commit -m "test(frontend): client-layer DOMPurify + player verification harness"
```

---

## Phase F — Content-Security-Policy header

The security review found no CSP anywhere. Add one as a cheap third layer. The audit (recon) found exactly one inline `<script>` (externalize it to keep `script-src 'self'` clean) and runtime inline *styles* (which require `style-src 'unsafe-inline'` — the spec forbids `unsafe-inline` only for *scripts*).

### Task 23: Externalize the inline boot script

**Files:**
- Create: `frontend/src/boot.js`
- Modify: `frontend/platform.html:14-23` (replace the inline module script with a `src=` reference)
- Test: `tests/test_static.py` (append — assert no inline script body remains)

**Interfaces:** the page's only inline script moves to `/src/boot.js` (served same-origin by the existing `/src/<path>` route), so `script-src 'self'` needs no hash/nonce/`unsafe-inline`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_static.py`:
```python
def test_platform_html_has_no_inline_script_body():
    from pathlib import Path
    html = Path("frontend/platform.html").read_text()
    assert 'src="/src/boot.js"' in html
    assert "import { init }" not in html  # boot logic moved out of the page
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_static.py -k inline_script -q`
Expected: FAIL.

- [ ] **Step 3: Create `frontend/src/boot.js`**

```javascript
// App bootstrap, moved out of platform.html so the page carries no inline script
// (keeps the CSP script-src at 'self' with no hash/nonce).
import { init } from "/src/app.js";

init({ window, fetch: window.fetch.bind(window) });

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
```

- [ ] **Step 4: Update `frontend/platform.html`**

Replace lines 14-23 (the inline `<script type="module">…</script>`) with:
```html
    <script type="module" src="/src/boot.js"></script>
```

- [ ] **Step 5: Run test + import check**

Run: `.venv/bin/python -m pytest tests/test_static.py -q && cd frontend && node -e "import('./src/boot.js').then(()=>console.log('ok')).catch(e=>{console.error(e.message);process.exit(1)})"`
Expected: PASS + `ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/boot.js frontend/platform.html tests/test_static.py
git commit -m "refactor(frontend): externalize boot script so CSP script-src stays 'self'"
```

---

### Task 24: Add the CSP (+ nosniff) response header

**Files:**
- Modify: `backend/app.py` (`create_app` — add an `after_request` hook)
- Test: `tests/test_app.py` (or the file housing route tests; uses the `client` fixture from `tests/conftest.py`)

**Interfaces:** every response carries `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'` and `X-Content-Type-Options: nosniff`. `unsafe-inline` is present for styles only (runtime `.style` assignments + mermaid's rendered `<style>`), never for scripts.

- [ ] **Step 1: Write the failing tests**

```python
def test_csp_header_on_index(client):
    csp = client.get("/").headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "script-src 'self';" in csp        # script-src is exactly 'self' — no unsafe-inline
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp

def test_csp_header_on_api(client):
    assert client.get("/api/courses").headers.get("Content-Security-Policy") is not None

def test_style_src_allows_inline_but_script_src_does_not(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    style_dir = [d for d in csp.split(";") if "style-src" in d][0]
    script_dir = [d for d in csp.split(";") if "script-src" in d][0]
    assert "unsafe-inline" in style_dir
    assert "unsafe-inline" not in script_dir
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_app.py -k csp -q`
Expected: FAIL (no header). (If the route-test file has a different name, place these tests wherever the `client` fixture is already used — grep `def test_` + `client)` to find it.)

- [ ] **Step 3: Implement**

In `backend/app.py` `create_app`, after the routes are registered (anywhere inside `create_app`, before `return app`), add:

```python
    _CSP = ("default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        return resp
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Verify the app is not broken (MCP browser)**

With the app running, use the MCP browser to load the home page and a lesson: confirm the console shows **no CSP violation errors**, and that CSS, mermaid figures, an svg-animated figure + its controls, and web-images all still render. This is the "CSP doesn't break the app" gate the spec requires (§5F). Record the console state in the report.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_app.py
git commit -m "feat(security): Content-Security-Policy + nosniff response headers"
```

---

## Pre-flight (before Task 1)

- **Confirm the branch:** work continues on `feat/lesson-visuals` (the spec commit `d98eb1e` is here). Do not start on `main`.
- **Werner-gated: commit or stash the Golden-Hour `styles.css` reskin first.** `frontend/styles.css` has uncommitted local changes (Werner's reskin + the self-hosted Newsreader font fix). Tasks 7 and 21 add figure CSS to this file. If the reskin is still uncommitted when those tasks run, `git add frontend/styles.css` will entangle Werner's work with the figure CSS. **Ask Werner to commit the reskin (and `frontend/vendor/newsreader/`) before implementation begins**, so the figure-CSS commits are clean and isolated. This is the one hard prerequisite the controller must resolve with Werner before Task 7.
- **Two files also touch `frontend/src/app.js`** across phases (Tasks 5, 10, 19, 21) — these are sequential, same-session edits; no conflict, but the controller runs the frontend import check after each.

## Verification & Deploy (Werner-gated — NOT part of implementation)

After all tasks pass their reviews and the whole-branch review is clean, these steps ship it. **All are Werner-gated per the deploy memory (the Pi is production and the only data copy; backups first; never `rsync --delete`).**

1. **Full green locally:** `.venv/bin/python -m pytest tests/ -q` (966 + new) and `cd frontend && node --test` (371 + new) and the import check.
2. **Deploy to the Pi** using the canonical command in `docs/DEPLOY.md` (never `rsync --delete`; take the daily content backup first). Restart the service; pull + verify. **Bump the service-worker cache version** in `frontend/sw.js` (`const CACHE = "cu-shell-vN"` → `vN+1`) as part of this deploy — the SW serves `/styles.css` and all `/src/*` + `/vendor/*` assets cache-first, so without a version bump users keep the *old* `styles.css`/`app.js`/`figureplayer.js` for at least a load and the frozen cache never self-purges. Bumping the name makes the `activate` handler delete the stale cache so the new figure JS/CSS actually reaches users. (Set to `cu-shell-v3`; `v2` was used for the Golden-Hour reskin deploy.)
3. **Capture the telemetry baseline BEFORE regeneration** (spec §5A): the `figure-telemetry.jsonl` starts empty; the baseline is the *current* on-brand-but-mermaid-only distribution. Record `figure_metrics.compute(content_dir, <course>)` for each of the 4 live courses as the baseline the regression gate (Task 13) compares against.
4. **Verify the style contract on real figures** (spec §5C): open the human-body course on the real Pi URL; confirm the 6 existing mermaid figures now render in the warm on-brand palette (render-time theming — no regeneration needed) and sit on the glass tile.
5. **Regenerate a handful of lessons across domains** (esp. human-body) to exercise B/D/E — confirm via telemetry that `web-image` and `svg`/`svg-animated` now appear (realization rate > 0), visually confirm a working animated figure with controls + reduced-motion, on the real Pi URL. Run the regression gate: alignment ↑ AND figures/lesson within ±10% of baseline AND zero-figure rate not falling — else revert the prompt (D).
6. **(Deferred, Werner's call) Re-resolve existing lessons for photos.** The spec's "backfill = yes" for *re-resolving* existing lessons (swapping mermaid→photos where warranted) is **not built in this plan** — `backfill_course` skips lessons that already have images, and re-resolving overwrites cached content on the only data copy. If Werner wants it, it is a follow-up: add a `force` re-resolve mode to `backfill_course` (strip existing figures/tokens, re-propose) as its own small plan, run with a fresh backup. The high-value half (on-brand existing figures) is already delivered by step 4 for free.
7. **Tier-B showcases (post-release curated track):** the heart-rate heart (`scratchpad/heart-mockup.html`) is the first Tier-B showcase — hand-built, trusted-by-review, added on demand, never a release gate. Not part of this plan.

## Self-Review (completed by plan author)

**1. Spec coverage** — every §5 component maps to tasks:
- §5A telemetry → Tasks 1-4 (+ baseline in Deploy step 3). §5B drop-fixes → Tasks 8, 9, 10. §5C style → Tasks 5, 6, 7. §5D router + difficulty + metrics → Tasks 11, 12, 13 (difficulty scales the control layer, delivered generically by the player G; population metrics = Task 13). §5E animated SVG → Tasks 14-19. §5F CSP → Tasks 23, 24. §5G player → Tasks 20, 21, 22.
- §6 data model → Task 15 (`valid_image_slot`), Task 16 (`process_slots`), Task 18 (`isValidFigureEntry`/`figureHTML` + `data-fig-svg-anim`); no new figure field (confirmed — player attaches by type). §7 sequencing → phase order A→C→B→D→E→G→F matches. §8 testing → server unit tests throughout, malicious+must-pass corpus (Task 14), still-frame test (Tasks 14, 17), client-layer harness (Task 22), import checks per frontend task, Pi live-verify (Deploy). §9 decisions → honored, with three refinements flagged at the top. §10 risks → the regression gate (Task 13) enforces "no decorative bloat"; difficulty stays coarse (read from bloom/knowledge, validated by telemetry before scaling — nothing here scales machinery on it).

**2. Placeholder scan** — no TBD/TODO; every code step carries real code; every test step carries real assertions.

**3. Type consistency** — `on_event(record)` dict shape is identical across Tasks 2/3/4/16; `valid_image_slot` is the single validator after Task 11 and gains svg-animated in Task 15; `SVG_ANIM_SANITIZE_CONFIG` defined once (Task 19, `figureconfig.js`) and consumed by app.js (Task 19) + harness (Task 22); `attachFigurePlayer`/`clampSpeed`/`nextTime` signatures consistent across Tasks 20/21; `data-fig-svg-anim` attribute name identical in lesson.js render (Task 18) and app.js hydration (Task 19). Class `lesson-fig-svg-animated` (from `lesson-fig-${entry.type}`) matches the CSS selector in Task 21.

**Known intentional divergences from the spec (flagged, not gaps):** (a) telemetry sink = JSONL not events table (no DB in the pipeline); (b) style contract reaches existing figures at render time, risky re-resolve deferred; (c) control-chip uses existing glass tokens; (d) Tier-A loop-*off* toggle deferred (figures repeat by authoring). Each is justified inline where it appears.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-lesson-visuals.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh implementer subagent per task, a task review (spec + quality) after each, a whole-branch review at the end. Werner asked for this ("sub agent driven is good").
2. **Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints.

**Before Task 1**, the controller must resolve the one pre-flight prerequisite with Werner: commit/stash the uncommitted `styles.css` reskin so the figure-CSS tasks stay clean.
