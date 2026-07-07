from backend import compiler, generation, claude_client

OUTLINE = {"title": "Intro ML", "subtitle": "hands-on",
           "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
           "targetHours": 130, "groundingSources": [{"title": "MIT 6.036", "url": "https://mit.edu/6036"}],
           "modules": [{"id": "m1", "title": "Basics",
                        "lessons": [{"id": "l1", "title": "Vectors", "estMinutes": 90}]}]}

def test_valid_outline_accepts_and_rejects():
    assert compiler.valid_outline(OUTLINE)
    bad = {**OUTLINE, "level": {"code": "phd", "label": "x"}}
    assert not compiler.valid_outline(bad)
    bad2 = {**OUTLINE, "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "l1", "title": "t", "estMinutes": 0}]}]}
    assert not compiler.valid_outline(bad2)

def test_grounded_outline_keeps_only_retrieved_sources():
    captured = [{"title": "MIT 6.036", "url": "https://mit.edu/6036"}]
    gen = lambda prompt, validate: (OUTLINE, captured)
    outline, sources = compiler._grounded_outline({"goal": "build models"}, generate_sourced=gen)
    assert outline["title"] == "Intro ML"
    assert [s["url"] for s in sources] == ["https://mit.edu/6036"]  # trust guarantee kept it

def test_grounded_outline_drops_uncaptured_source():
    gen = lambda prompt, validate: (OUTLINE, [])  # nothing actually retrieved
    _, sources = compiler._grounded_outline({"goal": "g"}, generate_sourced=gen)
    assert sources == []


OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def test_merge_objectives_keeps_outline_ids_and_filters_forward_prereqs():
    outline = {"modules": [{"id": "m1", "title": "Basics", "lessons": [
        {"id": "l1", "title": "Vectors", "estMinutes": 90},
        {"id": "l2", "title": "Matrices", "estMinutes": 60}]}]}
    # model echoed DIFFERENT ids and a forward edge; merge must fix both by position
    result = {"outcomes": [OBJ], "skills": ["do X"], "modules": [{"id": "x", "title": "renamed",
        "outcomes": [OBJ], "lessons": [
            {"id": "a", "title": "?", "objectives": [OBJ], "prereqs": ["b"]},   # forward -> dropped
            {"id": "b", "title": "?", "objectives": [OBJ], "prereqs": ["a"]}]}]}  # a==l1 -> l1
    enriched = compiler._merge_objectives(outline, result)
    lessons = enriched["modules"][0]["lessons"]
    assert [l["id"] for l in lessons] == ["l1", "l2"]           # outline ids win
    assert lessons[0]["prereqs"] == []                           # forward edge filtered
    assert lessons[1]["prereqs"] == ["l1"]                       # remapped a->l1
    assert enriched["modules"][0]["title"] == "Basics"          # outline title wins
    assert generation.valid_prereq_graph(enriched["modules"])

def test_objectives_and_graph_batches_per_module_and_rolls_up():
    # two modules -> one objectives call per module + one course-level roll-up call; the second
    # module's call must be told l1 is an earlier lesson so a cross-module prereq survives.
    outline = {"title": "Course", "modules": [
        {"id": "m1", "title": "M1", "lessons": [{"id": "l1", "title": "a", "estMinutes": 60}]},
        {"id": "m2", "title": "M2", "lessons": [{"id": "l2", "title": "b", "estMinutes": 60}]}]}
    m1_res = {"outcomes": [OBJ], "lessons": [{"id": "l1", "title": "a", "objectives": [OBJ], "prereqs": []}]}
    m2_res = {"outcomes": [OBJ], "lessons": [{"id": "l2", "title": "b", "objectives": [OBJ], "prereqs": ["l1"]}]}
    rollup = {"outcomes": [OBJ], "skills": ["s"]}
    prompts, calls = [], iter([m1_res, m2_res, rollup])
    def verify(p, v):
        prompts.append(p)
        return next(calls)
    got = compiler._objectives_and_graph(outline, verify=verify)
    assert len(prompts) == 3                                   # per-module + roll-up, not one big call
    assert "l1" in prompts[1]                                  # module 2 sees the earlier lesson id
    assert compiler.valid_objectives_result(got)              # assembled shape matches whole-course contract
    assert got["skills"] == ["s"]
    assert [l["id"] for m in got["modules"] for l in m["lessons"]] == ["l1", "l2"]
    assert got["modules"][1]["lessons"][0]["prereqs"] == ["l1"]  # cross-module prereq preserved


def test_valid_module_objectives_and_rollup_gate_their_shapes():
    good_mod = {"outcomes": [OBJ], "lessons": [{"id": "l1", "title": "t", "objectives": [OBJ], "prereqs": []}]}
    assert compiler.valid_module_objectives(good_mod)
    assert not compiler.valid_module_objectives({"outcomes": [OBJ], "lessons": []})           # no lessons
    assert not compiler.valid_module_objectives({"lessons": [good_mod["lessons"][0]]})        # no outcomes
    assert compiler.valid_course_rollup({"outcomes": [OBJ], "skills": ["s"]})
    assert not compiler.valid_course_rollup({"outcomes": [OBJ], "skills": []})                # no skills


ENRICHED = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
    "outcomes": [OBJ], "lessons": [{"id": "l1", "title": "t", "estMinutes": 60, "objectives": [OBJ], "prereqs": []}]}]}

