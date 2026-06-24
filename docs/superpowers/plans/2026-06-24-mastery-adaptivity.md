# Mastery & Adaptivity (Slice 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive a per-lesson mastery level from the event log and make lesson generation adapt to
the learner's recent performance.

**Architecture:** Pure event-derived logic (`backend/mastery.py`) parallel to `srs.py`, combining
SM-2 repetitions with `lesson_check` accuracy. A course-level performance summary is injected into
`lesson_prompt`. Mastery is exposed on `GET /api/courses/<id>` and shown as a small breakdown on
the dashboard. No schema change; no curriculum reordering.

**Tech Stack:** Flask + SQLite backend (`.venv/bin/pytest`), plain ES-module frontend
(`node --test`).

## Global Constraints

- Mastery and the performance summary are **pure functions of the event log** — no new tables, no
  stored mastery. Same principle as `srs.py`.
- Four levels, exact order: `LEVELS = ["attempted", "familiar", "proficient", "mastered"]`.
- Level rule: reps ladder (`0→attempted, 1→familiar, 2→proficient, ≥3→mastered`) with a
  check-accuracy gate — `acc < 0.5` caps at `attempted`; `0.5 ≤ acc < 0.8` caps at `proficient`;
  `acc is None` (no checks answered) applies no cap.
- `lesson_check` payload shape is `{index, type, correct}`; accuracy = correct ÷ total per lesson.
- Only **completed** lessons (`courses.completed_lesson_ids`) get a level.
- Generation stays adaptive only via one prompt line — **no** manifest mutation, **no** regenerating
  cached lessons.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: `backend/mastery.py` — event-derived mastery + performance summary

**Files:**
- Create: `backend/mastery.py`
- Test: `tests/test_mastery.py`

**Interfaces:**
- Consumes: `srs._reviews_by_lesson(conn, course_id)`, `srs.sm2(reviews)["repetitions"]`,
  `courses.load_manifest`, `courses.flatten_lessons`, `courses.completed_lesson_ids`.
- Produces: `LEVELS`; `level_for(reps, acc)->str`; `lesson_mastery(conn, content_dir, course_id)
  ->{lessonId: level}`; `mastery_counts(map)->{level:int}`; `performance_summary(conn, content_dir,
  course_id)->str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mastery.py
import json

from backend import db, mastery


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _course(tmp_path):
    import json as _j
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    manifest = {
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "Demo brief.",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "demo-l1", "title": "L1"}, {"id": "demo-l2", "title": "L2"},
        ]}],
    }
    (root / "demo" / "course.json").write_text(_j.dumps(manifest))
    return root


def _ev(conn, etype, lesson, payload, occurred):
    conn.execute(
        "INSERT INTO events (client_event_id, session_id, device, topic_id, course_id, "
        "event_type, occurred_at, payload) VALUES (?,?,?,?,?,?,?,?)",
        (f"{etype}-{lesson}-{occurred}", "s1", "web", lesson, "demo", etype,
         occurred, json.dumps(payload)),
    )
    conn.commit()


def test_level_for_reps_ladder():
    assert mastery.level_for(0, None) == "attempted"
    assert mastery.level_for(1, None) == "familiar"
    assert mastery.level_for(2, None) == "proficient"
    assert mastery.level_for(3, None) == "mastered"
    assert mastery.level_for(7, None) == "mastered"


def test_level_for_accuracy_gate():
    # strong recall but weak checks -> capped
    assert mastery.level_for(3, 0.4) == "attempted"   # acc<0.5 caps at attempted
    assert mastery.level_for(3, 0.6) == "proficient"  # acc<0.8 caps at proficient
    assert mastery.level_for(3, 0.9) == "mastered"    # acc>=0.8 no cap
    assert mastery.level_for(1, 0.9) == "familiar"    # gate never promotes


def test_lesson_mastery_completed_only_and_reps():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    # l1: two good reviews -> reps 2 -> proficient (no checks)
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-05T10:00:00Z")
    # l2: never completed -> absent
    m = mastery.lesson_mastery(conn, root, "demo")
    assert m == {"demo-l1": "proficient"}


def test_lesson_mastery_check_accuracy_caps():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-05T10:00:00Z")
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "good"}, "2026-06-20T10:00:00Z")
    # reps would be 3 (mastered) but checks are 1/3 correct -> acc 0.33 -> attempted
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": True}, "2026-06-20T10:01:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 1, "type": "mcq", "correct": False}, "2026-06-20T10:02:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 2, "type": "fill", "correct": False}, "2026-06-20T10:03:00Z")
    m = mastery.lesson_mastery(conn, root, "demo")
    assert m == {"demo-l1": "attempted"}


def test_mastery_counts():
    counts = mastery.mastery_counts({"a": "mastered", "b": "mastered", "c": "familiar"})
    assert counts == {"attempted": 0, "familiar": 1, "proficient": 0, "mastered": 2}


def test_performance_summary_no_history_empty():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    assert mastery.performance_summary(conn, root, "demo") == ""


def test_performance_summary_struggling():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "again"}, "2026-06-01T10:00:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": False}, "2026-06-01T10:01:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 1, "type": "mcq", "correct": False}, "2026-06-01T10:02:00Z")
    s = mastery.performance_summary(conn, root, "demo")
    assert "struggling" in s.lower()


def test_performance_summary_strong():
    conn = _conn()
    import tempfile, pathlib
    root = _course(pathlib.Path(tempfile.mkdtemp()))
    for d in ("2026-06-01", "2026-06-05", "2026-06-20"):
        _ev(conn, "lesson_reviewed", "demo-l1", {"quality": "easy"}, f"{d}T10:00:00Z")
    _ev(conn, "lesson_check", "demo-l1", {"index": 0, "type": "mcq", "correct": True}, "2026-06-20T10:01:00Z")
    s = mastery.performance_summary(conn, root, "demo")
    assert "strongly" in s.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mastery.py -q`
