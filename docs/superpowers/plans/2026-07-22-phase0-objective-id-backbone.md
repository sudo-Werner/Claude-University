# Phase 0 — Objective-ID Backbone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every learning objective a stable id in a course-level registry (single source of truth), and route every objective-reader and objective-writer through one resolver — the data-model backbone that unblocks Phases 1–4 — with zero user-visible change.

**Architecture:** Objectives become first-class entities. On **disk** (schemaVersion 3) a course carries a course-level `objectives[]` registry of `{id, text, bloom, knowledge}`, and each lesson carries `objectiveIds[]` referencing it — no embedded lesson objectives (refs-canonical). On the **wire** (compile/revise output, API responses to the browser, the apply-revision request body) objectives stay embedded on each lesson exactly as today, so the frontend, the LLM stages, and the create/revise round-trip are unchanged. One new module, `backend/objectives.py`, is the single boundary: `build_registry` converts wire→disk (assigning/preserving ids), `resolved_manifest` converts disk→wire (hydrating embedded objectives for responses), and `for_lesson` is the read primitive every reader uses. Course/module `outcomes` are **not** part of the registry — they are course/module rollups, never id-joined to diagnosis/teaching/exams/mastery, so they stay embedded untouched.

**Tech Stack:** Python 3 / Flask backend (filesystem course store under `content/courses/<id>/course.json`, SQLite events), vanilla-JS frontend (pure string-builder views, no DOM tests). Backend tests: `pytest`. Frontend tests: `node --test`.

## Global Constraints

Every task's requirements implicitly include this section. Values copied from the spec (`docs/superpowers/specs/2026-07-22-objective-centric-redesign-design.md`) and the project charter.

- **No user-visible change.** Phase 0 is invisible to the learner; the app must render, generate, exam, revise, and score exactly as before. (spec §10)
- **Refs-canonical, single source of truth on disk.** Post-migration, objective *definitions* live only in `manifest.objectives[]`. No embedded lesson-objective copy is persisted anywhere. (spec §5, §12) — A frozen snapshot (e.g. `exam_result.weakSpots[].objectives` text, already historical) is a record, not a definition, and is left as-is.
- **Objective ids are stable and preserved across revisions.** Format `<courseId>-oN`, mirroring lesson ids `<courseId>-lN`. A retained lesson keeps its objectives' ids; a new lesson mints ids above the course max. (spec §3, §6, §11)
- **schemaVersion 3** for the new disk shape; the current gate is `== 2`.
- **Migration safety (HARD RULE — 2026-07-15 data-loss incident):** the migration is *deterministic* (no LLM regeneration), runs on a **copy of `content/` first**, writes a per-course pre-migration backup sidecar, is idempotent (skips already-v3), and is only run against the live Pi after the daily backup is confirmed by `restore_check.py`. NEVER `rsync --delete`. Additive only — never delete or rewrite existing event/mastery/streak/heatmap data.
- **The test suite stays green after every task.** Baseline: backend `pytest tests/ -q` (~905 `def test_`), frontend `cd frontend && node --test` (369 `test(`). The stale worktree copy at `.claude/worktrees/agent-ac9799766df31ca89/` is NOT canonical — ignore it.
- **No emojis. Explain the WHY in commit messages. Do not commit unless explicitly asked** (the human runs `git commit`).

## Key design decisions (please confirm at plan review)

These are technical trade-offs made from a firsthand read of the code; each faithfully serves the spec's intent but a couple refine its letter. Flagged so Werner can veto before execution.

1. **Registry = lesson objectives only.** Course `outcomes` and module `outcomes` stay embedded dicts, unchanged. They are rollup statements, never id-joined to any downstream system (verified: exams/capstone read them as text; nothing keys on them). Moving them would add cost with zero Phase-0 benefit.
2. **Resolve-at-boundary.** Disk is refs-canonical; the wire keeps the embedded shape. The **only** frontend change is the schemaVersion gate (app.js:478). Everything else the browser sees is unchanged because the manifest-serving route resolves refs→embedded in its response.
3. **Deterministic migration, not `enrich_course`.** The spec §10 says "via the enrich path," but `enrich_course` regenerates objective *content* via the LLM — a user-visible change that contradicts Phase 0. All 4 live courses are already schemaVersion 2 with embedded objectives (verified on the Pi: 90/74/90/66), so a pure deterministic id-stamp is correct and lossless.
4. **Objective-id preservation across revise reuses the existing wholesale copy.** `compiler.revise_course` already copies a retained lesson's objectives verbatim by lesson id (compiler.py:411-416); only *new* lessons get fresh objectives. So retained objectives keep their ids for free once we feed revise a resolved (id-bearing) manifest — no per-objective `keepId` in the prompt is needed (simpler than spec §11's sketch).
5. **Exams do not store `objectiveId` in Phase 0.** The blueprint *readers* cut over to the resolver (mandatory, or they break on v3 disk), but persisted exam questions keep only their `objectiveText` snapshot. Storing the id on questions is a Phase-4 join-enabler (weak-spot routing by id); adding it now would touch four persistence surfaces for no Phase-0 behavior change.
6. **Untouched in Phase 0:** `mastery.py`, `capstone.py`, `remediation.py`, `misconceptions.py`, `srs.py`, `events.py`, `db.py`. Verified they read no lesson-objective *definitions* (mastery/srs are lesson-keyed; capstone reads course/module outcomes; remediation reads frozen weakSpot strings; events carry no objective identity). Per-objective mastery is Phase 4.
7. **Transitional read-tolerance.** `objectives.for_lesson` returns whichever shape is present (refs if `objectiveIds`, else embedded `objectives`), so the app is correct during the deploy window between shipping the code and running the migration. This is a read primitive, not a persisted dual-store — post-migration nothing on disk is embedded.

