# Refine This Course — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Werner discuss changes to an existing course with Claude and apply a reviewed,
approved revised syllabus that preserves retained lessons' ids, bodies, and progress.

**Architecture:** A third compiler path `revise_course` (structure changes, retained identity
survives via a model-emitted `keepId` per lesson) + a `courses.apply_revision` in-place writer
with backup, fronted by a `/revise` (non-persisting) and `/apply-revision` (persisting) route
pair, and a frontend flow mirroring the existing intake → syllabus → create flow.

**Tech Stack:** Flask + SQLite backend (pytest via `.venv/bin/pytest`), plain ES-module
frontend (`node --test frontend/tests/<file>.test.js` — NEVER a bare directory), Pi deploy via
rsync + `systemctl restart claude-university`.

## Global Constraints

- All learner-/model-authored text rendered in the frontend MUST be `esc()`-escaped
  (`frontend/src/escape.js`). No exceptions.
- Course-id and lesson-id validation uses the existing `_ID_RE` in `app.py`; new lesson ids
  follow the pattern `^<course_id>-l\d+$` (matches `courses.write_course`).
- The compiler stays DB-free. Anything needing the event log (progress-at-risk) is computed in
  the route, which holds the DB connection.
- Nothing is persisted until the explicit apply step. `revise_course` and the `/revise` route
  return a proposal only.
- Every apply writes a `course.json.pre-revise-<UTC-stamp>` backup before the atomic in-place
  write. Retained lessons' cached body files under `lessons/` are never deleted.
- Model output is untrusted: `apply_revision` re-validates the submitted course server-side
  (id equals the URL course id; `valid_compiled_course`; every lesson id is either a
  pre-existing id or matches `^<course_id>-l\d+$`; no duplicate ids).
- Skip the accuracy sweep on revision (it is slow, web-grounded, and structure-risky). Reuse
  the per-module objectives stage (`_objectives_and_graph`) which is already timeout-safe.
- Reuse `syllabusHTML` unchanged for the review render. Reuse the existing shimmer loading state.
- DEFAULT_MODEL and all `claude_client` wiring stay as the compile route uses them.

---

### Task 1: `keepId` id-resolution + revise-outline validator (compiler.py, pure functions)

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Produces:
  - `valid_revise_outline(obj)` → bool. True iff `obj` is a dict with a non-empty `modules`
    list; each module a dict with a truthy `title` and a non-empty `lessons` list; each lesson a
    dict with a truthy `title` (a `keepId`, if present, must be a str or None); and `changeSummary`
    is a list (possibly empty) of strings. `title`/`subtitle`/`level`/`groundingSources` optional.
  - `_resolve_revised_ids(existing_manifest, revised_outline)` → an id-bearing outline dict
    `{"title","subtitle","level","modules":[{"id","title","lessons":[{"id","title","estMinutes",
    "_keep": bool}]}]}` plus a returned set/list of retained ids. It assigns ids:
    - A lesson whose `keepId` is an existing lesson id NOT already used in this pass → that id,
      `_keep=True`.
    - Otherwise (absent, unknown, or duplicate `keepId`) → a freshly minted `<course_id>-l<N>`
      where N starts at `max(existing lesson numeric suffix) + 1` and increments per new lesson,
      `_keep=False`.
    - Module ids are re-minted positionally `m1..mK` (module identity does not carry progress).
    - `estMinutes` defaults to 60 when the model omits it.

- [ ] **Step 1: Write failing tests**

