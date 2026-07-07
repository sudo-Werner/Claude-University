import json
from backend import migrate_courses, compiler, generation

OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def _write(dirp, cid, manifest):
    (dirp / cid).mkdir(parents=True)
    (dirp / cid / "course.json").write_text(json.dumps(manifest))

def test_migrate_enriches_legacy_and_skips_current(tmp_path, monkeypatch):
    _write(tmp_path, "legacy", {"id": "legacy", "title": "Legacy", "subtitle": "", "brief": "b",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "legacy-l1", "title": "A"}]}]})
    _write(tmp_path, "current", {"id": "current", "schemaVersion": 2, "title": "Cur", "modules": []})

    def fake_enrich(manifest, **kw):
        return {"schemaVersion": 2, "id": manifest["id"], "title": manifest["title"], "subtitle": "",
                "brief": "b", "learnerBrief": {"goal": "g"},
                "level": {"code": "bachelor-y1", "label": "Bachelor Year 1-equivalent"},
                "targetHours": 120, "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": "legacy-l1", "title": "A", "estMinutes": 90, "objectives": [OBJ], "prereqs": []}]}]}
    monkeypatch.setattr(compiler, "enrich_course", fake_enrich)

    result = migrate_courses.migrate(tmp_path)
    assert result == {"enriched": 1, "clean": 1, "errors": 0}
    on_disk = json.loads((tmp_path / "legacy" / "course.json").read_text())
    assert on_disk["schemaVersion"] == 2 and on_disk["id"] == "legacy"
    assert generation.valid_compiled_course(on_disk)

def test_migrate_one_failure_does_not_abort_batch(tmp_path, monkeypatch):
    _write(tmp_path, "aaa", {"id": "aaa", "title": "A", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "aaa-l1", "title": "x"}]}]})
    _write(tmp_path, "bbb", {"id": "bbb", "title": "B", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "bbb-l1", "title": "y"}]}]})
    def flaky(manifest, **kw):
        if manifest["id"] == "aaa":
            raise RuntimeError("boom")
        return {"schemaVersion": 2, "id": "bbb", "title": "B", "subtitle": "", "brief": "b",
                "learnerBrief": {"goal": "g"}, "level": {"code": "foundation", "label": "Foundation"},
                "targetHours": 100, "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": "bbb-l1", "title": "y", "estMinutes": 60, "objectives": [OBJ], "prereqs": []}]}]}
    monkeypatch.setattr(compiler, "enrich_course", flaky)
    result = migrate_courses.migrate(tmp_path)
    assert result == {"enriched": 1, "clean": 0, "errors": 1}
    assert json.loads((tmp_path / "bbb" / "course.json").read_text())["schemaVersion"] == 2
    assert "schemaVersion" not in json.loads((tmp_path / "aaa" / "course.json").read_text())

def test_migrate_write_failure_does_not_abort_batch(tmp_path, monkeypatch):
    _write(tmp_path, "aaa", {"id": "aaa", "title": "A", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "aaa-l1", "title": "x"}]}]})
    _write(tmp_path, "bbb", {"id": "bbb", "title": "B", "modules": [
        {"id": "m1", "title": "M", "lessons": [{"id": "bbb-l1", "title": "y"}]}]})
    def valid_enrich(manifest, **kw):
        return {"schemaVersion": 2, "id": manifest["id"], "title": manifest["title"], "subtitle": "",
                "brief": "b", "learnerBrief": {"goal": "g"},
                "level": {"code": "bachelor-y1", "label": "Bachelor Year 1-equivalent"},
                "targetHours": 120, "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": f"{manifest['id']}-l1", "title": "X", "estMinutes": 90, "objectives": [OBJ], "prereqs": []}]}]}
    monkeypatch.setattr(compiler, "enrich_course", valid_enrich)

    write_calls = []
    original_write = migrate_courses._atomic_write
    def flaky_write(path, data):
        write_calls.append(str(path))
        if "aaa" in str(path):
            raise OSError("disk full")
        return original_write(path, data)
    monkeypatch.setattr(migrate_courses, "_atomic_write", flaky_write)

    result = migrate_courses.migrate(tmp_path)
    assert result["enriched"] >= 1 and result["errors"] >= 1
    assert json.loads((tmp_path / "bbb" / "course.json").read_text())["schemaVersion"] == 2
    assert "schemaVersion" not in json.loads((tmp_path / "aaa" / "course.json").read_text())