## File structure

| File | New/modified | Responsibility |
|---|---|---|
| `backend/objectives.py` | **new** | The registry+resolver boundary: `objective_index`, `for_lesson`, `resolved_manifest`, `build_registry`, id-minting helpers. Pure functions, no I/O. |
| `backend/generation.py` | modify | `valid_compiled_course` accepts schemaVersion 3. |
| `backend/courses.py` | modify | `flatten_lessons` resolves via `objectives.for_lesson`; `write_course` and `apply_revision` build the registry for compiled courses. |
| `backend/exams.py` | modify | `module_blueprint` / `final_blueprint` read objectives via `objectives.for_lesson`. |
| `backend/app.py` | modify | `get_course` returns a resolved manifest; `post_course_revise` feeds a resolved manifest to `revise_course`. |
| `backend/compiler.py` | modify | `_assemble_contract` emits schemaVersion 3. |
| `backend/migrate_objective_ids.py` | **new** | Deterministic v2→v3 id-stamp migration with backup sidecar + idempotency. |
| `frontend/src/app.js` | modify | schemaVersion contract gate accepts 3. |
| `tests/test_objectives.py` | **new** | Unit tests for the resolver/builder. |
| `tests/test_migrate_objective_ids.py` | **new** | Migration tests. |
| existing test files | modify | Update fixtures/asserts to the v3 shape where the task changes behavior. |

**Task order guarantees a green suite after every task.** Foundation (T1) → gate widened to accept both versions (T2) → readers cut over, still green on v2 fixtures via fallback (T3, T4, T5) → writers produce v3 disk, readers already resolve it (T6) → producer version bump (T7) → migration script (T8) → frontend gate (T9).

---

### Task 1: The objective registry + resolver module

**Files:**
- Create: `backend/objectives.py`
- Test: `tests/test_objectives.py`

**Interfaces:**
- Produces (used by later tasks):
  - `objective_index(manifest) -> dict[str, dict]` — id → objective dict from `manifest["objectives"]`.
  - `for_lesson(manifest, lesson) -> list[dict]` — a lesson's objective dicts, from refs (v3) or embedded (v2/wire).
  - `resolved_manifest(manifest) -> dict` — disk→wire; every lesson gets embedded `objectives`. Non-destructive.
  - `build_registry(manifest) -> dict` — wire→disk; lifts objectives into `objectives[]`, sets `objectiveIds`, stamps schemaVersion 3, preserves valid existing ids. Non-destructive.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_objectives.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.objectives'`.

- [ ] **Step 3: Write the module**