```python
def test_valid_revise_outline_gates_shape():
    good = {"modules": [{"title": "M1", "lessons": [{"title": "L1", "keepId": "c-l1"},
                                                     {"title": "L2"}]}],
            "changeSummary": ["added L2"]}
    assert compiler.valid_revise_outline(good)
    assert not compiler.valid_revise_outline({"modules": []})
    assert not compiler.valid_revise_outline({"modules": [{"title": "M", "lessons": []}]})
    assert not compiler.valid_revise_outline({"modules": [{"title": "M",
        "lessons": [{"keepId": "c-l1"}]}]})  # lesson missing title
    assert not compiler.valid_revise_outline({"modules": [{"lessons": [{"title": "L"}]}]})  # module missing title
    assert not compiler.valid_revise_outline({"modules": [{"title": "M",
        "lessons": [{"title": "L"}]}], "changeSummary": "nope"})  # changeSummary not a list


def test_resolve_revised_ids_keeps_valid_reuses_and_mints_new():
    existing = {"id": "c", "modules": [
        {"id": "m1", "title": "A", "lessons": [{"id": "c-l1", "title": "One"},
                                               {"id": "c-l2", "title": "Two"}]},
        {"id": "m2", "title": "B", "lessons": [{"id": "c-l3", "title": "Three"}]}]}
    revised = {"modules": [
        {"title": "A2", "lessons": [{"title": "One renamed", "keepId": "c-l1"},
                                    {"title": "Brand new"}]},                 # new -> mint
        {"title": "B", "lessons": [{"title": "Three", "keepId": "c-l3"},
                                   {"title": "Dup", "keepId": "c-l1"},        # dup keepId -> mint
                                   {"title": "Ghost", "keepId": "c-l99"}]}]}  # unknown -> mint
    outline, retained = compiler._resolve_revised_ids(existing, revised)
    flat = [l for m in outline["modules"] for l in m["lessons"]]
    assert [l["id"] for l in flat[:1]] == ["c-l1"]          # retained keeps id
    assert flat[0]["_keep"] is True and flat[0]["title"] == "One renamed"
    # highest existing suffix is 3 -> new ids start at c-l4
    new_ids = [l["id"] for l in flat if not l["_keep"]]
    assert new_ids == ["c-l4", "c-l5", "c-l6"]
    assert all(i.startswith("c-l") for i in new_ids)
    assert "c-l2" not in [l["id"] for l in flat]            # c-l2 removed (not referenced)
    assert set(retained) == {"c-l1", "c-l3"}
    assert [m["id"] for m in outline["modules"]] == ["m1", "m2"]  # modules re-minted positionally
```

- [ ] **Step 2: Run to verify they fail** — `.venv/bin/pytest tests/test_compiler.py -k "revise_outline or resolve_revised" -q` → FAIL (functions not defined).

- [ ] **Step 3: Implement** (add to `backend/compiler.py`):

```python
def valid_revise_outline(obj):
    if not isinstance(obj, dict):
        return False
    if not isinstance(obj.get("changeSummary", []), list):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and isinstance(m.get("title"), str) and m["title"].strip()):
            return False
        lessons = m.get("lessons")
        if not (isinstance(lessons, list) and lessons):
            return False
        for l in lessons:
            if not (isinstance(l, dict) and isinstance(l.get("title"), str) and l["title"].strip()):
                return False
            keep = l.get("keepId")
            if keep is not None and not isinstance(keep, str):
                return False
    return True


def _max_lesson_num(existing_manifest):
    nums = []
    for m in existing_manifest.get("modules", []):
        for l in m.get("lessons", []):
            mo = re.search(r"-l(\d+)$", l.get("id", ""))
            if mo:
                nums.append(int(mo.group(1)))
    return max(nums) if nums else 0


def _resolve_revised_ids(existing_manifest, revised_outline):
    course_id = existing_manifest["id"]
    existing_ids = {l.get("id") for m in existing_manifest.get("modules", [])
                    for l in m.get("lessons", [])}
    counter = _max_lesson_num(existing_manifest)
    used, retained, modules = set(), [], []
    for mi, m in enumerate(revised_outline.get("modules", []), start=1):
        lessons = []
        for l in m.get("lessons", []):
            keep = l.get("keepId")
            if isinstance(keep, str) and keep in existing_ids and keep not in used:
                lid, is_keep = keep, True
                used.add(keep)
                retained.append(keep)
            else:
                counter += 1
                lid, is_keep = f"{course_id}-l{counter}", False
            lessons.append({"id": lid, "title": l.get("title"),
                            "estMinutes": l.get("estMinutes", 60), "_keep": is_keep})
        modules.append({"id": f"m{mi}", "title": m.get("title"), "lessons": lessons})
    outline = {"title": revised_outline.get("title", existing_manifest.get("title", "")),
               "subtitle": revised_outline.get("subtitle", existing_manifest.get("subtitle", "")),
               "level": revised_outline.get("level", existing_manifest.get("level", {})),
               "modules": modules}
    return outline, retained
```

