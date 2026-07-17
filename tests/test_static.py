def test_root_serves_platform_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!doctype html" in resp.data.lower()


def test_src_module_served(client):
    resp = client.get("/src/sync.js")
    assert resp.status_code == 200
    assert b"export" in resp.data


def test_styles_served(client):
    resp = client.get("/styles.css")
    assert resp.status_code == 200
    assert b".card" in resp.data


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
