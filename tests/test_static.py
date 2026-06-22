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