(Confirm `import re` exists at the top of `compiler.py`; add it if missing.)

- [ ] **Step 4: Run tests** — same command → PASS.

- [ ] **Step 5: Commit** — `git add backend/compiler.py tests/test_compiler.py && git commit -m "feat(revise): keepId id-resolution + revise-outline validator"`

---

### Task 2: `revise_course` + revise-outline prompt + objectives overlay (compiler.py)

**Files:**
- Modify: `backend/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `_resolve_revised_ids`, `valid_revise_outline` (Task 1), plus existing
  `_objectives_and_graph`, `_merge_objectives`, `_assemble_contract`, `generation._resolve_sources`.
- Produces:
  - `_revise_outline_prompt(existing_manifest, messages)` → str.
  - `revise_course(existing_manifest, messages, *, generate_sourced, verify)` → proposed course
    dict with `schemaVersion==2`, `id == existing_manifest["id"]`, and a `changeSummary` list.
    Retained lessons keep their existing objectives; new lessons carry generated objectives;
    prereqs are the freshly computed graph. The accuracy sweep is NOT called.

**Prompt contract** (`_revise_outline_prompt`): give the model the existing course skeleton
(id, title, subtitle, level, modules→lessons with id+title) and the discussion `messages`
(role/content). Instruct it to return ONLY a JSON object, no prose/fence:
`{"title","subtitle","level":{"code","label"},"groundingSources":[{"title","url"}],`
`"changeSummary":["short human-readable change", ...],`
`"modules":[{"title","lessons":[{"title","keepId":"<existing lesson id or omit if new>","estMinutes":90}]}]}`.
Rules stated in the prompt: reuse `keepId` for any lesson that continues an existing one (even
if renamed or moved); omit `keepId` for brand-new lessons; do not invent ids; keep the course
coherent; `changeSummary` lists what changed versus the current course.

- [ ] **Step 1: Write failing test** (uses fakes, asserts overlay + no-sweep):

```python
def test_revise_course_keeps_retained_objectives_mints_new_and_skips_sweep(monkeypatch):
    existing = {"id": "c", "title": "Course", "subtitle": "Sub",
                "level": {"code": "bachelor-y1", "label": "Bachelor Y1"},
                "modules": [{"id": "m1", "title": "A", "lessons": [
                    {"id": "c-l1", "title": "One",
                     "objectives": [{"text": "Do X", "bloom": "Apply"}], "estMinutes": 60}]}]}
    revise_outline = {"title": "Course", "subtitle": "Sub",
                      "level": {"code": "bachelor-y1", "label": "Bachelor Y1"},
                      "groundingSources": [{"title": "S", "url": "https://ex.com"}],
                      "changeSummary": ["added a lesson"],
                      "modules": [{"title": "A", "lessons": [
                          {"title": "One", "keepId": "c-l1", "estMinutes": 60},
                          {"title": "New", "estMinutes": 90}]}]}

    def fake_sourced(prompt, validate):
        return revise_outline, []            # (obj, captured)

    def fake_verify(prompt, validate):
        # per-module objectives + rollup: give both lessons generated objectives
        if "roll" in prompt.lower() or "skills" in prompt.lower():
            return {"outcomes": [{"text": "Course outcome", "bloom": "Evaluate"}],
                    "skills": ["skill one"]}
        return {"outcomes": [{"text": "Mod outcome", "bloom": "Understand"}],
                "lessons": [{"id": "c-l1", "objectives": [{"text": "GEN one", "bloom": "Apply"}], "prereqs": []},
                            {"id": "c-l4", "objectives": [{"text": "GEN new", "bloom": "Apply"}], "prereqs": []}]}

    monkeypatch.setattr(compiler, "_accuracy_sweep",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("sweep must not run")))
    out = compiler.revise_course(existing, [{"role": "user", "content": "add a lesson"}],
                                 generate_sourced=fake_sourced, verify=fake_verify)
    assert out["id"] == "c" and out["schemaVersion"] == 2
    assert out["changeSummary"] == ["added a lesson"]
    flat = [l for m in out["modules"] for l in m["lessons"]]
    assert flat[0]["id"] == "c-l1"
    assert flat[0]["objectives"] == [{"text": "Do X", "bloom": "Apply"}]   # retained -> existing kept
    assert flat[1]["id"] == "c-l4"
    assert flat[1]["objectives"] == [{"text": "GEN new", "bloom": "Apply"}]  # new -> generated
    assert generation.valid_compiled_course(out)