Expected: FAIL (`ModuleNotFoundError: backend.mastery`).

- [ ] **Step 3: Write `backend/mastery.py`**

```python
import json

from backend import courses, srs

LEVELS = ["attempted", "familiar", "proficient", "mastered"]


def level_for(reps, acc):
    if reps >= 3:
        base = 3
    elif reps == 2:
        base = 2
    elif reps == 1:
        base = 1
    else:
        base = 0
    if acc is not None:
        if acc < 0.5:
            base = min(base, 0)
        elif acc < 0.8:
            base = min(base, 2)
    return LEVELS[base]


def _checks_by_lesson(conn, course_id):
    rows = conn.execute(
        "SELECT topic_id, payload FROM events "
        "WHERE event_type = 'lesson_check' AND course_id = ?",
        (course_id,),
    ).fetchall()
    out = {}
    for row in rows:
        if not row["topic_id"]:
            continue
        payload = json.loads(row["payload"]) if row["payload"] else {}
        correct, total = out.get(row["topic_id"], (0, 0))
        total += 1
        if payload.get("correct"):
            correct += 1
        out[row["topic_id"]] = (correct, total)
    return out


def lesson_mastery(conn, content_dir, course_id):
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return {}
    completed = courses.completed_lesson_ids(conn, course_id)
    reviews = srs._reviews_by_lesson(conn, course_id)
    checks = _checks_by_lesson(conn, course_id)
    out = {}
    for lesson in courses.flatten_lessons(manifest):
        lid = lesson["id"]
        if lid not in completed:
            continue
        revs = reviews.get(lid)
        reps = srs.sm2(revs)["repetitions"] if revs else 0
        c = checks.get(lid)
        acc = (c[0] / c[1]) if c and c[1] else None
        out[lid] = level_for(reps, acc)
    return out


def mastery_counts(mastery_map):
    counts = {level: 0 for level in LEVELS}
    for level in mastery_map.values():
        counts[level] = counts.get(level, 0) + 1
    return counts


def performance_summary(conn, content_dir, course_id):
    mastery_map = lesson_mastery(conn, content_dir, course_id)
    if not mastery_map:
        return ""
    counts = mastery_counts(mastery_map)
    checks = _checks_by_lesson(conn, course_id)
    correct = sum(c for c, _ in checks.values())
    total = sum(t for _, t in checks.values())
    acc = (correct / total) if total else None
    n = len(mastery_map)
    proficient_plus = counts["proficient"] + counts["mastered"]
    if (acc is not None and acc < 0.6) or counts["attempted"] >= 2:
        return ("The learner has been struggling — reinforce fundamentals, go step-by-step, "
                "and add scaffolding with a brief recap of prerequisites.")
    if (acc is None or acc >= 0.8) and proficient_plus >= max(1, round(0.6 * n)):
        return ("The learner is performing strongly — you may go a bit deeper and faster, and "
                "assume earlier lessons are retained.")
    return "The learner is progressing steadily — keep a balanced pace."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mastery.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/mastery.py tests/test_mastery.py
git commit -m "feat(backend): event-derived per-lesson mastery + performance summary"
```

