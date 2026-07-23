import json
from backend import migrate_objective_ids, objectives, generation


OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}


def _v2_course(cid):
    return {"schemaVersion": 2, "id": cid, "title": "C", "subtitle": "",
            "level": {"code": "bachelor-y1", "label": "B"}, "targetHours": 5, "skills": ["s"],
            "outcomes": [OBJ], "groundingSources": [],
            "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                {"id": f"{cid}-l1", "title": "L1", "estMinutes": 30, "objectives": [OBJ, OBJ], "prereqs": []},
                {"id": f"{cid}-l2", "title": "L2", "estMinutes": 30, "objectives": [OBJ], "prereqs": []},
            ]}]}


def _write(root, cid, manifest):
    d = root / cid
    (d / "lessons").mkdir(parents=True)
    (d / "course.json").write_text(json.dumps(manifest))
    return d


def test_migrate_stamps_ids_and_builds_registry(tmp_path):
    _write(tmp_path, "demo", _v2_course("demo"))
    result = migrate_objective_ids.migrate(tmp_path, now="20260722T210000Z")
    assert result == {"migrated": 1, "clean": 0, "errors": 0}
    disk = json.loads((tmp_path / "demo" / "course.json").read_text())
    assert disk["schemaVersion"] == 3
    assert [o["id"] for o in disk["objectives"]] == ["demo-o1", "demo-o2", "demo-o3"]
    lessons = disk["modules"][0]["lessons"]
    assert lessons[0]["objectiveIds"] == ["demo-o1", "demo-o2"]
    assert lessons[1]["objectiveIds"] == ["demo-o3"]
    assert "objectives" not in lessons[0]
    # every objective text is preserved (lossless)
    assert all(o["text"] == "Calculate X" for o in disk["objectives"])


def test_migrate_writes_backup_sidecar(tmp_path):
    _write(tmp_path, "demo", _v2_course("demo"))
    migrate_objective_ids.migrate(tmp_path, now="20260722T210000Z")
    backup = tmp_path / "demo" / "course.json.pre-objid-20260722T210000Z"
    assert backup.exists()
    assert json.loads(backup.read_text())["schemaVersion"] == 2   # original preserved


def test_migrate_is_idempotent(tmp_path):
    _write(tmp_path, "demo", _v2_course("demo"))
    migrate_objective_ids.migrate(tmp_path, now="20260722T210000Z")
    result = migrate_objective_ids.migrate(tmp_path, now="20260722T210500Z")
    assert result == {"migrated": 0, "clean": 1, "errors": 0}
    # second run made no second backup
    assert not (tmp_path / "demo" / "course.json.pre-objid-20260722T210500Z").exists()


def test_migrate_result_validates_as_compiled_course(tmp_path):
    _write(tmp_path, "demo", _v2_course("demo"))
    migrate_objective_ids.migrate(tmp_path, now="20260722T210000Z")
    disk = json.loads((tmp_path / "demo" / "course.json").read_text())
    # resolved back to wire shape, it is still a valid compiled course
    assert generation.valid_compiled_course(objectives.resolved_manifest(disk))


def test_migrate_batch_continues_past_broken_courses(tmp_path):
    # sorts BEFORE "demo" -- proves a broken course earlier in the batch does not
    # abort processing of a valid course later in the batch.
    bad_json_dir = tmp_path / "aaa-bad-json"
    bad_json_dir.mkdir()
    (bad_json_dir / "course.json").write_text("{not valid json")
    bad_json_before = (bad_json_dir / "course.json").read_bytes()

    _write(tmp_path, "demo", _v2_course("demo"))

    (tmp_path / "no-manifest-dir").mkdir()  # no course.json at all -> silently skipped

    bad_version_dir = tmp_path / "zzz-bad-version"
    bad_version_dir.mkdir()
    bad_version_manifest = _v2_course("zzz-bad-version")
    bad_version_manifest["schemaVersion"] = "3"  # non-numeric -> must error, not skip-as-clean
    (bad_version_dir / "course.json").write_text(json.dumps(bad_version_manifest))
    bad_version_before = (bad_version_dir / "course.json").read_bytes()

    result = migrate_objective_ids.migrate(tmp_path, now="20260722T210000Z")
    assert result == {"migrated": 1, "clean": 0, "errors": 2}

    # the valid course was actually migrated, with its backup sidecar
    disk = json.loads((tmp_path / "demo" / "course.json").read_text())
    assert disk["schemaVersion"] == 3
    assert (tmp_path / "demo" / "course.json.pre-objid-20260722T210000Z").exists()

    # broken courses were never touched: byte-identical to before, no backup sidecar
    assert (bad_json_dir / "course.json").read_bytes() == bad_json_before
    assert not list(bad_json_dir.glob("course.json.pre-objid-*"))
    assert (bad_version_dir / "course.json").read_bytes() == bad_version_before
    assert not list(bad_version_dir.glob("course.json.pre-objid-*"))