```python
# backend/objectives.py
"""Objective registry + resolver (Phase 0 objective-id backbone).

Single source of truth for objective identity. On disk (schemaVersion 3) a course
carries a course-level `objectives[]` registry of {id, text, bloom, knowledge}, and each
lesson carries `objectiveIds[]` referencing it -- no embedded lesson objectives. This
module is the one resolver every objective-reader goes through and the one builder every
writer goes through.

Two shapes exist by design:
- WIRE (compile/revise output, API responses, apply-revision input): objectives are
  embedded on each lesson as lesson["objectives"], exactly as before, optionally carrying
  an id. This is what the frontend and the LLM stages see.
- DISK (persisted course.json, v3): the registry + objectiveIds refs.

build_registry converts WIRE -> DISK (assigning/preserving ids). resolved_manifest
converts DISK -> WIRE (hydrating lesson["objectives"] from the registry). for_lesson is
the read primitive: it returns a lesson's objective dicts from whichever shape is present,
so a reader works on both a migrated (v3) and a not-yet-migrated (v2) course during the
deploy window. Course/module `outcomes` are NOT part of the registry.
"""
import re

_OBJ_ID_RE = re.compile(r"-o(\d+)$")


def objective_index(manifest):
    """Map objective id -> objective dict, from the course-level registry."""
    out = {}
    for o in manifest.get("objectives", []) or []:
        if isinstance(o, dict) and isinstance(o.get("id"), str):
            out[o["id"]] = o
    return out


def for_lesson(manifest, lesson):
    """A lesson's objective dicts: resolved through the registry when the lesson carries
    objectiveIds (v3 disk), else the lesson's embedded objectives (v2/wire), else []."""
    ids = lesson.get("objectiveIds")
    if isinstance(ids, list):
        index = objective_index(manifest)
        return [index[i] for i in ids if i in index]
    embedded = lesson.get("objectives")
    if isinstance(embedded, list):
        return embedded
    return []


def resolved_manifest(manifest):
    """DISK -> WIRE: a copy where every lesson carries embedded `objectives` (hydrated from
    the registry), so the frontend and the LLM stages see the pre-registry shape. The input
    manifest is not mutated."""
    modules = []
    for m in manifest.get("modules", []):
        lessons = [{**l, "objectives": for_lesson(manifest, l)} for l in m.get("lessons", [])]
        modules.append({**m, "lessons": lessons})
    return {**manifest, "modules": modules}


def _max_objective_num(manifest):
    nums = []
    for oid in ([o.get("id", "") for o in manifest.get("objectives", []) or [] if isinstance(o, dict)]):
        mo = _OBJ_ID_RE.search(oid or "")
        if mo:
            nums.append(int(mo.group(1)))
    for m in manifest.get("modules", []):
        for l in m.get("lessons", []):
            for oid in l.get("objectiveIds", []) or []:
                mo = _OBJ_ID_RE.search(oid or "")
                if mo:
                    nums.append(int(mo.group(1)))
            for o in l.get("objectives", []) or []:
                mo = _OBJ_ID_RE.search(o.get("id", "") if isinstance(o, dict) else "")
                if mo:
                    nums.append(int(mo.group(1)))
    return max(nums) if nums else 0


def build_registry(manifest):
    """WIRE -> DISK: lift every lesson's objectives into a course-level `objectives[]`
    registry with stable ids, replace them with `objectiveIds` refs, and stamp
    schemaVersion 3. An objective already carrying a valid, unused `<courseId>-oN` id keeps
    it (id preservation across revisions); a new one is minted above the current max. Reads
    each lesson via `for_lesson`, so it is idempotent on disk-shape input. Course/module
    `outcomes` are left untouched. The input manifest is not mutated."""
    course_id = manifest.get("id", "")
    counter = _max_objective_num(manifest)
    registry, used, modules = [], set(), []
    for m in manifest.get("modules", []):
        lessons = []
        for l in m.get("lessons", []):
            ids = []
            for o in for_lesson(manifest, l):
                if not isinstance(o, dict):
                    continue
                oid = o.get("id")
                if not (isinstance(oid, str) and _OBJ_ID_RE.search(oid) and oid not in used):
                    counter += 1
                    oid = f"{course_id}-o{counter}"
                used.add(oid)
                registry.append({"id": oid, "text": o.get("text", ""),
                                 "bloom": o.get("bloom", ""), "knowledge": o.get("knowledge", "")})
                ids.append(oid)
            new_l = {k: v for k, v in l.items() if k != "objectives"}
            new_l["objectiveIds"] = ids
            lessons.append(new_l)
        modules.append({**m, "lessons": lessons})
    return {**manifest, "schemaVersion": 3, "objectives": registry, "modules": modules}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_objectives.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full backend suite (no regressions — nothing imports the new module yet)**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, same count as baseline plus the 6 new tests.

- [ ] **Step 6: Commit**

```bash
git add backend/objectives.py tests/test_objectives.py
git commit -m "feat(objectives): registry+resolver module for objective-id backbone"
```

---

### Task 2: Accept schemaVersion 3 in the compiled-course validator

**Files:**
- Modify: `backend/generation.py:153` (inside `valid_compiled_course`)
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `generation.valid_compiled_course` accepts a wire course with `schemaVersion` 2 **or** 3 (both are valid compiled-course proposals; the wire shape is identical, only the version differs). Rejects other values.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_generation.py` (near the existing `valid_compiled_course` tests around line 1478):

```python
def test_valid_compiled_course_accepts_v2_and_v3_rejects_others():
    c = _compiled()
    c["schemaVersion"] = 2
    assert generation.valid_compiled_course(c)
    c["schemaVersion"] = 3
    assert generation.valid_compiled_course(c)
    c["schemaVersion"] = 1
    assert not generation.valid_compiled_course(c)
    c["schemaVersion"] = 4
    assert not generation.valid_compiled_course(c)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_generation.py::test_valid_compiled_course_accepts_v2_and_v3_rejects_others -v`
