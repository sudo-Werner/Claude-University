# tests/test_objectives.py
from backend import objectives


def _wire_course(cid="demo"):
    """A compiled course in WIRE shape: embedded objectives, no registry."""
    return {
        "schemaVersion": 3, "id": cid, "title": "T",
        "outcomes": [{"text": "Course O", "bloom": "analyze", "knowledge": "conceptual"}],
        "modules": [{
            "id": "m1", "title": "M1",
            "outcomes": [{"text": "Module O", "bloom": "apply", "knowledge": "conceptual"}],
            "lessons": [
                {"id": f"{cid}-l1", "title": "L1", "estMinutes": 30, "prereqs": [],
                 "objectives": [{"text": "Calc A", "bloom": "apply", "knowledge": "procedural"},
                                {"text": "Calc B", "bloom": "apply", "knowledge": "procedural"}]},
                {"id": f"{cid}-l2", "title": "L2", "estMinutes": 40, "prereqs": [f"{cid}-l1"],
                 "objectives": [{"text": "Compare C", "bloom": "analyze", "knowledge": "conceptual"}]},
            ],
        }],
    }


def test_build_registry_lifts_objectives_and_assigns_ids():
    disk = objectives.build_registry(_wire_course())
    assert disk["schemaVersion"] == 3
    # registry has one entry per lesson-objective, ids in flat order
    assert [o["id"] for o in disk["objectives"]] == ["demo-o1", "demo-o2", "demo-o3"]
    assert disk["objectives"][0] == {"id": "demo-o1", "text": "Calc A",
                                     "bloom": "apply", "knowledge": "procedural"}
    lessons = [l for m in disk["modules"] for l in m["lessons"]]
    assert lessons[0]["objectiveIds"] == ["demo-o1", "demo-o2"]
    assert lessons[1]["objectiveIds"] == ["demo-o3"]
    # embedded objectives are gone from the disk shape
    assert "objectives" not in lessons[0]
    # course/module outcomes are untouched
    assert disk["outcomes"][0]["text"] == "Course O"
    assert disk["modules"][0]["outcomes"][0]["text"] == "Module O"


def test_build_registry_is_non_destructive():
    wire = _wire_course()
    objectives.build_registry(wire)
    assert wire["modules"][0]["lessons"][0]["objectives"][0]["text"] == "Calc A"
    assert "objectives" not in wire  # input never gained a registry


def test_for_lesson_resolves_refs_and_falls_back_to_embedded():
    disk = objectives.build_registry(_wire_course())
    l1 = disk["modules"][0]["lessons"][0]
    assert [o["text"] for o in objectives.for_lesson(disk, l1)] == ["Calc A", "Calc B"]
    # embedded (v2) lesson with no registry: fallback returns the embedded list
    v2_lesson = {"objectives": [{"text": "X", "bloom": "apply", "knowledge": "procedural"}]}
    assert objectives.for_lesson({}, v2_lesson) == v2_lesson["objectives"]
    # nothing present -> empty
    assert objectives.for_lesson({}, {"id": "z"}) == []


def test_resolved_manifest_hydrates_embedded_objectives():
    disk = objectives.build_registry(_wire_course())
    wire = objectives.resolved_manifest(disk)
    l1 = wire["modules"][0]["lessons"][0]
    assert [o["text"] for o in l1["objectives"]] == ["Calc A", "Calc B"]
    # each hydrated objective carries its id (join key available to consumers)
    assert l1["objectives"][0]["id"] == "demo-o1"


def test_build_registry_preserves_existing_ids_and_mints_above_max():
    # a course already carrying an id on one objective (retained across a revise)
    wire = _wire_course()
    wire["modules"][0]["lessons"][0]["objectives"][0]["id"] = "demo-o5"
    disk = objectives.build_registry(wire)
    ids = [o["id"] for o in disk["objectives"]]
    assert ids[0] == "demo-o5"           # kept
    assert ids[1] == "demo-o6"           # minted above the max (5)
    assert ids[2] == "demo-o7"


def test_build_registry_is_idempotent_on_disk_input():
    disk1 = objectives.build_registry(_wire_course())
    disk2 = objectives.build_registry(disk1)   # feeding disk (refs) back in
    assert [o["id"] for o in disk1["objectives"]] == [o["id"] for o in disk2["objectives"]]
    assert disk2["modules"][0]["lessons"][0]["objectiveIds"] == ["demo-o1", "demo-o2"]