---

### Task 2: Generation adaptivity — performance line in the lesson prompt

**Files:**
- Modify: `backend/generation.py` (`lesson_prompt`, `ensure_lesson`)
- Test: `tests/test_generation.py` (add cases)

**Interfaces:**
- Consumes: nothing new.
- Produces: `lesson_prompt(..., performance="")` adds a `Learner performance so far: …` line when
  non-empty; `ensure_lesson(..., performance="")` forwards it to `lesson_prompt`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_generation.py`)

```python
def test_lesson_prompt_includes_performance_when_given():
    p = gen.lesson_prompt(
        brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
        module_title="M", position=2, total=3,
        performance="The learner is performing strongly — go deeper.",
    )
    assert "Learner performance so far:" in p
    assert "performing strongly" in p


def test_lesson_prompt_omits_performance_when_empty():
    p = gen.lesson_prompt(
        brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
        module_title="M", position=1, total=1,
    )
    assert "Learner performance so far:" not in p


def test_ensure_lesson_forwards_performance(tmp_path):
    root = _course(tmp_path)
    captured = {}
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["checks"] = [dict(_OK_CHECK)]

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return dict(made)

    gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=fake_generate,
                      performance="The learner has been struggling — slow down.")
    assert "Learner performance so far:" in captured["prompt"]
    assert "struggling" in captured["prompt"]
```

(`_course` and `_OK_CHECK` already exist in this test file.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_generation.py -q -k "performance"`
Expected: FAIL (unexpected `performance` kwarg / line absent).

- [ ] **Step 3: Implement**

In `backend/generation.py`, change `lesson_prompt`'s signature and body:

```python
def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total,
                  performance=""):
    perf_line = f"Learner performance so far: {performance}\n" if performance else ""
    return (
        "You are writing one self-contained lesson for a personalized course.\n"
        f"Course context: {brief}\n"
        f"Learner preferences (JSON): {json.dumps(profile or {})}\n"
        f"{perf_line}"
        f"This is lesson {position} of {total}. Module: {module_title}. "
        f"Lesson title: {lesson_title}.\n\n"
        "Write a single exercise-style lesson. Reply with ONLY a JSON object (no prose, no fence) "
        "with exactly these keys:\n"
        f'  id: "{lesson_id}"\n'
        "  courseId, topic (short), step (integer 1), totalSteps (integer 1), "
        'eyebrow ("EXERCISE"), promptHtml (the question as HTML, may use <code>), '
        "hintHtml (a hint as HTML), solutionAns (the answer), solutionNote (one-sentence why),\n"
        "  checks: a list of 1-3 concept-check items. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,"explanation":"<one sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact expected answer>",'
        '"explanation":"<one sentence why>"}.\n'
        "Shape every learner-facing field to the learner preferences above."
    )
```

Then add `performance=""` to `ensure_lesson` and forward it. Change the signature line:

```python
def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance=""):
```

and in its `prompt = lesson_prompt(...)` call add `performance=performance,` as the final kwarg:

```python
    prompt = lesson_prompt(
        brief=manifest.get("brief", ""),
        profile=profile,
        lesson_id=lesson_id,
        lesson_title=meta["title"],
        module_title=meta["moduleTitle"],
        position=position,
        total=len(flat),
        performance=performance,
    )
```

- [ ] **Step 4: Run to verify pass + no regressions**

Run: `.venv/bin/pytest tests/test_generation.py -q`
Expected: PASS (all, including the 3 new).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(backend): inject learner performance into lesson generation prompt"
```

---

### Task 3: API wiring — mastery on course, performance into JIT generation

**Files:**
- Modify: `backend/app.py` (`get_course`, `get_lesson`; import `mastery`)
- Test: `tests/test_app.py` (add a case)

**Interfaces:**
- Consumes: `mastery.lesson_mastery`, `mastery.mastery_counts`, `mastery.performance_summary`.
- Produces: `GET /api/courses/<id>` body gains `mastery` + `masteryCounts`; `get_lesson` passes a
  computed `performance` into `ensure_lesson`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_app.py`)

First inspect `tests/test_app.py` for the existing client fixture and how a course is placed on
disk for a test (there is already coverage for `/api/courses/<id>`); follow that exact pattern.
Add:

