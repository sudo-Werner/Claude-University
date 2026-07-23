def test_root_serves_platform_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!doctype html" in resp.data.lower()


def test_root_html_wires_up_pwa_install(client):
    body = client.get("/").get_data(as_text=True)
    assert 'rel="manifest" href="/manifest.json"' in body
    assert 'name="theme-color"' in body
    # SW registration moved out of the inline page script into /src/boot.js
    # (keeps platform.html free of an inline script body for CSP purposes).
    boot = client.get("/src/boot.js").get_data(as_text=True)
    assert 'navigator.serviceWorker.register("/sw.js")' in boot


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


def test_manifest_served_as_json_with_required_pwa_fields():
    from backend.app import create_app
    client = create_app().test_client()
    resp = client.get("/manifest.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "Claude University"
    assert body["display"] == "standalone"
    assert body["start_url"] == "/"
    sizes = {icon["sizes"] for icon in body["icons"]}
    assert {"192x192", "512x512"} <= sizes


def test_service_worker_served_at_root_scope_never_caches_api():
    from backend.app import create_app
    client = create_app().test_client()
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "/api/" in body   # the exclusion check must reference the API prefix


def test_icons_served(client):
    resp = client.get("/icons/icon-192.png")
    assert resp.status_code == 200
    assert resp.content_type == "image/png"
    resp2 = client.get("/icons/icon-512.png")
    assert resp2.status_code == 200


def test_icons_404_outside_the_allowed_filenames(client):
    assert client.get("/icons/../app.py").status_code == 404
    assert client.get("/icons/not-a-real-icon.png").status_code == 404


def test_platform_html_has_no_inline_script_body():
    from pathlib import Path
    html = Path("frontend/platform.html").read_text()
    assert 'src="/src/boot.js"' in html
    assert "import { init }" not in html  # boot logic moved out of the page
