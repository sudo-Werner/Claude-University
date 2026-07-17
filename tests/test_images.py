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


def test_resolve_images_caps_download_attempts_not_successes(tmp_path):
    """Verify that download attempts are capped at MAX_DOWNLOADS_PER_SLOT, even if all
    downloads fail verification. This protects the per-lesson time budget by preventing
    excessive attempts when candidates keep failing magic-byte checks."""
    content_dir = tmp_path / "courses"

    # Build 8 license-valid candidates from Commons + Openverse
    commons_json = json.dumps({"query": {"pages": {
        str(i): {"title": f"File:C{i}.png", "imageinfo": [{
            "thumburl": f"https://upload.wikimedia.org/c{i}.png",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/File:C{i}.png",
            "extmetadata": {"LicenseShortName": {"value": "CC0"}, "Artist": {"value": "Ann"},
                            "AttributionRequired": {"value": "false"}}}]}
        for i in range(4)  # 4 Commons candidates
    }}}).encode()

    openverse_json = json.dumps({"results": [
        {"title": f"Openverse photo {i}", "creator": "Cara",
         "thumbnail": f"https://api.openverse.org/thumb/{i}",
         "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
         "foreign_landing_url": "https://flickr.com/x"}
        for i in range(4)  # 4 Openverse candidates
    ]}).encode()

    download_calls = {"count": 0}

    def fake_http_get(url):
        # API search calls
        if "commons.wikimedia.org" in url:
            return commons_json
        if "api.openverse.org" in url:
            return openverse_json
        # Download attempts — return SVG bytes (fails magic-byte verification)
        download_calls["count"] += 1
        return _SVG_BYTES

    def fake_structured(prompt, *, validate=None, tools=None):
        return {"pick": None}  # Explicit null drop (no vision error)

    slots = [{"query": "test", "caption": "test caption"}]
    resolved = images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                                     http_get=fake_http_get, structured=fake_structured)

    # All downloads fail verification, so no slot resolves
    assert resolved == []
    # But we should have capped attempts at MAX_DOWNLOADS_PER_SLOT (4), not tried all 8
    assert download_calls["count"] <= images.MAX_DOWNLOADS_PER_SLOT