```

- [ ] **Step 2: Run to verify it fails** — `.venv/bin/pytest tests/test_compiler.py -k revise_course -q` → FAIL.

- [ ] **Step 3: Implement**:

```python
def _revise_outline_prompt(existing_manifest, messages):
    skeleton = {"id": existing_manifest.get("id"), "title": existing_manifest.get("title", ""),
                "subtitle": existing_manifest.get("subtitle", ""),
                "level": existing_manifest.get("level", {}),
                "modules": [{"id": m.get("id"), "title": m.get("title"),
                             "lessons": [{"id": l.get("id"), "title": l.get("title")}
                                         for l in m.get("lessons", [])]}
                            for m in existing_manifest.get("modules", [])]}
    convo = "\n".join(f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                      for msg in messages if isinstance(msg, dict))
    return (
        "You are revising an EXISTING course based on a discussion with the learner. Using web "
        "search where the change needs new material, produce the revised syllabus. Current course:\n"
        f"{json.dumps(skeleton, ensure_ascii=False)}\n\n"
        f"Discussion:\n{convo}\n\n"
        "For every lesson that CONTINUES an existing one (kept as-is, renamed, or moved), set "
        "\"keepId\" to that existing lesson id EXACTLY. OMIT keepId for brand-new lessons. Never "
        "invent ids. Keep the course coherent and correctly ordered. changeSummary lists, in short "
        "human-readable phrases, what changed versus the current course. Reply with ONLY a JSON "
        "object, no prose, no fence:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "...", "label": "..."}, '
        '"groundingSources": [{"title": "...", "url": "..."}], "changeSummary": ["..."], '
        '"modules": [{"title": "...", "lessons": [{"title": "...", "keepId": "c-l1", "estMinutes": 90}]}]}'
    )


def revise_course(existing_manifest, messages, *, generate_sourced, verify):
    obj, captured = generate_sourced(_revise_outline_prompt(existing_manifest, messages),
                                     valid_revise_outline)
    outline, retained = _resolve_revised_ids(existing_manifest, obj)
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    # Overlay: retained lessons keep their previously approved objectives; only prereqs (which
    # depend on the new order) come from the fresh graph. New lessons keep generated objectives.
    existing_obj = {l.get("id"): l.get("objectives")
                    for m in existing_manifest.get("modules", []) for l in m.get("lessons", [])}
    for m in enriched.get("modules", []):
        for l in m.get("lessons", []):
            if l.get("id") in retained and existing_obj.get(l["id"]):
                l["objectives"] = existing_obj[l["id"]]
    compiled = _assemble_contract(_brief_from_manifest(existing_manifest), outline, enriched, sources)
    compiled["id"] = existing_manifest["id"]
    compiled["changeSummary"] = obj.get("changeSummary", [])
    return compiled
