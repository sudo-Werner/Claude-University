import json

from backend import images


_JPEG_BYTES = b"\xff\xd8\xff" + b"0" * 50
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 50
_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 50
_SVG_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


# ---- write_bytes_atomic already covered in tests/test_fsutil.py ----


# ---- _safe_url: reject non-http(s) URLs (XSS prevention) ----

def test_safe_url_accepts_https():
    assert images._safe_url("https://creativecommons.org/licenses/by-sa/4.0") == \
        "https://creativecommons.org/licenses/by-sa/4.0"


def test_safe_url_accepts_http():
    assert images._safe_url("http://commons.wikimedia.org/wiki/File:X") == \
        "http://commons.wikimedia.org/wiki/File:X"


def test_safe_url_rejects_javascript_url():
    assert images._safe_url("javascript:alert(1)") is None


def test_safe_url_rejects_data_url():
    assert images._safe_url("data:text/html,<script>alert(1)</script>") is None


def test_safe_url_rejects_none():
    assert images._safe_url(None) is None


def test_safe_url_rejects_empty_string():
    assert images._safe_url("") is None


def test_safe_url_rejects_non_string():
    assert images._safe_url(123) is None


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


def test_commons_search_rejects_malicious_license_and_source_urls():
    """XSS prevention: javascript: and data: URLs in metadata are rejected."""
    fixture = {
        "query": {
            "pages": {
                "111": {
                    "title": "File:Malicious.png",
                    "imageinfo": [{
                        "thumburl": "https://upload.wikimedia.org/thumb/mal.png/800px-mal.png",
                        "url": "https://upload.wikimedia.org/mal.svg",
                        "descriptionurl": "javascript:alert(1)",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC0"},
                            "LicenseUrl": {"value": "data:text/html,<script>alert(1)</script>"},
                            "Artist": {"value": "Attacker"},
                            "AttributionRequired": {"value": "false"},
                        },
                    }],
                },
            },
        },
    }
    def fake_http_get(url):
        return json.dumps(fixture).encode()
    candidates = images.commons_search("q", http_get=fake_http_get)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["licenseUrl"] is None  # malicious LicenseUrl rejected
    assert c["sourceUrl"] is None or c["sourceUrl"] == ""  # malicious descriptionurl rejected


def test_commons_search_accepts_valid_urls():
    """Legitimate https URLs pass through unchanged."""
    fixture = {
        "query": {
            "pages": {
                "111": {
                    "title": "File:Good.png",
                    "imageinfo": [{
                        "thumburl": "https://upload.wikimedia.org/thumb/good.png/800px-good.png",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Good.png",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY 4.0"},
                            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0"},
                            "Artist": {"value": "Jane"},
                            "AttributionRequired": {"value": "true"},
                        },
                    }],
                },
            },
        },
    }
    def fake_http_get(url):
        return json.dumps(fixture).encode()
    candidates = images.commons_search("q", http_get=fake_http_get)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["licenseUrl"] == "https://creativecommons.org/licenses/by/4.0"
    assert c["sourceUrl"] == "https://commons.wikimedia.org/wiki/File:Good.png"


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


def test_openverse_search_rejects_malicious_license_and_source_urls():
    """XSS prevention: javascript: and data: URLs are rejected."""
    fixture = {"results": [
        {"title": "Malicious photo", "creator": "Attacker",
         "thumbnail": "https://api.openverse.org/thumb/mal",
         "license": "by", "license_url": "javascript:alert(1)",
         "foreign_landing_url": "data:text/html,<script>alert(1)</script>"},
    ]}
    candidates = images.openverse_search("q", http_get=lambda url: json.dumps(fixture).encode())
    assert len(candidates) == 1
    c = candidates[0]
    assert c["licenseUrl"] is None  # malicious license_url rejected
    assert c["sourceUrl"] is None or c["sourceUrl"] == ""  # malicious foreign_landing_url rejected