def test_accuracy_sweep_unchanged_when_audit_clean():
    gen = lambda prompt, validate: ({"ok": True}, [])
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen) == ENRICHED

def test_accuracy_sweep_applies_correction_when_flagged():
    corrected = {"outcomes": [OBJ], "skills": ["s2"], "modules": ENRICHED["modules"]}
    calls = iter([({"ok": False, "issues": ["topic X is wrong"]}, []), (corrected, [])])
    gen = lambda prompt, validate: next(calls)
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen)["skills"] == ["s2"]

def test_accuracy_sweep_rejects_correction_that_changes_lesson_ids():
    # a correction that INVENTS a lesson passes valid_objectives_result but changes the id set;
    # it must be rejected so migration's id/structure preservation holds (regression: ML gained 3).
    added = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
        "outcomes": [OBJ], "lessons": [
            {"id": "l1", "title": "t", "estMinutes": 60, "objectives": [OBJ], "prereqs": []},
            {"id": "l2", "title": "invented", "estMinutes": 60, "objectives": [OBJ], "prereqs": []}]}]}
    calls = iter([({"ok": False, "issues": ["x"]}, []), (added, [])])
    gen = lambda prompt, validate: next(calls)
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen) == ENRICHED  # rejected -> fallback

def test_accuracy_sweep_falls_back_on_invalid_correction():
    bad = {"outcomes": [], "skills": [], "modules": []}  # fails valid_objectives_result
    calls = iter([({"ok": False, "issues": ["x"]}, []), (bad, [])])
    gen = lambda prompt, validate: next(calls)
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=gen) == ENRICHED

def test_accuracy_sweep_falls_back_on_error():
    def boom(prompt, validate):
        raise claude_client.ClaudeError("down")
    assert compiler._accuracy_sweep(ENRICHED, [], generate_sourced=boom) == ENRICHED


def test_assemble_contract_computes_hours_and_shape():
    outline = {"title": "Intro ML", "subtitle": "s",
               "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
               "modules": [{"id": "m1", "title": "M", "lessons": [
                   {"id": "l1", "title": "a", "estMinutes": 90},
                   {"id": "l2", "title": "b", "estMinutes": 150}]}]}
    enriched = {"outcomes": [OBJ], "skills": ["s"], "modules": [{"id": "m1", "title": "M",
        "outcomes": [OBJ], "lessons": [
            {"id": "l1", "title": "a", "estMinutes": 90, "objectives": [OBJ], "prereqs": []},
            {"id": "l2", "title": "b", "estMinutes": 150, "objectives": [OBJ], "prereqs": ["l1"]}]}]}
    c = compiler._assemble_contract({"goal": "build models", "desiredDepth": "deep"}, outline, enriched, [])
    assert c["schemaVersion"] == 2 and c["targetHours"] == 4          # round(240/60)
    assert "id" not in c and c["level"]["code"] == "bachelor-y2"
    assert generation.valid_compiled_course(c)
    assert "build models" in c["brief"]