```

- [ ] **Step 4: Run tests** — same command → PASS. Then full compiler suite:
  `.venv/bin/pytest tests/test_compiler.py -q`.

- [ ] **Step 5: Commit** — `git commit -am "feat(revise): revise_course — grounded revise outline + objectives overlay, no sweep"`

---

### Task 3: `apply_revision` — validated, backed-up, in-place write (courses.py)

**Files:**
- Modify: `backend/courses.py`
- Test: `tests/test_courses.py`

**Interfaces:**
- Consumes: `generation.valid_compiled_course`.
- Produces: `apply_revision(content_dir, course_id, revised, *, now)` → written manifest dict, or
  `None` if validation fails / the course dir is missing. `now` is an injected UTC timestamp
  string (default computed from `datetime.now(timezone.utc)`) so the backup filename is testable.

Validation rules (return None on any failure): `revised["id"] == course_id`;
`generation.valid_compiled_course(revised)`; collect existing lesson ids from the on-disk
`course.json`; every revised lesson id is either an existing id or matches `^{course_id}-l\d+$`;
no duplicate ids across the revised course.

Write: back up current `course.json` → `course.json.pre-revise-<now>`; atomic write (temp file
in the course dir + `os.replace`) of `revised` (indent=2, ensure_ascii=False). Do NOT touch the
`lessons/` directory. Return `revised`.

- [ ] **Step 1: Write failing tests**

```python
def test_apply_revision_writes_in_place_backs_up_and_preserves_bodies(tmp_path):
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "c-l1", "title": "One"}]}]}))
    (course / "lessons" / "c-l1.json").write_text('{"id": "c-l1"}')  # retained body
    revised = _valid_compiled("c")  # helper building a schemaVersion-2 course with ids c-l1 + new c-l2
    out = courses.apply_revision(cdir, "c", revised, now="20260709T120000Z")
    assert out is not None
    on_disk = json.loads((course / "course.json").read_text())
    assert on_disk["schemaVersion"] == 2 and courses._lesson_id_list(on_disk)  # written in place
    assert (course / "course.json.pre-revise-20260709T120000Z").exists()       # backup made
    assert (course / "lessons" / "c-l1.json").exists()                          # body preserved


def test_apply_revision_rejects_tampered_course(tmp_path):
    cdir = tmp_path
    course = cdir / "c"
    (course / "lessons").mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"id": "c", "title": "Old",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "c-l1", "title": "One"}]}]}))
    foreign = _valid_compiled("c")
    foreign["modules"][0]["lessons"].append({"id": "other-l9", "title": "X",
        "objectives": [{"text": "y", "bloom": "Apply"}], "estMinutes": 30})  # bad id pattern
    assert courses.apply_revision(cdir, "c", foreign, now="t") is None
    assert courses.apply_revision(cdir, "c", {**foreign, "id": "d"}, now="t") is None  # id mismatch
```

(Add a `_valid_compiled(cid)` helper in the test module building a minimal valid
`schemaVersion:2` course, and use whichever existing helper the test file already has to list
lesson ids — or inline the comprehension.)

- [ ] **Step 2: Run to verify they fail** — `.venv/bin/pytest tests/test_courses.py -k apply_revision -q` → FAIL.

- [ ] **Step 3: Implement** (add to `backend/courses.py`; ensure imports `os`, `re`,
  `from datetime import datetime, timezone`, and `from backend import generation` at top —
  match the module's existing import style; if importing generation would cause a cycle, import
  it lazily inside the function):

```python
def apply_revision(content_dir, course_id, revised, *, now=None):
    content_dir = Path(content_dir)
    course_dir = content_dir / course_id
    manifest_path = course_dir / "course.json"
    if not manifest_path.exists():
        return None
    if not isinstance(revised, dict) or revised.get("id") != course_id:
        return None
    from backend import generation
    if not generation.valid_compiled_course(revised):
        return None
    current = json.loads(manifest_path.read_text())
    existing_ids = {l.get("id") for m in current.get("modules", []) for l in m.get("lessons", [])}
    pattern = re.compile(rf"^{re.escape(course_id)}-l\d+$")
    seen = set()
    for m in revised.get("modules", []):
        for l in m.get("lessons", []):
            lid = l.get("id")
            if lid in seen:
                return None
            seen.add(lid)
            if lid not in existing_ids and not pattern.match(lid or ""):
                return None
    if now is None:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (course_dir / f"course.json.pre-revise-{now}").write_text(manifest_path.read_text())
    tmp = course_dir / "course.json.tmp"
    tmp.write_text(json.dumps(revised, indent=2, ensure_ascii=False))
    os.replace(tmp, manifest_path)
    return revised