Expected: FAIL on the `schemaVersion = 3` assertion (current gate is `!= 2`).

- [ ] **Step 3: Widen the gate**

In `backend/generation.py`, `valid_compiled_course` (line 152-153), change:

```python
def valid_compiled_course(obj):
    if not isinstance(obj, dict) or obj.get("schemaVersion") not in (2, 3):
        return False
```

(Only the `schemaVersion` check changes; the rest of the function — which validates embedded `outcomes`/`objectives`, i.e. the wire shape — is unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_generation.py -q`
Expected: PASS (including the existing `schemaVersion == 1` rejection test at line 1490).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(generation): accept schemaVersion 3 in valid_compiled_course"
```

---

### Task 3: `flatten_lessons` resolves objectives through the registry

**Files:**
- Modify: `backend/courses.py:31-41` (`flatten_lessons`)
- Test: `tests/test_courses.py`

**Interfaces:**
- Consumes: `objectives.for_lesson` (Task 1).
- Produces: `courses.flatten_lessons(manifest)` returns `{id, title, moduleTitle, objectives}` where `objectives` is resolved — refs on a v3 manifest, embedded on a v2 manifest. Downstream consumers (`review_items` via `lesson_meta`, `course_progress.nextLesson`) are unaffected in shape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_courses.py` (alongside `test_flatten_lessons_includes_objectives` at ~198):

```python
def test_flatten_lessons_resolves_registry_refs():
    from backend import objectives
    OBJ = {"text": "Calculate the result", "bloom": "apply", "knowledge": "procedural"}
    wire = {
        "schemaVersion": 3, "id": "demo", "title": "T",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "demo-l1", "title": "L1", "estMinutes": 30, "prereqs": [], "objectives": [OBJ]},
        ]}],
    }
    disk = objectives.build_registry(wire)   # refs shape, no embedded objectives
    flat = courses.flatten_lessons(disk)
    assert flat[0]["objectives"][0]["text"] == "Calculate the result"
    assert flat[0]["objectives"][0]["id"] == "demo-o1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_courses.py::test_flatten_lessons_resolves_registry_refs -v`
Expected: FAIL — `flat[0]["objectives"]` is `[]` (current code reads `lesson.get("objectives", [])`, which is absent on the disk shape).

- [ ] **Step 3: Route through the resolver**

In `backend/courses.py`, add the import at the top (with the existing `from backend import fsutil, spine`):

```python
from backend import fsutil, objectives, spine
```

Then change `flatten_lessons` (line 31-41):

```python
def flatten_lessons(manifest):
    out = []
    for module in manifest.get("modules", []):
        for lesson in module.get("lessons", []):
            out.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "moduleTitle": module["title"],
                "objectives": objectives.for_lesson(manifest, lesson),
            })
    return out
```

- [ ] **Step 4: Run to verify it passes (and no regression)**

Run: `.venv/bin/python -m pytest tests/test_courses.py tests/test_review_items.py -q`
Expected: PASS. The existing `test_flatten_lessons_includes_objectives` (embedded fixture) still passes via the `for_lesson` fallback.

- [ ] **Step 5: Confirm no circular import**

Run: `.venv/bin/python -c "import backend.courses, backend.objectives"`
Expected: no error. (`objectives.py` imports only `re`, so `courses -> objectives` is safe.)

- [ ] **Step 6: Commit**

```bash
git add backend/courses.py tests/test_courses.py
git commit -m "feat(courses): flatten_lessons resolves objectives via the registry"
```

---

### Task 4: Exam blueprints read objectives through the resolver

**Files:**
- Modify: `backend/exams.py` — `module_blueprint` (line ~48) and `final_blueprint` (line ~74), the two `lesson.get("objectives", [])` reads.
- Test: `tests/test_exams.py`

**Interfaces:**
- Consumes: `objectives.for_lesson` (Task 1).
- Produces: exam blueprints resolve each lesson's objectives from the registry (v3) or embedded (v2). `_slot`, `finalize_exam`, `client_view`, `grade_exam`, `_weak_spots` are **unchanged** — the persisted `objectiveText` snapshot stays exactly as today (decision #5).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_exams.py` (the module fixture is `_manifest()` at line 6):

```python
def test_module_blueprint_resolves_registry_refs():
    from backend import objectives, exams
    m = objectives.build_registry(_manifest())   # v3 disk: lessons have objectiveIds
    slots = exams.blueprint(m, "m1")
    # blueprint still yields slots with objectiveText resolved from the registry
    assert slots and all(s["objectiveText"] for s in slots)
    assert any(s["objectiveText"] == "o1a" for s in slots)
```