def test_compile_course_runs_all_stages():
    outline = {"title": "Intro ML", "subtitle": "s",
               "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
               "groundingSources": [{"title": "MIT", "url": "https://mit.edu/x"}],
               "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "l1", "title": "a", "estMinutes": 120}]}]}
    module_res = {"outcomes": [OBJ], "lessons": [{"id": "l1", "title": "a", "objectives": [OBJ], "prereqs": []}]}
    rollup = {"outcomes": [OBJ], "skills": ["s"]}
    verify_calls = iter([module_res, rollup])                       # 1 module + roll-up
    captured = [{"title": "MIT", "url": "https://mit.edu/x"}]
    sourced_calls = iter([(outline, captured), ({"ok": True}, [])])  # outline, then sweep-audit
    gen_sourced = lambda p, v: next(sourced_calls)
    c = compiler.compile_course({"goal": "build"}, generate_sourced=gen_sourced, verify=lambda p, v: next(verify_calls))
    assert generation.valid_compiled_course(c)
    assert c["targetHours"] == 2 and [s["url"] for s in c["groundingSources"]] == ["https://mit.edu/x"]


LEGACY = {"id": "the-human-body", "title": "The Human Body", "subtitle": "engineer's view",
          "brief": "systems view of anatomy", "modules": [
              {"id": "m1", "title": "Cardio", "lessons": [
                  {"id": "the-human-body-l1", "title": "The Heart"},
                  {"id": "the-human-body-l2", "title": "Blood"}]}]}

def _enrich_gens():
    # 1st sourced call = enrich outline (model may echo junk ids; we ignore them);
    # 2nd sourced call = sweep audit -> clean
    outline_reply = {"title": "x", "subtitle": "y",
                     "level": {"code": "bachelor-y1", "label": "Bachelor Year 1-equivalent"},
                     "groundingSources": [], "modules": [{"id": "zz", "title": "zz", "lessons": [
                         {"id": "junk1", "title": "junk", "estMinutes": 80},
                         {"id": "junk2", "title": "junk", "estMinutes": 100}]}]}
    sourced = iter([(outline_reply, []), ({"ok": True}, [])])
    def next_sourced(p, v):
        try:
            return next(sourced)
        except StopIteration:
            raise AssertionError(
                "enrich_course made more web-grounded calls than this fixture provides "
                "(expected outline + one clean audit). A new sourced stage was likely added — "
                "append its canned reply to _enrich_gens.") from None
    # verify (structured) is now called per module then once for the course roll-up
    module_res = {"outcomes": [OBJ], "lessons": [
        {"id": "the-human-body-l1", "title": "The Heart", "objectives": [OBJ], "prereqs": []},
        {"id": "the-human-body-l2", "title": "Blood", "objectives": [OBJ], "prereqs": ["the-human-body-l1"]}]}
    rollup = {"outcomes": [OBJ], "skills": ["s"]}
    verify_calls = iter([module_res, rollup])
    def next_verify(p, v):
        try:
            return next(verify_calls)
        except StopIteration:
            raise AssertionError(
                "enrich_course made more structured calls than this fixture provides "
                "(expected one per module + one roll-up). Add a canned reply to _enrich_gens.") from None
    return next_sourced, next_verify

def test_enrich_course_preserves_ids_order_and_id():
    gs, vf = _enrich_gens()
    c = compiler.enrich_course(LEGACY, generate_sourced=gs, verify=vf)
    assert c["id"] == "the-human-body"
    flat = [l["id"] for m in c["modules"] for l in m["lessons"]]
    assert flat == ["the-human-body-l1", "the-human-body-l2"]     # existing ids + order preserved
    assert c["level"]["code"] == "bachelor-y1"
    assert generation.valid_compiled_course(c)

def test_enrich_course_is_idempotent_on_ids():
    gs, vf = _enrich_gens()
    once = compiler.enrich_course(LEGACY, generate_sourced=gs, verify=vf)
    gs2, vf2 = _enrich_gens()
    twice = compiler.enrich_course(once, generate_sourced=gs2, verify=vf2)
    assert [l["id"] for m in twice["modules"] for l in m["lessons"]] == \
           [l["id"] for m in once["modules"] for l in m["lessons"]]