```

- [ ] **Step 4: Run tests** — same command → PASS, then `.venv/bin/pytest tests/test_courses.py -q`.

- [ ] **Step 5: Commit** — `git commit -am "feat(revise): apply_revision — validated in-place write with backup"`

---

### Task 4: `/revise` and `/apply-revision` routes (app.py)

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_app.py` (match the file the other route tests live in — grep for
  `post_course_compile` / `/api/courses/compile` to find it).

**Interfaces:**
- Consumes: `compiler.revise_course`, `courses.apply_revision`,
  `generation.valid_compiled_course`, `courses.completed_lesson_ids`, the existing
  `claude_client` lambdas and error handling, `_ID_RE`.

**`POST /api/courses/<course_id>/revise`** — body `{messages: [...]}`:
- 404 if `not _ID_RE.match(course_id)` or the manifest is missing.
- Build `generate_sourced` / `verify` exactly as `post_course_compile` does.
- `try: proposed = compiler.revise_course(manifest, messages, generate_sourced=..., verify=...)`
  with the same `ClaudeAuthError`→503 (reauth) and `ClaudeError`→502 handling.
- If `not generation.valid_compiled_course(proposed)` → 502.
- Compute `progressAtRisk`: `completed = courses.completed_lesson_ids(conn, course_id)`; for
  each existing lesson id NOT present in the proposed course's lesson-id set AND in `completed`,
  include `{"id": ..., "title": <existing title>}`. Close the conn in a `finally`.
- Return `jsonify({"course": proposed, "changeSummary": proposed.get("changeSummary", []),
  "progressAtRisk": progressAtRisk})`. Does NOT persist.

**`POST /api/courses/<course_id>/apply-revision`** — body `{course: {...}}`:
- 404 if `not _ID_RE.match(course_id)`.
- `revised = body.get("course")`; `written = courses.apply_revision(courses.CONTENT_DIR,
  course_id, revised)`; if `written is None` → 400 `{"error": "invalid revision"}`.
- Return `jsonify({"course": written})`.

- [ ] **Step 1: Write failing tests** — a `/revise` test that monkeypatches
  `compiler.revise_course` to return a known proposed course dropping a completed lesson, seeds a
  `lesson_reviewed`/completion event for that lesson, and asserts the response carries
  `progressAtRisk` with that lesson and does NOT write `course.json`; an `/apply-revision` test
  that posts a valid revised course and asserts `course.json` changed on disk, plus a 400 on a
  tampered payload. Follow the existing app-test patterns (test client, temp content dir,
  monkeypatched `claude_client`).

- [ ] **Step 2: Run to verify they fail** → FAIL (routes 404).

- [ ] **Step 3: Implement** both routes inside `create_app`, mirroring `post_course_compile`'s
  structure and the DB-conn handling in `get_reviews`/`get_course`.

- [ ] **Step 4: Run tests** — `.venv/bin/pytest tests/test_app.py -q` (or the matched file),
  then the full backend suite `.venv/bin/pytest -q`.

- [ ] **Step 5: Commit** — `git commit -am "feat(revise): /revise (non-persisting) + /apply-revision routes"`

---

### Task 5: courses.js API helpers + dashboard Refine button (frontend)

**Files:**
- Modify: `frontend/src/courses.js`, `frontend/src/views/dashboard.js`
- Test: `frontend/tests/courses.test.js`, `frontend/tests/views.test.js`

**Interfaces:**
- Produces:
  - `reviseCourse({fetch, courseId, messages})` → `{course, changeSummary, progressAtRisk}`
    (POST `/api/courses/<id>/revise`). Follow the exact shape/pattern of the existing
    `compileProgram` in this file (same error handling, same `resp.json()` usage).
  - `applyRevision({fetch, courseId, course})` → written course (POST
    `/api/courses/<id>/apply-revision`).
  - dashboard.js renders a secondary button
    `<button class="btn-secondary" data-action="refine" style="margin-top:8px">Refine this course</button>`
    directly after the existing "View all lessons" button.