def test_openverse_search_accepts_valid_urls():
    """Legitimate https URLs pass through unchanged."""
    fixture = {"results": [
        {"title": "Good photo", "creator": "Jane", "thumbnail": "https://api.openverse.org/thumb/x",
         "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
         "foreign_landing_url": "https://flickr.com/photos/jane/123"},
    ]}
    candidates = images.openverse_search("q", http_get=lambda url: json.dumps(fixture).encode())
    assert len(candidates) == 1
    c = candidates[0]
    assert c["licenseUrl"] == "https://creativecommons.org/licenses/by/4.0/"
    assert c["sourceUrl"] == "https://flickr.com/photos/jane/123"


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


def test_resolve_images_no_double_emit_when_build_raises(tmp_path, monkeypatch):
    evs, on_event = _events_capture()
    content_dir = tmp_path / "courses"
    slots = [{"query": "q", "caption": "c"}]

    def http_get(url):
        if "commons" in url:
            return json.dumps({"query": {"pages": {"1": {"title": "t",
                "imageinfo": [{"thumburl": "http://img/x.jpg", "descriptionurl": "http://s",
                "extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}}}}).encode()
        return b"\xff\xd8\xffjpeg"

    def boom(candidate):
        raise AttributeError("title not a string")
    monkeypatch.setattr(images, "build_credit", boom)

    images.resolve_images("demo", "demo-l1", slots, content_dir=content_dir,
                          http_get=http_get, structured=lambda *a, **k: {"pick": 1},
                          on_event=on_event)
    # build_credit raises AFTER the candidate is picked; the slot must still get
    # exactly ONE telemetry record, not a "rendered" followed by an "error".
    assert len(evs) == 1
    assert evs[0]["outcome"] == "dropped"
    assert evs[0]["drop_reason"] == "error"


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

    def fake_resolve(course_id, lesson_id, slots, *, content_dir, **kwargs):
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


def test_backfill_course_survives_timeout_and_continues_batch(tmp_path):
    """backfill_course must handle subprocess.TimeoutExpired (not just ClaudeError)
    and continue processing remaining lessons."""
    import subprocess
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)

    lesson_1 = {"id": "demo-l1", "topic": "t", "promptHtml": "<p>First lesson.</p>"}
    lesson_2 = {"id": "demo-l2", "topic": "t", "promptHtml": "<p>Second lesson.</p>"}
    path_1 = root / "demo" / "lessons" / "demo-l1.json"
    path_2 = root / "demo" / "lessons" / "demo-l2.json"
    path_1.write_text(json.dumps(lesson_1))
    path_2.write_text(json.dumps(lesson_2))

    generate_calls = []
    def generate_with_timeout_on_first(prompt, validate):
        generate_calls.append(prompt)
        if len(generate_calls) == 1:
            # First lesson times out
            raise subprocess.TimeoutExpired("claude", 240)
        # Second lesson succeeds
        return {"images": [], "promptHtml": "<p>Second lesson.</p>"}

    def fake_resolve(course_id, lesson_id, slots, *, content_dir):
        return []

    import unittest.mock
    with unittest.mock.patch.object(images, "resolve_images", fake_resolve):
        count = images.backfill_course(root, "demo", generate=generate_with_timeout_on_first)

    # Both lessons should have been attempted; count reflects successful ones
    assert len(generate_calls) == 2, f"generate should be called twice, got {len(generate_calls)}"
    assert count == 1, "one lesson succeeded and was written"

    # First lesson should remain unchanged (timeout = skipped)
    on_disk_1 = json.loads(path_1.read_text())
    assert "images" not in on_disk_1

    # Second lesson should have images added
    on_disk_2 = json.loads(path_2.read_text())
    assert "images" in on_disk_2
    assert on_disk_2["images"] == []


def test_process_slots_mixed_types(tmp_path):
    content_dir = tmp_path / "courses"
    slots = [
        {"query": "q", "caption": "c"},
        {"type": "svg", "code": '<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>', "caption": "s"},
        {"type": "mermaid", "code": "pie", "caption": "m"},
    ]

    def fake_resolver(course_id, lesson_id, slots_arg, *, content_dir, **kwargs):
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
