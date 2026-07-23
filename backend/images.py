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

from backend import claude_client, figure_telemetry, figures, fsutil

USER_AGENT = "ClaudeUniversity/1.0 (personal learning app; wernerpvanellewee@gmail.com)"

MAX_BYTES = 2 * 1024 * 1024
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


def _safe_url(value):
    """Validate that a URL is a safe http(s) URL. Returns the URL if valid, None
    otherwise. Rejects javascript:, data:, and other dangerous schemes."""
    if not isinstance(value, str) or not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return None


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
        ("iiurlwidth", "1600"),
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
            "licenseUrl": _safe_url(_mv("LicenseUrl")),
            "sourceUrl": _safe_url(info.get("descriptionurl")) or "",
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
            "licenseUrl": _safe_url(r.get("license_url")),
            "sourceUrl": _safe_url(r.get("foreign_landing_url")) or "",
            "attributionRequired": True,
        })
    return candidates


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
    entry = {
        "n": n,
        "type": "web-image",
        "file": filename,
        "caption": caption,
        "credit": build_credit(candidate),
        "license": candidate.get("licenseShort") or "",
        "licenseUrl": candidate.get("licenseUrl"),
        "sourceUrl": candidate.get("sourceUrl") or "",
    }
    if on_event:
        on_event({"course_id": course_id, "lesson_id": lesson_id, "n": n,
                  "requested_type": "web-image", "outcome": "rendered",
                  "drop_reason": None, "query": query})
    return entry


def _default_structured(prompt, *, validate=None, tools=None):
    return claude_client.run_structured(prompt, validate=validate, tools=tools)


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


def process_slots(course_id, lesson_id, slots, *, content_dir, resolve_images_fn=None,
                  on_event=None):
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
    `resolve_images`). `on_event`, if given, receives exactly one record per slot
    (see Task A) — local svg/mermaid records emitted here, web-image records from
    the resolver."""

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
        elif kind == "svg-animated":
            sanitized = figures.sanitize_svg(slot.get("code", ""), allow_animation=True)
            if sanitized is not None:
                local_entries.append({"n": i, "type": "svg-animated", "code": sanitized,
                                       "caption": slot.get("caption", "")})
                emit(i, "svg-animated", "rendered")
            else:
                emit(i, "svg-animated", "dropped", "sanitizer-rejected")
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


def _valid_images_slots(images_val):
    """Backfill-specific images-shape check: unlike generation.valid_images,
    the key must ALWAYS be a list (possibly empty) — the proposal always states
    a decision, it never omits the field. Same three per-slot shapes as
    generation.valid_images (web-image needs query+caption; mermaid/svg need
    code (<=8192 chars) + caption); any other `type` is invalid."""
    if not (isinstance(images_val, list) and len(images_val) <= MAX_SLOTS):
        return False
    for slot in images_val:
        if not figures.valid_image_slot(slot):
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
        except Exception:
            continue  # never block the batch on one flaky lesson
        lesson["promptHtml"] = proposal["promptHtml"]
        try:
            resolved = process_slots(course_id, lesson_id, proposal["images"], content_dir=content_dir,
                                      on_event=lambda ev: figure_telemetry.record(content_dir, ev))
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
    _run = claude_client.structured_generate
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