```python
def test_get_course_includes_mastery(client, tmp_path, monkeypatch):
    # Reuse the existing helper/pattern in this file that creates a course on disk and
    # points courses.CONTENT_DIR at it. Then:
    resp = client.get("/api/courses/demo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "mastery" in body
    assert "masteryCounts" in body
    assert set(body["masteryCounts"].keys()) == {"attempted", "familiar", "proficient", "mastered"}
```

If `tests/test_app.py` has no existing course-on-disk helper, place a manifest under a `tmp_path`
courses dir and `monkeypatch.setattr(courses, "CONTENT_DIR", that_dir)` exactly as the nearest
existing course route test does. Match the file's established fixture style.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_app.py -q -k "mastery"`
Expected: FAIL (`KeyError`/assert — keys absent).

- [ ] **Step 3: Implement**

In `backend/app.py`, add `mastery` to the existing import line:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery
```

Replace `get_course` so it attaches mastery:

```python
    @app.get("/api/courses/<course_id>")
    def get_course(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            m = mastery.lesson_mastery(conn, courses.CONTENT_DIR, course_id)
        finally:
            conn.close()
        return jsonify({**manifest, "mastery": m, "masteryCounts": mastery.mastery_counts(m)})
```

In `get_lesson`, compute the performance summary in the existing post-cache-miss conn block and
forward it. Change that block to:

```python
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            performance = mastery.performance_summary(conn, courses.CONTENT_DIR, course_id)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data") if isinstance(prof, dict) else None
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_lesson)
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance,
            )
```

(The cached-lesson early return above this block is unchanged, so the summary is only computed on a
cache miss.)

- [ ] **Step 4: Run to verify pass + no regressions**

Run: `.venv/bin/pytest -q`
Expected: PASS (full backend suite).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_app.py
git commit -m "feat(api): expose mastery on course; feed performance into JIT lesson generation"
```

---

### Task 4: Dashboard mastery breakdown

**Files:**
- Modify: `frontend/src/views/dashboard.js` (`dashboardHTML`), `frontend/src/app.js`
  (`sessionData` + store masteryCounts from `loadCourse`)
- Test: `frontend/tests/views.test.js` (add a case)

**Interfaces:**
- Consumes: `masteryCounts` (`{attempted, familiar, proficient, mastered}`) threaded from the
  `/api/courses/<id>` payload into `dashboardHTML`'s data object.
- Produces: a "Mastery" breakdown rendered only when at least one level count > 0.

- [ ] **Step 1: Read the current code** — open `frontend/src/views/dashboard.js` (`dashboardHTML`
  signature + the data fields it reads) and `frontend/src/app.js` (`openCourse`, `loadCourse`
  result handling, and `sessionData`). The breakdown reads from the same `data` object
  `dashboardHTML` already receives; add a `masteryCounts` field to that object in `sessionData`,
  sourced from the manifest returned by `loadCourse` (store it on `ui`, e.g. `ui.masteryCounts`,
  when the course loads).

- [ ] **Step 2: Write the failing test** (append to `frontend/tests/views.test.js`)

Follow the file's existing import of `dashboardHTML` and its test style. Add:

```javascript
test("dashboard shows a mastery breakdown when there is mastery data", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 50, lessonsDone: 2,
      lessonsTotal: 4, reviewsDue: 0, streakDays: 0,
      masteryCounts: { attempted: 1, familiar: 0, proficient: 1, mastered: 0 } },
    "",
  );
  assert.match(html, /Mastery/);
  assert.match(html, /Proficient/i);
});

test("dashboard omits the mastery breakdown when all counts are zero", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 4, reviewsDue: 0, streakDays: 0,
      masteryCounts: { attempted: 0, familiar: 0, proficient: 0, mastered: 0 } },
    "",
  );
  assert.doesNotMatch(html, /class="mastery"/);
});
```

If `dashboardHTML` is called elsewhere in existing tests without `masteryCounts`, the new branch
must treat a missing `masteryCounts` as all-zero (omit the block) so those tests stay green.

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && node --test tests/views.test.js`
Expected: FAIL (no "Mastery" markup).

- [ ] **Step 4: Implement**

In `dashboard.js`, add a helper and render it. The block lists only non-zero levels with
human labels, inside a card-styled container with class `mastery`:

```javascript
const MASTERY_LABELS = { attempted: "Attempted", familiar: "Familiar", proficient: "Proficient", mastered: "Mastered" };