- [ ] **Step 1: Write failing tests** — in `courses.test.js`, assert `reviseCourse` and
  `applyRevision` POST to the right URLs with the right bodies and return the parsed course
  (mirror the existing `compileProgram` test). In `views.test.js`, assert `dashboardHTML`
  output contains `data-action="refine"`.

- [ ] **Step 2: Run to verify they fail** — `node --test frontend/tests/courses.test.js frontend/tests/views.test.js` → FAIL.

- [ ] **Step 3: Implement** the two helpers (copy `compileProgram`'s structure) and add the
  button line in `dashboard.js`'s session card, after the "View all lessons" button.

- [ ] **Step 4: Run tests** — same command → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(revise): courses.js revise/apply helpers + dashboard Refine button"`

---

### Task 6: app.js refine flow + revision review screen + CSS (frontend)

**Files:**
- Modify: `frontend/src/app.js`, `frontend/styles.css`
- Create: `frontend/src/views/revision.js`
- Test: `frontend/tests/views.test.js`

**Interfaces:**
- Consumes: `reviseCourse`, `applyRevision` (Task 5), `syllabusHTML`, the existing chat view,
  the existing shimmer loading state, `esc`.
- Produces:
  - `frontend/src/views/revision.js` exporting `revisionHTML({course, changeSummary,
    progressAtRisk})` → the review screen: `syllabusHTML(course)` + a "What's changing" list
    (each `changeSummary` item `esc()`-escaped) + a progress-at-risk callout when the list is
    non-empty ("Progress on N lesson(s) will no longer count:" + escaped titles) + two buttons
    `data-action="apply-revision"` and `data-action="keep-discussing"`.
  - app.js wiring: a `data-action="refine"` handler → refine chat screen (reuse the chat view,
    seed a lead-in line naming the course); a "Propose changes" action → `ui.screen="revising"`
    (shimmer) → `reviseCourse(...)` → `ui.screen="revision"` render `revisionHTML(...)`;
    `apply-revision` → `applyRevision(...)` → reload course → dashboard; `keep-discussing` →
    back to the refine chat. New `ui.screen` values guarded like the existing screens.

- [ ] **Step 1: Write failing test** — in `views.test.js`, assert `revisionHTML` renders the
  syllabus title, a `changeSummary` item, an `apply-revision` button, and — given a
  `progressAtRisk` entry — an escaped warning; include an XSS test feeding
  `<img src=x onerror=alert(1)>` as a changeSummary item and asserting it is escaped
  (no raw `<img`).

- [ ] **Step 2: Run to verify it fails** — `node --test frontend/tests/views.test.js` → FAIL.

- [ ] **Step 3: Implement** `revision.js`, wire app.js (mirror the existing
  `showChat`/`compileAndReview`/`acceptSyllabus` handlers for the intake flow), and add CSS for
  the "What's changing" list + `.progress-at-risk` callout (reuse existing tokens:
  `--glass-stat`, `--border-glass`, `--r-md`, `--purple`, `--text-mut`).

- [ ] **Step 4: Run tests** — `node --test frontend/tests/views.test.js`, then the full frontend
  suite `node --test frontend/tests/*.test.js`. Run the node import-resolution check on the
  changed/new frontend modules (per the frontend-import-check memory).

- [ ] **Step 5: Commit** — `git commit -am "feat(revise): app.js refine flow + revision review screen + CSS"`

---

## Post-build

- Final whole-branch review (most capable model), fix Critical/Important, then squash-or-keep
  per Werner's git policy (this is on `main` under the autonomous loop — build on a feature
  branch `feat/refine-course` off `main`, do NOT merge/push until Werner approves).
- Deploy to the Pi (rsync `--exclude='data/'`, restart `claude-university`), verify with a real
  refine on a throwaway/duplicate course — NOT on the 4 real courses until Werner has reviewed.
- Report at the slice boundary with the spec path for Werner's review.