(Adjust `"o1a"` to whatever the first lesson's first objective text is in `_manifest()` — per the inventory it is `obj("o1a", "remember")`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_exams.py::test_module_blueprint_resolves_registry_refs -v`
Expected: FAIL — with refs, `lesson.get("objectives", [])` is empty, so every lesson falls back to `_fallback_objective` and no slot carries `"o1a"`.

- [ ] **Step 3: Route both blueprints through the resolver**

In `backend/exams.py`, add to the imports (it already `from backend import ... courses ...` — add `objectives`):

```python
from backend import courses, events, generation, objectives
```

(Match the existing import line; add `objectives` to it.)

In `module_blueprint`, change the read (currently `objs = [o for o in lesson.get("objectives", []) or [] ...]`):

```python
        objs = [o for o in objectives.for_lesson(manifest, lesson)
                if isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip()]
```

In `final_blueprint`, change the inner loop (currently `for o in lesson.get("objectives", []) or []:`):

```python
            for o in objectives.for_lesson(manifest, lesson):
```

- [ ] **Step 4: Run to verify it passes (and no regression)**

Run: `.venv/bin/python -m pytest tests/test_exams.py -q`
Expected: PASS. Existing embedded-fixture tests pass via the fallback; the new refs test passes via resolution.

- [ ] **Step 5: Commit**

```bash
git add backend/exams.py tests/test_exams.py
git commit -m "feat(exams): blueprints read objectives via the registry resolver"
```

---

### Task 5: Serve resolved manifests to the browser and to the revise stage

**Files:**
- Modify: `backend/app.py` — `get_course` (line ~256-270) and `post_course_revise` (line ~958-991)
- Test: `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `objectives.resolved_manifest` (Task 1).
- Produces: `GET /api/courses/<id>` returns a manifest with embedded `lesson.objectives` (frontend contract unchanged even after disk goes to refs). `compiler.revise_course` receives a resolved (id-bearing) manifest, so a retained lesson's objectives carry their ids into the proposal.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_courses_api.py` (which already has a `get_course` test asserting `schemaVersion` at line 41):

```python
def test_get_course_returns_embedded_objectives_for_v3(tmp_path, monkeypatch):
    from backend import objectives, courses
    # write a v3 (registry) course to disk, then GET it
    wire = dict(COMPILED, id="c-demo")   # COMPILED fixture (module 6-10) is wire shape
    disk = objectives.build_registry({**wire, "id": "c-demo"})
    course_dir = tmp_path / "c-demo"
    (course_dir / "lessons").mkdir(parents=True)
    (course_dir / "course.json").write_text(__import__("json").dumps(disk))
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path)
    # ... build the test client per this file's existing pattern, GET /api/courses/c-demo ...
    body = resp.get_json()
    lesson = body["modules"][0]["lessons"][0]
    assert lesson["objectives"][0]["text"]   # embedded objectives present in the response
    assert "objectives" in body["modules"][0]["lessons"][0]
```

(Wire this to the file's existing client fixture and disk-layout helpers — follow the pattern already used by the other `test_courses_api.py` tests rather than the sketch above.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py::test_get_course_returns_embedded_objectives_for_v3 -v`
Expected: FAIL — the raw v3 manifest has `objectiveIds`, not `objectives`, on each lesson.

- [ ] **Step 3: Resolve in the two handlers**

In `backend/app.py`, ensure `objectives` is imported (add to the existing `from backend import ...` block).

In `get_course`, change the response (currently `return jsonify({**manifest, "mastery": ...})`):

```python
        return jsonify({**objectives.resolved_manifest(manifest),
                        "mastery": m, "masteryCounts": mastery.mastery_counts(m),
                        "exams": ex, "coursePassed": exams.course_passed(ex, manifest)})
```

In `post_course_revise`, change the `revise_course` call to pass a resolved manifest so retained objectives carry their ids:

```python
        proposed = compiler.revise_course(
            objectives.resolved_manifest(manifest), body.get("messages", []),
            generate_sourced=generate_sourced, verify=verify,
        )
```

- [ ] **Step 4: Run to verify it passes (and no regression)**

Run: `.venv/bin/python -m pytest tests/test_courses_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(api): resolve objective refs for course responses and revise input"
```

---

### Task 6: Writers build the registry (disk becomes refs-canonical)

**Files:**
- Modify: `backend/courses.py` — `write_course` (line ~106-154) and `apply_revision` (line ~157-212)
- Test: `tests/test_courses.py`, `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `objectives.build_registry` (Task 1).
- Produces: a *compiled* course written to disk is in v3 disk shape (registry + `objectiveIds`, no embedded lesson objectives, `schemaVersion 3`). A *legacy* course (no `schemaVersion`, no objectives) is written exactly as before. `apply_revision` persists the revised course in v3 disk shape, preserving retained objectives' ids.

- [ ] **Step 1: Write the failing tests**

In `tests/test_courses.py`, update `test_write_course_compiled_shape_slugs_ids_and_remaps_prereqs` expectations and add a registry assertion:

```python
def test_write_course_compiled_builds_registry_and_refs(tmp_path):
    OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}
    compiled = {"schemaVersion": 2, "title": "C", "subtitle": "", "brief": "",
                "level": {"code": "bachelor-y1", "label": "B"}, "targetHours": 5,
                "skills": ["s"], "outcomes": [OBJ], "groundingSources": [],
                "modules": [{"id": "m1", "title": "M", "outcomes": [OBJ], "lessons": [
                    {"id": "l1", "title": "L1", "estMinutes": 30, "objectives": [OBJ], "prereqs": []},
                ]}]}
    m = courses.write_course(tmp_path, compiled)
    assert m["schemaVersion"] == 3
    assert [o["id"] for o in m["objectives"]] == [f'{m["id"]}-o1']
    lesson = m["modules"][0]["lessons"][0]
    assert lesson["objectiveIds"] == [f'{m["id"]}-o1']
    assert "objectives" not in lesson
    # module/course outcomes remain embedded, untouched
    assert m["outcomes"] == [OBJ]
    assert m["modules"][0]["outcomes"] == [OBJ]
```

Keep `test_write_course_legacy_shape_unchanged` — it must still assert `"schemaVersion" not in m` and no registry.

For `apply_revision`, add to `tests/test_courses.py` (or extend the existing `test_apply_revision_*`) a check that a retained lesson keeps its objective id after a revise write. Build the "current" manifest as a v3 disk course, resolve → revise-shape proposal that keeps the lesson, apply, and assert the persisted objective id is unchanged.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_courses.py -q`
Expected: FAIL — write_course currently carries `objectives` through embedded and keeps `schemaVersion 2`.

- [ ] **Step 3: Build the registry in `write_course`**

In `backend/courses.py` `write_course`, after the `manifest = {...}` dict is assembled and the `for field in (...)` carry-through loop (line ~137-149), and before writing, convert compiled courses to disk shape:

```python
    # A compiled course (it carries schemaVersion) becomes refs-canonical on disk: lift its
    # embedded lesson objectives into a course-level registry with stable ids. A legacy
    # proposal (no schemaVersion) is written exactly as before.
    if "schemaVersion" in manifest:
        manifest = objectives.build_registry(manifest)

    course_dir = content_dir / course_id
    (course_dir / "lessons").mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(course_dir / "course.json",
                             json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
```

- [ ] **Step 4: Build the registry in `apply_revision`**

In `backend/courses.py` `apply_revision`, the incoming `revised` is a wire proposal (embedded objectives, ids on retained lessons). Convert it to disk shape before the lesson-id validation and write. Insert immediately after the `valid_compiled_course(revised)` gate (line ~172-173) and before reading `current`:

```python
    if not generation.valid_compiled_course(revised):
        return None
    revised = objectives.build_registry(revised)   # wire -> disk (v3), preserving retained ids
    current = json.loads(manifest_path.read_text())
```

The existing lesson-id validation and `pattern` check operate on lesson ids, which are untouched by `build_registry`, so they still apply.

- [ ] **Step 5: Run to verify they pass (and no regression across the write/read boundary)**

Run: `.venv/bin/python -m pytest tests/test_courses.py tests/test_courses_api.py tests/test_exams.py tests/test_review_items.py -q`
Expected: PASS. Readers (Tasks 3-5) resolve the refs written here; the round-trip is closed.

- [ ] **Step 6: Commit**

```bash
git add backend/courses.py tests/test_courses.py tests/test_courses_api.py
git commit -m "feat(courses): write_course and apply_revision persist the objective registry"
```

---

### Task 7: Compiler emits schemaVersion 3

**Files:**
- Modify: `backend/compiler.py:296` (`_assemble_contract`)
- Test: `tests/test_compiler.py` (and any assert of `schemaVersion == 2` on compile/enrich/revise output)

**Interfaces:**
- Consumes: nothing new. `valid_compiled_course` already accepts 3 (Task 2).
- Produces: `compile_course`, `enrich_course`, and `revise_course` outputs carry `schemaVersion: 3` (wire shape, embedded objectives).

- [ ] **Step 1: Update the failing asserts**

In `tests/test_compiler.py`, change the version asserts on assembled output:
- `test_assemble_contract_computes_hours_and_shape`: `assert c["schemaVersion"] == 3`
- `test_compile_course_runs_all_stages`, `test_revise_course_keeps_retained_objectives_...`: `assert ...["schemaVersion"] == 3`
- Leave enrich idempotency/id tests as they are except any explicit `== 2` version assert → `== 3`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_compiler.py -q`
Expected: FAIL — producer still emits 2.

- [ ] **Step 3: Bump the emitted version**

In `backend/compiler.py` `_assemble_contract` (line 296), change:

```python
        "schemaVersion": 3,
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_compiler.py tests/test_courses.py tests/test_courses_api.py -q`
Expected: PASS. (`write_course` already stamps 3 via `build_registry`, so the v2-input fixtures in `test_courses.py` still land as v3 on disk — consistent.)

- [ ] **Step 5: Full backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. If any remaining fixture asserts `schemaVersion == 2` on *compiler output* (not on a hand-built input fixture), update it to 3.

- [ ] **Step 6: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "feat(compiler): emit schemaVersion 3 from _assemble_contract"
```

---

### Task 8: Deterministic v2→v3 migration script

**Files:**
- Create: `backend/migrate_objective_ids.py`
- Test: `tests/test_migrate_objective_ids.py`

**Interfaces:**
- Consumes: `objectives.build_registry` (Task 1), `fsutil.write_text_atomic`.
- Produces: `migrate(content_dir, *, now=None) -> dict` returning `{"migrated": n, "clean": n, "errors": n}`; a `main()` entry point. Deterministic (no LLM). Idempotent (skips schemaVersion ≥ 3). Writes a `course.json.pre-objid-<ts>` backup sidecar before overwriting. Never deletes or rewrites lesson bodies, events, or any other file.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_migrate_objective_ids.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrate_objective_ids.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the migration script**

```python
# backend/migrate_objective_ids.py
"""Deterministic Phase-0 migration: schemaVersion-2 courses (embedded objectives) ->
schemaVersion-3 (objectives registry + objectiveIds refs). No LLM, no content change --
a pure id-stamp, so it is lossless and idempotent. Writes a pre-migration backup sidecar
before overwriting, and skips courses already at v3.

Run on a COPY of content/ first, verify, and only then against the live tree (after the
daily backup is confirmed). Usage:
    .venv/bin/python -m backend.migrate_objective_ids [CONTENT_DIR]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil, objectives


def migrate(content_dir, *, now=None):
    content_dir = Path(content_dir)
    counts = {"migrated": 0, "clean": 0, "errors": 0}
    if not content_dir.exists():
        return counts
    for child in sorted(content_dir.iterdir()):
        manifest_path = child / "course.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError as exc:
            print(f"ERROR {child.name}: course.json does not parse ({exc})")
            counts["errors"] += 1
            continue
        if manifest.get("schemaVersion", 0) >= 3:
            print(f"skip  {child.name}: already schemaVersion 3")
            counts["clean"] += 1
            continue
        if manifest.get("schemaVersion") != 2:
            # legacy (pre-compile) course with no objectives -> nothing to id-stamp;
            # leave it exactly as-is (Phase 0 does not enrich content).
            print(f"skip  {child.name}: not a compiled (v2) course")
            counts["clean"] += 1
            continue
        try:
            disk = objectives.build_registry(manifest)
        except Exception as exc:  # one bad course must not abort the batch
            print(f"ERROR {child.name}: build_registry failed ({exc})")
            counts["errors"] += 1
            continue
        ts = now or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        try:
            (child / f"course.json.pre-objid-{ts}").write_text(manifest_path.read_text())
            fsutil.write_text_atomic(manifest_path,
                                     json.dumps(disk, indent=2, ensure_ascii=False))
        except Exception as exc:
            print(f"ERROR {child.name}: write failed ({exc})")
            counts["errors"] += 1
            continue
        n = len(disk.get("objectives", []))
        print(f"ok    {child.name}: migrated to schemaVersion 3, {n} objectives")
        counts["migrated"] += 1
    return counts


def main():
    from backend import courses
    content_dir = sys.argv[1] if len(sys.argv) > 1 else courses.CONTENT_DIR
    result = migrate(content_dir)
    print(f"\n{result['migrated']} migrated, {result['clean']} clean, {result['errors']} errors")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_migrate_objective_ids.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Dry-run against a local copy of the live content (proof it is lossless)**

```bash
cp -R content /tmp/content-migrate-test
.venv/bin/python -m backend.migrate_objective_ids /tmp/content-migrate-test/courses
```
Expected: one `ok ... migrated` line per compiled course, `0 errors`. Spot-check one migrated `course.json`: `schemaVersion` is 3, a `objectives[]` registry is present, and every lesson has `objectiveIds`. Confirm the `.pre-objid-*` sidecar holds the original v2.

- [ ] **Step 6: Commit**

```bash
git add backend/migrate_objective_ids.py tests/test_migrate_objective_ids.py
git commit -m "feat(migrate): deterministic v2->v3 objective-id migration with backup sidecar"
```

---

### Task 9: Frontend contract gate accepts schemaVersion 3

**Files:**
- Modify: `frontend/src/app.js:478`
- Test: `frontend/tests/views.test.js` (contract-block rendering)

**Interfaces:**
- Consumes: nothing. The manifest reaching the frontend already carries embedded `objectives` (Task 5), so `syllabus.js` is unchanged.
- Produces: a v3 course renders the contract block (level/hours/skills), identical to a v2 course. Without this, a migrated course would silently hide that block — the one place "no user-visible change" would otherwise break.

- [ ] **Step 1: Write the failing test**

In `frontend/tests/views.test.js`, the `COURSE` fixture (line ~886) drives dashboard/contract rendering. Add a test that a schemaVersion-3 course still populates the contract:

```js
test("sessionData contract is populated for schemaVersion 3 courses", () => {
  // whichever helper the file uses to build sessionData()/dashboard from ui.manifest,
  // pass { ...COURSE, schemaVersion: 3 } and assert the contract block (level/hours/skills)
  // renders exactly as it does for schemaVersion 2.
});
```

(Match the existing dashboard/contract test pattern in this file; the key assertion is that `level`, `hours`, and `skills` appear for a `schemaVersion: 3` manifest.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && node --test tests/views.test.js`
Expected: FAIL — the strict `=== 2` gate yields `contract: null` for v3.

- [ ] **Step 3: Widen the gate**

In `frontend/src/app.js` line 478, change:

```js
      contract: (ui.manifest && ui.manifest.schemaVersion >= 2) ? {
```

- [ ] **Step 4: Run to verify it passes (and full frontend suite)**

Run: `cd frontend && node --test`
Expected: PASS (370 tests).

- [ ] **Step 5: Frontend import-resolution check (app.js is not unit-tested for wiring)**

Run a node import-resolution check on the changed module per the project's frontend-import-check practice, to confirm `app.js` still resolves.
Expected: no unresolved imports.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app.js frontend/tests/views.test.js
git commit -m "feat(frontend): contract block renders for schemaVersion 3 courses"
```

---

## Deploy sequence (operational — run by Werner, gated)

Not a code task; the migration touches the live course store, so it is human-gated per the data-loss rule.

1. Merge the branch; pull on the Pi.
2. Confirm the daily backup exists and restores: `.venv/bin/python -m backend.restore_check` (or check `~/backups/claude_university/restore-check.log`).
3. Check for in-flight generation before restart: `pgrep -fa claude`.
4. **Migrate on the live tree** (the code is safe on un-migrated v2 courses via the `for_lesson` fallback, so ordering is forgiving): `.venv/bin/python -m backend.migrate_objective_ids`. Expect 4 migrated, 0 errors, one `.pre-objid-*` sidecar per course.
5. Restart `claude_university`; verify each course loads, the syllabus renders objectives, an exam blueprints, and a revise round-trip preserves objective ids.
6. Keep the `.pre-objid-*` sidecars until the deploy is confirmed healthy, then they may be cleaned up.

## Self-review checklist (run before execution)

- **Spec coverage:** stable ids (§3) → T1/T6/T8; registry data model (§6) → T1/T6; refs-canonical single source of truth (§5/§12) → T6 (disk) + T3/T4/T5 (readers) + T1 (`for_lesson` no persisted fallback); id preservation across revise (§11) → T1 (`build_registry` id-keep) + T5 (resolved revise input) + T6 (apply_revision); schemaVersion 3 (§10) → T2/T7; migration on a copy with backup (§10/§11 + data-loss rule) → T8 + deploy sequence; no user-visible change (§10) → T5 (resolve-at-boundary) + T9 (contract gate). Quick honesty win (`SESSION_MIN`, `estMinutes`) is explicitly **out of Phase 0** (spec §10 marks it independent; Phase 4 owns the metric work).
- **Type consistency:** `for_lesson`/`resolved_manifest`/`build_registry`/`objective_index` names are used identically across T1, T3, T4, T5, T6, T8. Objective id format `<courseId>-oN` is consistent (T1 mint, T8 assert). schemaVersion literal `3` consistent (T2 gate, T6 stamp, T7 emit, T8 output).
- **Placeholder scan:** the only intentionally-sketched steps are the three test-wiring stubs (T4 objective text, T5 client fixture, T9 dashboard helper) which must follow each file's existing fixture pattern — the implementer fills these against the real helpers, not with invented ones.
```