function masteryHTML(counts) {
  const c = counts || {};
  const parts = ["mastered", "proficient", "familiar", "attempted"]
    .filter((k) => (c[k] || 0) > 0)
    .map((k) => `<span class="m-item"><b>${c[k]}</b> ${MASTERY_LABELS[k]}</span>`);
  if (!parts.length) return "";
  return `<div class="mastery"><div class="m-label">MASTERY</div><div class="m-row">${parts.join("")}</div></div>`;
}
```

Then insert `${masteryHTML(data.masteryCounts)}` into the markup `dashboardHTML` returns, in the
progress/aside column near the COURSE PROGRESS tile (match the existing structure — place it so it
renders as its own block; do not break the existing grid).

In `app.js`:
- In the course-load path (`openCourse`/wherever the `loadCourse` result is stored), keep the
  loaded manifest's `masteryCounts` on `ui` (e.g. `ui.masteryCounts = course.masteryCounts || {}`).
- In `sessionData()`, add `masteryCounts: ui.masteryCounts || {}` to the returned object.

Add minimal CSS to `frontend/styles.css` for `.mastery`, `.m-label`, `.m-row`, `.m-item` (reuse
existing tile/`--glass-*` variables and the `.tile`/eyebrow patterns already in the file; keep it
small and on-theme — a label line plus a wrap row of count chips).

- [ ] **Step 5: Run to verify pass + no regressions**

Run: `cd frontend && node --test`
Expected: PASS (all suites).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/dashboard.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js
git commit -m "feat(frontend): show per-course mastery breakdown on the dashboard"
```

---

### Task 5: End-to-end verification + deploy

**What / Why / Verify:** Prove mastery shows and generation is performance-aware, then ship.

**Files:** none (verification + deploy).

- [ ] **Step 1: Full local sweep** — `.venv/bin/pytest -q` PASS; `cd frontend && node --test` PASS.

- [ ] **Step 2: Confirm the Pi's Claude login works** (generation needed for the e2e):
```
mcp__pi-ssh__exec: env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN HOME=/home/werner PATH=/home/werner/.local/bin:$PATH timeout 60 claude -p 'Reply with ONLY {"ok": true}' --output-format json --model claude-sonnet-4-6
```
Expected `is_error:false`. Also check `uptime` — if Pi load is very high (houston still heavy),
note it; generation may be slow.

- [ ] **Step 3: Deploy**
```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then `mcp__pi-ssh__sudo-exec: systemctl restart claude-university` and confirm `is-active`.

- [ ] **Step 4: Real-browser check (Playwright, `http://100.99.33.106:8200/`)**
1. Create a tiny course; complete its first lesson and give a recall rating; answer its checks
   (mix right/wrong). (If generation is slow under Pi load, a lesson JSON can be written directly
   into `content/courses/<id>/lessons/<id>-l1.json` on the Pi to exercise the render/rating path.)
2. Return to the course dashboard → confirm a **Mastery** breakdown appears reflecting that lesson.
3. Confirm `GET /api/courses/<id>` returns `mastery` + `masteryCounts`:
   `mcp__pi-ssh__exec: curl -s http://localhost:8200/api/courses/<id> | python3 -m json.tool | head`.
4. (Adaptivity) After the history exists, open the **next** lesson so it generates; confirm in the
   service log or by inspecting that generation ran with a performance line — simplest check: the
   `performance_summary` is non-empty for that course (can be asserted via a quick Python one-liner
   on the Pi against the live DB, or trust the unit test + confirm the lesson generated OK).
5. Remove the throwaway course on the Pi; confirm the university is empty.

- [ ] **Step 5: Confirm service active + enabled.**

---

## Self-Review

**1. Spec coverage:** mastery levels (T1), accuracy gate (T1), performance summary (T1),
generation adaptivity (T2), API exposure + JIT performance (T3), dashboard surface (T4), e2e (T5).
All spec sections map to a task.

**2. Placeholder scan:** No TBD/TODO. T3/T4 say "match the existing fixture/structure" with the
exact keys and markup required — concrete, because they touch existing files whose style must be
followed; the asserted shapes (`masteryCounts` keys, `mastery`/`masteryCounts` body keys, `.mastery`
markup) are exact.

**3. Type consistency:** `LEVELS` order and the four level strings are identical across mastery.py
(T1), the API `masteryCounts` (T3), and the dashboard labels (T4). `performance` kwarg name matches
across `lesson_prompt`/`ensure_lesson` (T2) and the `get_lesson` call (T3). `lesson_check` payload
`{index,type,correct}` (Slice 5) is what `_checks_by_lesson` reads (T1).
