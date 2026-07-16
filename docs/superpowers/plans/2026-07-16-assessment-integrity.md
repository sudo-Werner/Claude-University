# Assessment-Integrity Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the assessment story: graded capstones with rubrics, corrective-then-reassess retake gating, apply-level free-response practice in gap reviews, prerequisite-graph consumers, and transcript attempt/capstone rows.

**Architecture:** Five spec items (A-E) land as seven tasks. A new `backend/capstone.py` mirrors `backend/exams.py` (prompt builders + validators + server-recorded result events); `backend/remediation.py` gains apply items and a session-completion detector that gates exam retakes in `start_exam`; the frontend consumes all of it through the existing view-function + `paint*` repaint pattern in `frontend/src/app.js`.

**Tech Stack:** Flask + sqlite (events table), Claude CLI via `backend/claude_client.py` (`run_structured(prompt, validate=...)`), vanilla-JS ES modules with string-template views, pytest + `node --test`.

**Spec:** `docs/superpowers/specs/2026-07-16-assessment-integrity-batch-design.md` (approved 2026-07-16).

## Global Constraints

- Backend tests: `.venv/bin/pytest -q` (run from repo root)
- Frontend tests: `node --test frontend/tests/*.test.js` (NEVER the bare directory — it silently runs nothing)
- After any app.js change: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
- Sanitization boundary: server-sanitized HTML fields render RAW client-side; learner-typed text and client-forgeable payload-derived plain text is esc()'d client-side / html.escape'd server-side at stamp time
- All new event reads guard against malformed payloads (forged events must never 500 a route)
- The events DB column is event_type (not type); payload is a JSON string; queries order by occurred_at ASC, id ASC where latest-wins matters
- No emojis anywhere. Commit after each task with message ending: Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
- Legacy-data safety on the Pi: cached capstones without rubric, remediation sessions without apply, remediation events without examKey/attempt markers must all be handled per spec

**Ambiguities resolved against the code (spec wording vs. real signatures):**

1. Spec writes `remediation.session_completed(conn, course_id, exam_key)`. The stored session lives on disk under the content dir and "the Fix-the-gaps session **for the latest failed attempt**" must be the one checked, so the real signature is `session_completed(conn, content_dir, course_id, exam_key, expected_attempt)` — a stale session (older attempt than the latest fail) counts as absent.
2. Spec writes `generation.grade_prompt(..., explanation=answer)`. The real keyword is `answer` (`grade_prompt(*, prompt_html, solution_ans, solution_note, answer)`); it expresses the apply-grading need as-is, so no new prompt builder is added.
3. `valid_rubric(items)` validates the criterion LIST per spec, but `claude_client.extract_json` only parses JSON objects, so the rubric prompt demands `{"rubric": [...]}` and callers validate with `lambda o: isinstance(o, dict) and valid_rubric(o.get("rubric"))`.
4. `backend/app.py` `get_capstone` has a local variable named `capstone` — after Task 2 imports the `capstone` module, that local shadows it inside `get_capstone` only, which never references the module. Do NOT rename anything there; the new submit route uses distinct local names.
5. The spec's stats change ("activity label like exam entries") is dead data unless the activity view renders it, so Task 2 adds the matching `capstone_result` branch to `frontend/src/views/activity.js`.
6. Exam-result fail screens keep the retake button when there are no weak spots (`latest_failed_result` returns None for such fails, so the backend gate allows the retake; hiding the button would strand the learner).

---

### Task 1: backend/capstone.py — rubric, grading, scoring, recording

**Files:**
- Create: `backend/capstone.py`
- Create: `tests/test_capstone.py`

**Interfaces:**
- Consumes: `generation.sanitize_html(value)`, `generation._gen_lock(key)`, `events.insert_events(conn, [...])`, `fsutil.write_text_atomic(path, text)`
- Produces (Task 2 relies on these exact names):
  - `CAPSTONE_PASS = 0.7`
  - `load_capstone(content_dir, course_id, scope) -> dict | None`
  - `valid_rubric(items) -> bool` (validates the criterion list)
  - `rubric_prompt(*, capstone, objective_texts, scope_title) -> str`
  - `ensure_rubric(content_dir, course_id, scope, capstone, manifest, *, generate) -> dict` — `generate(prompt, validate)` callable
  - `capstone_grade_prompt(*, capstone, rubric, work, scope_label) -> str`
  - `valid_capstone_grade(obj, rubric) -> bool`
  - `score_grade(per_criterion) -> float`
  - `record_result(conn, course_id, scope, result) -> int` (the stamped attempt)
  - `submit_capstone(content_dir, conn, course_id, scope, work, *, manifest, generate) -> dict | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capstone.py`:

```python
import json

from backend import capstone, db, events


def _conn():
    conn = db.get_connection(":memory:")
    db.init_db(conn)
    return conn


def _manifest():
    return {"id": "c1", "title": "Course", "brief": "b",
            "outcomes": [{"text": "Do the course thing", "bloom": "apply", "knowledge": "procedural"}],
            "modules": [{"id": "m1", "title": "Mod One",
                         "outcomes": [{"text": "Do X well", "bloom": "apply", "knowledge": "procedural"}],
                         "lessons": [{"id": "c1-l1", "title": "L1"}]}]}


def _capstone(scope="m1", title="Mod One"):
    return {"scope": scope, "title": title, "intro": "Real world.",
            "items": [{"title": "AlphaFold", "detail": "d", "source": "s"},
                      {"title": "GPS", "detail": "d", "source": "s"}]}


RUBRIC4 = [{"criterion": f"Criterion {i}"} for i in range(4)]


def _grade(mets, summary="Overall solid."):
    return {"perCriterion": [
        {"index": i, "met": m, "note": "Shows it.", "evidence": "a quote"}
        for i, m in enumerate(mets)], "summary": summary}


def _fake_generate(rubric_obj, grade_obj):
    calls = []

    def gen(prompt, validate):
        calls.append(prompt)
        obj = grade_obj if '"perCriterion"' in prompt else rubric_obj
        assert validate(obj)
        return obj

    gen.calls = calls
    return gen


def _write_capstone(tmp_path, cap, scope="m1"):
    p = tmp_path / "c1" / "capstones" / f"{scope}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap))
    return p


def test_valid_rubric_bounds_and_shapes():
    assert capstone.valid_rubric(RUBRIC4)
    assert capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(6)])
    assert not capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(3)])   # too few
    assert not capstone.valid_rubric([{"criterion": f"C{i}"} for i in range(7)])   # too many
    assert not capstone.valid_rubric([{"criterion": ""}] * 4)                       # empty text
    assert not capstone.valid_rubric([{"criterion": "ok"}] * 3 + ["not a dict"])
    assert not capstone.valid_rubric("nope")
    assert not capstone.valid_rubric(None)                                          # legacy: no rubric


def test_load_capstone_missing_and_corrupt(tmp_path):
    assert capstone.load_capstone(tmp_path, "c1", "m1") is None
    p = _write_capstone(tmp_path, _capstone())
    assert capstone.load_capstone(tmp_path, "c1", "m1")["title"] == "Mod One"
    p.write_text("{nope")
    assert capstone.load_capstone(tmp_path, "c1", "m1") is None


def test_ensure_rubric_upgrades_legacy_file_and_escapes(tmp_path):
    _write_capstone(tmp_path, _capstone())          # legacy Pi cache: no rubric field
    gen = _fake_generate({"rubric": [{"criterion": "Uses <b>real</b> data"}] + RUBRIC4[:3]}, None)
    cap = capstone.load_capstone(tmp_path, "c1", "m1")
    out = capstone.ensure_rubric(tmp_path, "c1", "m1", cap, _manifest(), generate=gen)
    assert len(out["rubric"]) == 4
    assert out["rubric"][0]["criterion"] == "Uses &lt;b&gt;real&lt;/b&gt; data"     # plain-text escaped
    assert "AlphaFold" in gen.calls[0] and "Do X well" in gen.calls[0]              # items + module objectives
    saved = json.loads((tmp_path / "c1" / "capstones" / "m1.json").read_text())
    assert saved["rubric"] == out["rubric"]                                          # persisted upgrade
    assert saved["items"] == cap["items"]                                            # extended, not regenerated


def test_ensure_rubric_course_scope_uses_course_outcomes(tmp_path):
    _write_capstone(tmp_path, _capstone(scope="course", title="Course"), scope="course")
    gen = _fake_generate({"rubric": RUBRIC4}, None)
    cap = capstone.load_capstone(tmp_path, "c1", "course")
    capstone.ensure_rubric(tmp_path, "c1", "course", cap, _manifest(), generate=gen)
    assert "Do the course thing" in gen.calls[0]


def test_ensure_rubric_skips_generation_when_valid_rubric_present(tmp_path):
    cap = {**_capstone(), "rubric": RUBRIC4}
    _write_capstone(tmp_path, cap)
    gen = _fake_generate(None, None)
    out = capstone.ensure_rubric(tmp_path, "c1", "m1", cap, _manifest(), generate=gen)
    assert out["rubric"] == RUBRIC4 and gen.calls == []


def test_valid_capstone_grade_matrix():
    ok = _grade(["met", "partial", "unmet", "met"])
    assert capstone.valid_capstone_grade(ok, RUBRIC4)
    empty_evidence = _grade(["met", "met", "met", "met"])
    empty_evidence["perCriterion"][2]["evidence"] = ""
    assert capstone.valid_capstone_grade(empty_evidence, RUBRIC4)   # empty evidence allowed
    assert not capstone.valid_capstone_grade({"perCriterion": ok["perCriterion"][:3],
                                              "summary": "s"}, RUBRIC4)             # wrong count
    dup = json.loads(json.dumps(ok)); dup["perCriterion"][1]["index"] = 0
    assert not capstone.valid_capstone_grade(dup, RUBRIC4)                            # duplicate index
    out_of_range = json.loads(json.dumps(ok)); out_of_range["perCriterion"][3]["index"] = 9
    assert not capstone.valid_capstone_grade(out_of_range, RUBRIC4)
    bad_met = json.loads(json.dumps(ok)); bad_met["perCriterion"][0]["met"] = "kinda"
    assert not capstone.valid_capstone_grade(bad_met, RUBRIC4)
    no_note = json.loads(json.dumps(ok)); no_note["perCriterion"][0]["note"] = " "
    assert not capstone.valid_capstone_grade(no_note, RUBRIC4)
    no_evidence = json.loads(json.dumps(ok)); del no_evidence["perCriterion"][0]["evidence"]
    assert not capstone.valid_capstone_grade(no_evidence, RUBRIC4)                    # evidence mandatory
    no_summary = json.loads(json.dumps(ok)); no_summary["summary"] = ""
    assert not capstone.valid_capstone_grade(no_summary, RUBRIC4)
    assert not capstone.valid_capstone_grade("nope", RUBRIC4)


def test_score_grade_and_threshold():
    assert capstone.CAPSTONE_PASS == 0.7
    per = _grade(["met", "met", "partial", "unmet"])["perCriterion"]
    assert capstone.score_grade(per) == 0.625                                        # (1+1+.5+0)/4
    exact = _grade(["met", "met", "met", "partial", "unmet"])["perCriterion"]
    assert capstone.score_grade(exact) == 0.7                                        # 3.5/5, passes at >=
    assert capstone.score_grade(_grade(["met"] * 4)["perCriterion"]) == 1.0


def test_record_result_stamps_attempts_and_drops_evidence():
    conn = _conn()
    result = {"scope": "m1", "score": 1.0, "passed": True, "summary": "s",
              "perCriterion": [{"index": 0, "met": "met", "note": "n", "evidence": "quote"}]}
    assert capstone.record_result(conn, "c1", "m1", result) == 1
    assert capstone.record_result(conn, "c1", "m1", result) == 2
    assert capstone.record_result(conn, "c1", "course", result) == 1                 # per-scope counter
    rows = conn.execute(
        "SELECT payload FROM events WHERE event_type = 'capstone_result' "
        "AND course_id = 'c1' AND topic_id = 'm1' ORDER BY id ASC").fetchall()
    payloads = [json.loads(r["payload"]) for r in rows]
    assert [p["attempt"] for p in payloads] == [1, 2]
    assert payloads[0]["perCriterion"][0] == {"index": 0, "met": "met", "note": "n"}  # no evidence stored


def test_submit_capstone_none_without_file(tmp_path):
    conn = _conn()
    gen = _fake_generate({"rubric": RUBRIC4}, _grade(["met"] * 4))
    assert capstone.submit_capstone(tmp_path, conn, "c1", "m1", "work",
                                    manifest=_manifest(), generate=gen) is None
    assert gen.calls == []


def test_submit_capstone_happy_path_sanitizes_and_records(tmp_path):
    conn = _conn()
    _write_capstone(tmp_path, _capstone())
    grade = _grade(["met", "met", "met", "partial"], summary="Good <script>x</script> work")
    grade["perCriterion"][0]["note"] = "Nice <script>alert(1)</script> start"
    gen = _fake_generate({"rubric": RUBRIC4}, grade)
    out = capstone.submit_capstone(tmp_path, conn, "c1", "m1", "my work",
                                   manifest=_manifest(), generate=gen)
    assert out["score"] == 0.875 and out["passed"] is True and out["attempt"] == 1
    assert out["scope"] == "m1" and len(out["rubric"]) == 4
    assert out["perCriterion"][0]["evidence"] == "a quote"                            # API keeps evidence
    assert "<script>" not in out["perCriterion"][0]["note"]                           # sanitized
    assert "<script>" not in out["summary"]
    assert len(gen.calls) == 2                                                        # rubric, then grade
    row = conn.execute("SELECT payload FROM events WHERE event_type = 'capstone_result'").fetchone()
    assert json.loads(row["payload"])["attempt"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_capstone.py`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'capstone'`

- [ ] **Step 3: Write the implementation**

Create `backend/capstone.py`:

```python
"""Graded capstone (assessment-integrity Item A): rubric + submission grading.

The exploration capstone (generation.ensure_capstone) stays read-only; this module
adds the assessment half: a rubric stamped into the cached capstone JSON on first
need (read-time upgrade — legacy caches on the Pi are only extended, never
regenerated), a rubric-based grading call, and a server-recorded capstone_result
event. Capstone results are transcript-only credit: they feed neither the mastery
accuracy pool nor course_passed (courses on the Pi must not retroactively lock).
"""

import html as _html
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import events, fsutil, generation

CAPSTONE_PASS = 0.7

_MET_VALUES = ("met", "partial", "unmet")
_MET_POINTS = {"met": 1.0, "partial": 0.5, "unmet": 0.0}


def _capstone_path(content_dir, course_id, scope):
    return Path(content_dir) / course_id / "capstones" / f"{scope}.json"


def load_capstone(content_dir, course_id, scope):
    path = _capstone_path(content_dir, course_id, scope)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("items"), list) else None


def valid_rubric(items):
    if not (isinstance(items, list) and 4 <= len(items) <= 6):
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        if not (isinstance(it.get("criterion"), str) and it["criterion"].strip()):
            return False
    return True


def _scope_objective_texts(manifest, scope):
    """Objective texts for the rubric prompt: course outcomes for scope="course",
    module outcomes otherwise. Tolerates both objective dicts (schema v2) and the
    legacy plain-string module outcomes that exam_prompt already handles."""
    if scope == "course":
        objs = manifest.get("outcomes", []) or []
    else:
        module = next((m for m in manifest.get("modules", []) if m.get("id") == scope), None)
        objs = (module or {}).get("outcomes", []) or []
    out = []
    for o in objs:
        text = o.get("text") if isinstance(o, dict) else o
        if isinstance(text, str) and text.strip():
            out.append(text)
    return out


def rubric_prompt(*, capstone, objective_texts, scope_title):
    items = "; ".join(
        f'{it.get("title", "")}: {it.get("detail", "")}'
        for it in capstone.get("items", []) if isinstance(it, dict))
    objectives = "; ".join(objective_texts)
    return (
        f'You are writing the assessment RUBRIC for a capstone titled "{scope_title}" '
        "on a personal learning platform. The learner will submit a piece of their own "
        "work applying what they studied; the rubric is what that work is judged "
        "against.\n"
        f"The capstone's real-world connections: {items}\n"
        + (f"The objectives this scope taught: {objectives}\n" if objectives else "")
        + "Write 4 to 6 rubric criteria. Each criterion is ONE assessable sentence — a "
        "concrete, observable quality a grader can find evidence for in the submission "
        "(never 'understands' or 'appreciates'). Reply with ONLY a JSON object, no "
        'prose, no fence:\n{"rubric":[{"criterion":"<one assessable sentence>"}]}'
    )


def ensure_rubric(content_dir, course_id, scope, capstone, manifest, *, generate):
    """Stamp a rubric into the cached capstone JSON on first need (read-time upgrade,
    same pattern as generation._with_refreshed_source_types: legacy caches on the Pi
    are only extended, never regenerated). generate(prompt, validate) -> dict.
    Criteria are plain text: html.escape'd here, rendered raw client-side."""
    if valid_rubric(capstone.get("rubric")):
        return capstone
    prompt = rubric_prompt(
        capstone=capstone,
        objective_texts=_scope_objective_texts(manifest, scope),
        scope_title=capstone.get("title", ""),
    )
    obj = generate(prompt, lambda o: isinstance(o, dict) and valid_rubric(o.get("rubric")))
    capstone["rubric"] = [
        {"criterion": _html.escape(r["criterion"], quote=True)} for r in obj["rubric"]
    ]
    path = _capstone_path(content_dir, course_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(capstone, indent=2, ensure_ascii=False))
    return capstone


def capstone_grade_prompt(*, capstone, rubric, work, scope_label):
    criteria = "\n".join(f'{i}. {r["criterion"]}' for i, r in enumerate(rubric))
    return (
        "You are a fair, rigorous grader assessing a learner's capstone submission "
        f"for {scope_label} on a personal learning platform. Judge the submission "
        "against each rubric criterion — nothing else.\n"
        f"Capstone brief: {capstone.get('intro', '')}\n"
        f"Rubric criteria, by index:\n{criteria}\n\n"
        f"Learner's submission:\n{work}\n\n"
        "Grade EVERY criterion, in order. For each criterion include evidence: a "
        "short verbatim quote from the submission that your verdict rests on (empty "
        "string only if the submission contains nothing relevant to the criterion). "
        "Base each verdict only on what the evidence shows.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"perCriterion":[{"index":<criterion index>,"met":"met"|"partial"|"unmet",'
        '"note":"<one sentence addressed to \'you\': what the submission shows for '
        'this criterion and what would lift it>","evidence":"<verbatim quote from '
        'the submission, empty if none>"}],"summary":"<two or three sentences '
        "addressed to 'you': overall strengths, then the most important "
        'improvement>"}'
    )


def valid_capstone_grade(obj, rubric):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("summary"), str) and obj["summary"].strip()):
        return False
    per = obj.get("perCriterion")
    if not (isinstance(per, list) and len(per) == len(rubric)):
        return False
    seen = set()
    for g in per:
        if not isinstance(g, dict) or g.get("met") not in _MET_VALUES:
            return False
        if not (isinstance(g.get("note"), str) and g["note"].strip()):
            return False
        if not isinstance(g.get("evidence"), str):
            return False
        idx = g.get("index")
        if not (isinstance(idx, int) and not isinstance(idx, bool)) or idx in seen:
            return False
        seen.add(idx)
    return seen == set(range(len(rubric)))


def score_grade(per_criterion):
    points = sum(_MET_POINTS[g["met"]] for g in per_criterion)
    return round(points / len(per_criterion), 4)


def record_result(conn, course_id, scope, result):
    """Server-recorded capstone_result (mirror of exams.record_result). Stored
    perCriterion entries keep met/note but drop evidence — the quote is a grading
    reliability lever, not learner state (same rule as exam grading)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE event_type = 'capstone_result' AND course_id = ? AND topic_id = ?",
        (course_id, scope),
    ).fetchone()
    attempt = row["n"] + 1
    stored = [{"index": g["index"], "met": g["met"], "note": g["note"]}
              for g in result["perCriterion"]]
    events.insert_events(conn, [{
        "client_event_id": f"server-{uuid.uuid4()}",
        "session_id": "server",
        "device": "server",
        "topic_id": scope,
        "course_id": course_id,
        "event_type": "capstone_result",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"scope": scope, "score": result["score"], "passed": result["passed"],
                    "perCriterion": stored, "summary": result["summary"],
                    "attempt": attempt},
    }])
    return attempt


def submit_capstone(content_dir, conn, course_id, scope, work, *, manifest, generate):
    """Grade a capstone submission against its (ensured) rubric and record the
    result. Returns the graded result dict (with rubric and evidence, for the API
    response), or None when no capstone has been generated yet. Lets ClaudeError
    propagate — the route maps it to 502/503 exactly like the exam grader."""
    with generation._gen_lock(("capstone", course_id, scope)):
        capstone = load_capstone(content_dir, course_id, scope)
        if capstone is None:
            return None
        capstone = ensure_rubric(content_dir, course_id, scope, capstone, manifest,
                                 generate=generate)
    rubric = capstone["rubric"]
    scope_label = ("the whole course" if scope == "course"
                   else f'the module "{capstone.get("title", "")}"')
    graded = generate(
        capstone_grade_prompt(capstone=capstone, rubric=rubric, work=work,
                              scope_label=scope_label),
        lambda o: valid_capstone_grade(o, rubric),
    )
    per = sorted(graded["perCriterion"], key=lambda g: g["index"])
    per = [{"index": g["index"], "met": g["met"],
            "note": generation.sanitize_html(g["note"]),
            "evidence": g["evidence"]} for g in per]
    score = score_grade(per)
    result = {
        "scope": scope,
        "score": score,
        "passed": score >= CAPSTONE_PASS,
        "perCriterion": per,
        "summary": generation.sanitize_html(graded["summary"]),
    }
    result["attempt"] = record_result(conn, course_id, scope, result)
    result["rubric"] = rubric
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_capstone.py`
Expected: all PASS

Run the full backend suite to prove nothing regressed: `.venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/capstone.py tests/test_capstone.py
git commit -m "feat(capstone): rubric ensure/validate, grading, scoring, capstone_result recording

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Capstone submit route + stats whitelisting + activity label

**Files:**
- Modify: `backend/app.py` (import line 6; new route after `get_capstone`, i.e. after line 386)
- Modify: `backend/stats.py` (STUDY_EVENTS line 9, ACTIVITY_EVENTS line 14, label block lines 95-101)
- Modify: `frontend/src/views/activity.js` (new branch after the `remediation_started` branch, line 35)
- Test: `tests/test_courses_api.py` (append), `tests/test_stats.py` (append), `frontend/tests/activity.test.js` (append)

**Interfaces:**
- Consumes (Task 1): `capstone.submit_capstone(content_dir, conn, course_id, scope, work, *, manifest, generate)` -> dict | None
- Produces: `POST /api/courses/<cid>/capstone/<scope>/submit` with `{"work": "<str>"}` -> 200 result / 400 empty work / 404 missing course-or-capstone / 502 ClaudeError / 503 reauth. `capstone_result` counted in streaks and labeled in the activity feed.

- [ ] **Step 1: Write the failing backend route tests**

Append to `tests/test_courses_api.py` (after the existing capstone tests; `_client` and `_capstone_course` already exist in this file):

```python
def _capstone_file(root, cid, scope, title):
    cap = {"scope": scope, "title": title, "intro": "i", "items": [
        {"title": "A", "detail": "d", "source": "s"},
        {"title": "B", "detail": "d", "source": "s"}]}
    p = root / cid / "capstones" / f"{scope}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap))
    return cap


def _capstone_generate():
    rubric = {"rubric": [{"criterion": f"C{i}"} for i in range(4)]}
    grade = {"perCriterion": [
        {"index": i, "met": "met", "note": "n", "evidence": "q"} for i in range(4)],
        "summary": "s"}

    def fake(prompt, *, validate=None, **kw):
        obj = grade if '"perCriterion"' in prompt else rubric
        assert validate is None or validate(obj)
        return obj
    return fake


def test_capstone_submit_grades_and_records(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")
    monkeypatch.setattr(claude_client, "run_structured", _capstone_generate())
    r = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "my project"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["score"] == 1.0 and body["passed"] is True and body["attempt"] == 1
    assert len(body["rubric"]) == 4
    assert body["perCriterion"][0]["evidence"] == "q"           # response keeps evidence
    saved = json.loads((tmp_path / cid / "capstones" / f"{mid}.json").read_text())
    assert len(saved["rubric"]) == 4                            # read-time upgrade persisted
    r2 = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "more"})
    assert r2.get_json()["attempt"] == 2                        # unlimited attempts
    ev = client.get("/api/events?type=capstone_result").get_json()["events"]
    assert len(ev) == 2
    assert "evidence" not in ev[0]["payload"]["perCriterion"][0]  # never stored


def test_capstone_submit_requires_work(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={}).status_code == 400
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "  "}).status_code == 400


def test_capstone_submit_404_without_generated_capstone(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "w"}).status_code == 404
    assert client.post("/api/courses/nope/capstone/m1/submit",
                       json={"work": "w"}).status_code == 404


def test_capstone_submit_maps_claude_errors(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, mid = _capstone_course(courses, tmp_path)
    cid = manifest["id"]
    _capstone_file(tmp_path, cid, mid, "Mod A")

    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/capstone/{mid}/submit",
                       json={"work": "w"}).status_code == 502

    def auth_boom(prompt, **kw):
        raise claude_client.ClaudeAuthError("login")
    monkeypatch.setattr(claude_client, "run_structured", auth_boom)
    r = client.post(f"/api/courses/{cid}/capstone/{mid}/submit", json={"work": "w"})
    assert r.status_code == 503 and r.get_json()["code"] == "reauth"
```

- [ ] **Step 2: Write the failing stats tests**

Append to `tests/test_stats.py` (helpers `_ev`, `TODAY`, `conn` fixture already exist there):

```python
def test_capstone_result_counts_toward_streak(conn):
    events.insert_events(conn, [_ev(1, "capstone_result", "2026-07-15T09:00:00+00:00",
                                    topic_id="m1")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_activity_labels_capstone_results(conn, tmp_path):
    root = tmp_path / "courses"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "course.json").write_text(json.dumps({
        "id": "c1", "title": "Algo", "modules": [
            {"id": "m1", "title": "Sorting", "lessons": [{"id": "c1-l1", "title": "L1"}]}],
    }))
    ev = _ev(1, "capstone_result", "2026-07-15T09:00:00+00:00", topic_id="m1")
    ev["payload"] = {"scope": "m1", "score": 0.75, "passed": True, "attempt": 1}
    cv = _ev(2, "capstone_result", "2026-07-15T10:00:00+00:00", topic_id="course")
    cv["payload"] = {"scope": "course", "score": 0.5, "passed": False, "attempt": 1}
    events.insert_events(conn, [ev, cv])
    entries = stats.recent_activity(conn, root)
    assert entries[0]["examLabel"] == "Course capstone"
    assert entries[0]["score"] == 0.5 and entries[0]["passed"] is False
    assert entries[1]["examLabel"] == "Sorting capstone"
    assert entries[1]["passed"] is True
```

- [ ] **Step 3: Write the failing frontend activity test**

Append to `frontend/tests/activity.test.js`:

```js
test("capstone_result entries show label, score, and outcome", () => {
  const html = activityHTML([
    { occurredAt: "2026-07-16T10:00:00+00:00", type: "capstone_result",
      courseTitle: "Algo", examLabel: "Sorting capstone", score: 0.75, passed: true },
  ], { now: new Date("2026-07-16T12:00:00+00:00") });
  assert.ok(html.includes("<b>Capstone</b>"));
  assert.ok(html.includes("Sorting capstone"));
  assert.ok(html.includes("75%"));
  assert.ok(html.includes("passed"));
});
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_courses_api.py tests/test_stats.py`
Expected: new tests FAIL (404 on the submit route; streak 0; missing examLabel)

Run: `node --test frontend/tests/*.test.js`
Expected: the new activity test FAILS (no Capstone branch)

- [ ] **Step 5: Implement the route**

In `backend/app.py`, extend the import (line 6) to end with `, capstone`:

```python
from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats, exams, spine, remediation, transcript, capstone
```

Add after the `get_capstone` route (after line 386):

```python
    @app.post("/api/courses/<course_id>/capstone/<scope>/submit")
    def submit_capstone_route(course_id, scope):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        if scope != "course" and not _ID_RE.match(scope):
            return jsonify({"error": "not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        work = (body.get("work") or "").strip()
        if not work:
            return jsonify({"error": "work is required"}), 400
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        conn = db.get_connection(path)
        try:
            result = capstone.submit_capstone(
                courses.CONTENT_DIR, conn, course_id, scope, work,
                manifest=manifest, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade your capstone — your work was not lost, try again"}), 502
        finally:
            conn.close()
        if result is None:
            return jsonify({"error": "no capstone to submit against — open the capstone first"}), 404
        return jsonify(result)
```

- [ ] **Step 6: Implement the stats whitelisting + label**

In `backend/stats.py` replace the two tuples (lines 9-15):

```python
STUDY_EVENTS = ("lesson_view", "lesson_reviewed", "prequiz_attempt",
                "exam_result", "remediation_started", "capstone_result")

# Event types worth showing in the study log. Checks, hints, and timer ticks
# are noise at log granularity and are filtered out here, server-side.
ACTIVITY_EVENTS = ("lesson_view", "lesson_reviewed", "course_created", "course_revised",
                   "exam_result", "remediation_started", "capstone_result")
```

In `recent_activity`, replace the label block (lines 95-101):

```python
        if r["event_type"] in ("exam_result", "remediation_started", "capstone_result"):
            key = r["topic_id"]
            if r["event_type"] == "capstone_result":
                entry["examLabel"] = ("Course capstone" if key == "course"
                                      else f'{module_titles.get(key, "Module")} capstone')
            else:
                entry["examLabel"] = ("Final exam" if key == "final"
                                      else f'{module_titles.get(key, "Module")} exam')
            if r["event_type"] in ("exam_result", "capstone_result"):
                entry["score"] = payload.get("score")
                entry["passed"] = bool(payload.get("passed"))
```

- [ ] **Step 7: Implement the activity view branch**

In `frontend/src/views/activity.js`, insert after the `remediation_started` branch (after line 35):

```js
  if (e.type === "capstone_result") {
    const pct = Math.round((e.score || 0) * 100);
    return `<div class="act-entry"><span class="act-time">${when}</span>` +
      `<span class="act-text"><b>Capstone</b> ${esc(e.examLabel || "")} ` +
      `<span class="act-course">${esc(e.courseTitle || "")}</span>` +
      `<span class="act-quality">${pct}% — ${e.passed ? "passed" : "not passed"}</span></span></div>`;
  }
```

- [ ] **Step 8: Run all tests to verify they pass**

Run: `.venv/bin/pytest -q`
Expected: all PASS

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app.py backend/stats.py frontend/src/views/activity.js tests/test_courses_api.py tests/test_stats.py frontend/tests/activity.test.js
git commit -m "feat(capstone): submit route + capstone_result in streaks and activity feed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Remediation apply items — generation, validation, grade route

**Files:**
- Modify: `backend/remediation.py` (`remediation_prompt` lines 59-87, `valid_remediation` lines 90-106, `finalize_session` lines 109-137)
- Modify: `backend/app.py` (new route after `start_remediation`, i.e. after line 334)
- Test: `tests/test_remediation.py` (update `_gaps` + new tests), `tests/test_courses_api.py` (update the `gaps` fixture in `test_remediation_generates_serves_and_reuses` + new route tests)

**Interfaces:**
- Consumes: `generation.grade_prompt(*, prompt_html, solution_ans, solution_note, answer)`, `generation.valid_grade(obj)`, `generation.sanitize_html(value)`, `remediation.load_session(content_dir, course_id, exam_key)`
- Produces:
  - Fresh sessions carry, per gap: `gap["apply"] = {"prompt": <sanitized html>, "modelAnswer": <sanitized html>}`. Legacy sessions on disk lack `apply` — every consumer (Tasks 4 and 5) treats it as optional.
  - `POST /api/courses/<cid>/exams/<exam_key>/remediation/grade` with `{"gapIndex": <int>, "answer": "<str>"}` -> `{"verdict", "note", "modelAnswer"}` / 404 no session / 400 bad gapIndex, gap without apply, or empty answer / 502 / 503.

- [ ] **Step 1: Update fixtures and write the failing module tests**

In `tests/test_remediation.py`, replace the `_gaps` helper (lines 30-39) so every generated gap carries `apply` (the validator becomes strict for NEW generations):

```python
def _gaps(weak):
    return {"gaps": [{
        "lessonId": w["lessonId"],
        "explanationHtml": "<p>An analogy.</p>",
        "practice": [
            {"type": "mcq", "prompt": "<p>Q</p>", "choices": ["a", "b", "c"],
             "answer": 1, "explanation": "because"},
            {"type": "fill", "prompt": "Blank?", "answer": "word", "explanation": "why"},
        ],
        "apply": {"prompt": "<p>A novel scenario.</p>", "modelAnswer": "Covers X and Y."},
    } for w in weak]}
```

Append new tests to `tests/test_remediation.py`:

```python
def test_prompt_demands_apply_item_with_novel_scenario():
    p = remediation.remediation_prompt(manifest=_manifest(), exam_key="m1",
                                       weak_spots=WEAK, spine_lessons={})
    assert '"apply"' in p and '"modelAnswer"' in p
    assert "NOVEL scenario, case, or problem that does not appear in the lessons" in p


def test_valid_remediation_requires_apply_on_new_generations():
    good = _gaps(WEAK)
    assert remediation.valid_remediation(good, WEAK)
    missing = json.loads(json.dumps(good)); del missing["gaps"][0]["apply"]
    assert not remediation.valid_remediation(missing, WEAK)
    empty = json.loads(json.dumps(good)); empty["gaps"][0]["apply"]["prompt"] = " "
    assert not remediation.valid_remediation(empty, WEAK)
    no_model = json.loads(json.dumps(good)); no_model["gaps"][0]["apply"]["modelAnswer"] = ""
    assert not remediation.valid_remediation(no_model, WEAK)


def test_finalize_sanitizes_apply_fields():
    raw = _gaps(WEAK)
    raw["gaps"][0]["apply"] = {"prompt": "<p>Scenario <script>x()</script></p>",
                               "modelAnswer": "Covers <script>y()</script> Z"}
    s = remediation.finalize_session(raw, WEAK, "m1", "c1", 2)
    assert "<script>" not in s["gaps"][0]["apply"]["prompt"]
    assert "<script>" not in s["gaps"][0]["apply"]["modelAnswer"]
    assert s["gaps"][1]["apply"]["modelAnswer"] == "Covers X and Y."
```

- [ ] **Step 2: Write the failing route tests**

In `tests/test_courses_api.py`, first update the `gaps` fixture inside `test_remediation_generates_serves_and_reuses` (it asserts `validate(gaps)`, which the stricter validator would now fail). Its dict gains one key:

```python
    gaps = {"gaps": [{"lessonId": lesson_id, "explanationHtml": "<p>angle</p>",
                      "practice": [
                          {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                           "answer": 0, "explanation": "e"},
                          {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
                      ],
                      "apply": {"prompt": "<p>scenario</p>", "modelAnswer": "covers x"}}]}
```

Then append the new route tests:

```python
def _remediation_session_on_disk(root, cid, lesson_id, *, with_apply=True, attempt=1,
                                 exam_key="m1"):
    from backend import remediation
    gap = {"lessonId": lesson_id, "lessonTitle": "A", "objectives": [],
           "explanationHtml": "<p>angle</p>",
           "practice": [
               {"type": "mcq", "prompt": "q", "choices": ["a", "b"],
                "answer": 0, "explanation": "e"},
               {"type": "fill", "prompt": "q2", "answer": "w", "explanation": "e2"},
           ]}
    if with_apply:
        gap["apply"] = {"prompt": "<p>scenario</p>", "modelAnswer": "covers x"}
    session = {"examKey": exam_key, "courseId": cid, "attempt": attempt,
               "generatedAt": "2026-07-16T00:00:00+00:00", "gaps": [gap]}
    remediation.save_session(root, cid, session)
    return session


def test_remediation_grade_returns_verdict_and_model_answer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _remediation_session_on_disk(tmp_path, cid, lesson_id)
    monkeypatch.setattr(claude_client, "run_structured",
                        lambda prompt, **kw: {"verdict": "close",
                                              "note": "Nearly <script>x</script>"})
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "my attempt"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["verdict"] == "close"
    assert "<script>" not in body["note"]                       # sanitized
    assert body["modelAnswer"] == "covers x"                    # revealed only after grading


def test_remediation_grade_statuses(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # 404: no session on disk
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "a"}).status_code == 404
    _remediation_session_on_disk(tmp_path, cid, lesson_id)
    # 400: bad gapIndex shapes
    for bad in [{"gapIndex": 5, "answer": "a"}, {"gapIndex": -1, "answer": "a"},
                {"gapIndex": "0", "answer": "a"}, {"answer": "a"}]:
        assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                           json=bad).status_code == 400
    # 400: empty answer
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "  "}).status_code == 400
    # 502 on Claude failure
    def boom(prompt, **kw):
        raise claude_client.ClaudeError("nope")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    assert client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                       json={"gapIndex": 0, "answer": "a"}).status_code == 502


def test_remediation_grade_400_for_legacy_gap_without_apply(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    _remediation_session_on_disk(tmp_path, cid, lesson_id, with_apply=False)  # legacy Pi session
    r = client.post(f"/api/courses/{cid}/exams/m1/remediation/grade",
                    json={"gapIndex": 0, "answer": "a"})
    assert r.status_code == 400
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_remediation.py tests/test_courses_api.py`
Expected: new tests FAIL (`'"apply"' in p` false; `valid_remediation` accepts the apply-less gap; grade route 404s on every URL)

- [ ] **Step 4: Implement the remediation.py changes**

In `remediation_prompt`, add one bullet after the practice bullet (i.e. after the `"...within the mcq/fill format above.\n"` line) and update the JSON shape line. The middle of the returned string becomes:

```python
        "For each gap:\n"
        "- explanationHtml: re-explain the missed objectives from a DIFFERENT angle than a "
        "textbook lesson would — use an analogy, a worked example, or a contrast with a "
        "common misconception. Do NOT summarize the lesson. 2-4 short paragraphs of simple "
        "HTML (p, em, strong, code, ul/ol/li only).\n"
        f"- practice: {PRACTICE_MIN}-{PRACTICE_MAX} NEW retrieval questions on those "
        "objectives (do not reuse exam wording). Each is either "
        '{"type":"mcq","prompt":"...","choices":["..."],"answer":0,"explanation":"..."} '
        "with 3-4 plausible choices and the 0-based correct answer, or "
        '{"type":"fill","prompt":"...","answer":"<the exact word or short phrase>",'
        '"explanation":"..."}. The explanation says why the answer is right. Where a missed '
        "objective's Bloom level is apply or higher, make its practice question require the "
        "learner to APPLY the objective — a scenario-based stem — not recall a definition, "
        "within the mcq/fill format above.\n"
        "- apply: ONE free-response application task on those objectives: pose a NOVEL "
        "scenario, case, or problem that does not appear in the lessons — the learner must "
        "USE the concept to resolve it, not describe the concept. Shape: "
        '{"prompt":"<the scenario, simple HTML (p, em, strong, code) only>",'
        '"modelAnswer":"<what a correct answer covers>"}.\n'
        "Before emitting, re-answer each mcq question independently from the question text "
        "alone. Confirm the choice at answer is the answer you get, and that no distractor is "
        "also defensibly correct — if one is, rewrite it.\n"
        "Echo each gap's lessonId verbatim.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"gaps":[{"lessonId":"<from gap>","explanationHtml":"<html>","practice":[...],'
        '"apply":{"prompt":"<html>","modelAnswer":"<text>"}}]}'
```

In `valid_remediation`, add before the final `return True` of the loop body (after the practice checks):

```python
        apply = g.get("apply")
        if not isinstance(apply, dict):
            return False
        if not (isinstance(apply.get("prompt"), str) and apply["prompt"].strip()):
            return False
        if not (isinstance(apply.get("modelAnswer"), str) and apply["modelAnswer"].strip()):
            return False
```

In `finalize_session`, the `gaps.append({...})` dict gains one key (fresh generations always validated to carry `apply`; only OLD sessions already on disk lack it):

```python
        gaps.append({
            "lessonId": w["lessonId"],
            "lessonTitle": w.get("lessonTitle", ""),
            "objectives": [o for o in w.get("objectives", []) if isinstance(o, str)],
            "explanationHtml": generation.sanitize_html(g["explanationHtml"]),
            "practice": practice,
            "apply": {
                "prompt": generation.sanitize_html(g["apply"]["prompt"]),
                "modelAnswer": generation.sanitize_html(g["apply"]["modelAnswer"]),
            },
        })
```

- [ ] **Step 5: Implement the grade route**

In `backend/app.py`, add after the `start_remediation` route (after line 334):

```python
    @app.post("/api/courses/<course_id>/exams/<exam_key>/remediation/grade")
    def grade_remediation_apply(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        session = remediation.load_session(courses.CONTENT_DIR, course_id, exam_key)
        if session is None:
            return jsonify({"error": "no gap review on record for this exam"}), 404
        body = request.get_json(silent=True) or {}
        gap_index = body.get("gapIndex")
        gaps = session.get("gaps", [])
        if not (isinstance(gap_index, int) and not isinstance(gap_index, bool)
                and 0 <= gap_index < len(gaps)):
            return jsonify({"error": "gapIndex must identify a gap in the review"}), 400
        gap = gaps[gap_index] if isinstance(gaps[gap_index], dict) else {}
        apply_item = gap.get("apply")
        # Legacy sessions on the Pi predate apply items — nothing to grade there.
        if not (isinstance(apply_item, dict)
                and isinstance(apply_item.get("prompt"), str) and apply_item["prompt"].strip()):
            return jsonify({"error": "this gap has no apply task"}), 400
        answer = body.get("answer")
        answer = answer.strip() if isinstance(answer, str) else ""
        if not answer:
            return jsonify({"error": "answer is required"}), 400
        # Reuse the exercise grader verbatim (verdict trio + note) — no new prompt builder.
        prompt = generation.grade_prompt(
            prompt_html=apply_item.get("prompt", ""),
            solution_ans=apply_item.get("modelAnswer", ""),
            solution_note="",
            answer=answer,
        )
        try:
            result = claude_client.run_structured(prompt, validate=generation.valid_grade)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade this answer"}), 502
        # modelAnswer is revealed only after grading, like a solution reveal.
        return jsonify({"verdict": result["verdict"],
                        "note": generation.sanitize_html(result["note"]),
                        "modelAnswer": apply_item.get("modelAnswer", "")})
```

- [ ] **Step 6: Verify the mastery pool tolerates the enriched payloads**

`backend/mastery.py` `_accuracy_pool` reads only `payload.get("verdict")` from `lesson_explained` rows (line 63), so extra keys (`source`, `examKey`, `attempt`, `index`) are ignored. Confirm with a unit test appended to `tests/test_mastery.py` (that file's own `_conn()` and `_ev(conn, etype, lesson, payload, occurred)` helpers, course_id `"demo"`):

```python
def test_accuracy_pool_folds_remediation_apply_verdicts():
    conn = _conn()
    _ev(conn, "lesson_explained", "demo-l1",
        {"verdict": "close", "source": "remediation", "examKey": "m1",
         "attempt": 1, "index": 0}, "2026-07-16T10:00:00Z")
    pool = mastery._accuracy_pool(conn, "demo")
    assert pool["demo-l1"] == (0.5, 1.0)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q`
Expected: all PASS (including the pre-existing remediation tests against the updated fixtures)

- [ ] **Step 8: Commit**

```bash
git add backend/remediation.py backend/app.py tests/test_remediation.py tests/test_courses_api.py tests/test_mastery.py
git commit -m "feat(remediation): apply-level free-response items + grade route

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Retake gating — session_completed detector + start_exam 409 guard

**Files:**
- Modify: `backend/remediation.py` (append after `load_session`)
- Modify: `backend/app.py` (`start_exam`, lines 253-260 — the final-lock conn block)
- Test: `tests/test_remediation.py` (append), `tests/test_courses_api.py` (append)

**Interfaces:**
- Consumes: `remediation.latest_failed_result(conn, course_id, exam_key)`, `exams.exam_status(conn, course_id, manifest)`, `exams.final_unlocked(status, manifest)`, `remediation.load_session(...)`
- Produces: `remediation.session_completed(conn, content_dir, course_id, exam_key, expected_attempt) -> bool` (see resolved ambiguity 1). `start_exam` returns 409 `{"error": "Complete the gap review before retaking — that's the corrective step."}` when a not-yet-passed exam's latest fail has an incomplete (or missing, or stale) gap review. Task 5's frontend relies on the exact `lesson_check`/`lesson_explained` payload markers described here.

- [ ] **Step 1: Write the failing detector unit tests**

Append to `tests/test_remediation.py`:

```python
def _mark(conn, i, event_type, payload, topic_id="c1-l1"):
    events.insert_events(conn, [{
        "client_event_id": f"mk-{event_type}-{i}", "session_id": "s1",
        "event_type": event_type, "occurred_at": f"2026-07-16T10:{i:02d}:00+00:00",
        "course_id": "c1", "topic_id": topic_id, "payload": payload,
    }])


def _check_payload(index, attempt=1, **overrides):
    p = {"index": index, "type": "mcq", "correct": True, "source": "remediation",
         "examKey": "m1", "attempt": attempt}
    p.update(overrides)
    return p


def test_session_completed_requires_all_practice_and_apply(tmp_path):
    conn = _conn()
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    # 2 gaps x 2 practice = flat indices 0..3, plus one apply per gap (indices 0 and 1)
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # applies missing
    _mark(conn, 10, "lesson_explained", {"verdict": "correct", "source": "remediation",
                                         "examKey": "m1", "attempt": 1, "index": 0})
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    _mark(conn, 11, "lesson_explained", {"verdict": "close", "source": "remediation",
                                         "examKey": "m1", "attempt": 1, "index": 1})
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)


def test_session_completed_false_without_session_or_on_stale_attempt(tmp_path):
    conn = _conn()
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # nothing on disk
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    for gi in range(2):
        _mark(conn, 10 + gi, "lesson_explained",
              {"verdict": "correct", "source": "remediation", "examKey": "m1",
               "attempt": 1, "index": gi})
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)
    # a newer failed attempt makes the stored session stale -> not completed
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 2)


def test_session_completed_ignores_unmarked_and_malformed_events(tmp_path):
    conn = _conn()
    s = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    remediation.save_session(tmp_path, "c1", s)
    # legacy remediation answers: no examKey/attempt markers -> must not count
    for i in range(4):
        _mark(conn, i, "lesson_check",
              {"index": i, "type": "mcq", "correct": True, "source": "remediation"})
    # forged garbage must be skipped, never raised on
    _mark(conn, 20, "lesson_check", "not-a-dict")
    _mark(conn, 21, "lesson_check", _check_payload("zero"))          # non-int index
    _mark(conn, 22, "lesson_check", _check_payload(99))              # out of range
    _mark(conn, 23, "lesson_check", _check_payload(0, examKey="final"))
    _mark(conn, 24, "lesson_check", _check_payload(0, attempt=7))
    assert not remediation.session_completed(conn, tmp_path, "c1", "m1", 1)


def test_session_completed_legacy_session_without_apply(tmp_path):
    conn = _conn()
    legacy = remediation.finalize_session(_gaps(WEAK), WEAK, "m1", "c1", 1)
    for g in legacy["gaps"]:
        del g["apply"]                                               # session from before this ships
    remediation.save_session(tmp_path, "c1", legacy)
    for i in range(4):
        _mark(conn, i, "lesson_check", _check_payload(i))
    assert remediation.session_completed(conn, tmp_path, "c1", "m1", 1)  # practice alone suffices
```

- [ ] **Step 2: Write the failing gate-matrix route tests**

Append to `tests/test_courses_api.py` (uses `_post_exam_result` and `_remediation_session_on_disk` defined earlier in the file, plus a marker-event helper):

```python
def _post_marker(client, cid, event_type, payload, i, topic_id):
    r = client.post("/api/events", json={"events": [{
        "client_event_id": f"gm-{event_type}-{i}", "session_id": "s1",
        "event_type": event_type, "occurred_at": f"2026-07-16T10:{i:02d}:00+00:00",
        "course_id": cid, "topic_id": topic_id, "payload": payload,
    }]})
    assert r.status_code == 200


def test_retake_gate_matrix(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    # Stub generation FIRST: reaching it (502) proves the gate is OPEN; 409 proves CLOSED.
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)

    # 1. no prior result -> first attempts always allowed (gate open, stub reached)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502

    # 2. latest failed, gap review never generated -> 409
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["o"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 1, "weakSpots": weak}, i=1)
    r = client.post(f"/api/courses/{cid}/exams/m1")
    assert r.status_code == 409
    assert "gap review" in r.get_json()["error"]

    # 3. session exists but is incomplete -> still 409
    _remediation_session_on_disk(tmp_path, cid, lesson_id, attempt=1)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409

    # 4. legacy events without examKey/attempt markers do not count -> still 409
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation"},
                     i, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409

    # 5. fully worked session (2 practice + 1 apply) -> gate opens (stub reached)
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation",
                      "examKey": "m1", "attempt": 1}, 10 + i, lesson_id)
    _post_marker(client, cid, "lesson_explained",
                 {"verdict": "correct", "source": "remediation", "examKey": "m1",
                  "attempt": 1, "index": 0}, 20, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502

    # 6. passed exams retake freely even with an old fail on record
    _post_exam_result(client, cid, "m1",
                      {"score": 0.9, "passed": True, "attempt": 2, "weakSpots": []}, i=2)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 502


def test_retake_gate_stale_session_blocks_after_new_fail(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    manifest, lesson_id = _fixture_course(courses, tmp_path)
    cid = manifest["id"]
    def boom(prompt, validate=None, **kw):
        raise claude_client.ClaudeError("stub")
    monkeypatch.setattr(claude_client, "run_structured", boom)
    weak = [{"lessonId": lesson_id, "lessonTitle": "A", "objectives": ["o"]}]
    _post_exam_result(client, cid, "m1",
                      {"score": 0.5, "passed": False, "attempt": 2, "weakSpots": weak}, i=3)
    # session + events all belong to attempt 1: completed for 1, stale for 2
    _remediation_session_on_disk(tmp_path, cid, lesson_id, attempt=1)
    for i in range(2):
        _post_marker(client, cid, "lesson_check",
                     {"index": i, "type": "mcq", "correct": True, "source": "remediation",
                      "examKey": "m1", "attempt": 1}, 30 + i, lesson_id)
    _post_marker(client, cid, "lesson_explained",
                 {"verdict": "correct", "source": "remediation", "examKey": "m1",
                  "attempt": 1, "index": 0}, 40, lesson_id)
    assert client.post(f"/api/courses/{cid}/exams/m1").status_code == 409
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_remediation.py tests/test_courses_api.py`
Expected: FAIL — `AttributeError: module 'backend.remediation' has no attribute 'session_completed'`; gate tests get 502 where 409 is expected

- [ ] **Step 4: Implement session_completed**

Append to `backend/remediation.py` (after `load_session`):

```python
def _marked_indices(conn, course_id, exam_key, attempt, event_type):
    """Distinct payload.index values from remediation-marked events of one type.
    Payloads are client-forgeable: anything malformed, unmarked (legacy answers
    logged before markers shipped), or for another exam/attempt is skipped."""
    rows = conn.execute(
        "SELECT payload FROM events WHERE event_type = ? AND course_id = ?",
        (event_type, course_id),
    ).fetchall()
    out = set()
    for row in rows:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("source") != "remediation":
            continue
        if payload.get("examKey") != exam_key or payload.get("attempt") != attempt:
            continue
        idx = payload.get("index")
        if isinstance(idx, int) and not isinstance(idx, bool):
            out.add(idx)
    return out


def session_completed(conn, content_dir, course_id, exam_key, expected_attempt):
    """True when the stored gap review for the given failed attempt has been fully
    worked: every practice item answered (flat indices matching the frontend's
    flatPractice ordering) and every apply task submitted — apply items are counted
    only when the session has them (legacy sessions on the Pi don't). No session on
    disk, or a session for an older attempt, means the corrective step for THIS
    attempt hasn't happened -> False."""
    session = load_session(content_dir, course_id, exam_key)
    if session is None or session.get("attempt") != expected_attempt:
        return False
    attempt = session.get("attempt")
    gaps = [g for g in session.get("gaps", []) if isinstance(g, dict)]
    practice_total = sum(len(g.get("practice") or []) for g in gaps)
    apply_expected = {i for i, g in enumerate(gaps) if isinstance(g.get("apply"), dict)}
    checks = _marked_indices(conn, course_id, exam_key, attempt, "lesson_check")
    if len({i for i in checks if 0 <= i < practice_total}) < practice_total:
        return False
    applies = _marked_indices(conn, course_id, exam_key, attempt, "lesson_explained")
    return apply_expected <= applies
```

- [ ] **Step 5: Implement the start_exam guard**

In `backend/app.py` `start_exam`, replace the final-only conn block (lines 253-260):

```python
        conn = db.get_connection(path)
        try:
            status = exams.exam_status(conn, course_id, manifest)
            if exam_key == "final" and not exams.final_unlocked(status, manifest):
                return jsonify({"error": "The final is locked — pass every module exam first."}), 409
            # Bloom's corrective-then-reassess: while an exam is not yet passed, a
            # retake after a fail is blocked until that fail's gap review is completed.
            # First attempts have no failed result and pass straight through.
            if not status.get(exam_key, {}).get("passed"):
                latest = remediation.latest_failed_result(conn, course_id, exam_key)
                if latest is not None and not remediation.session_completed(
                        conn, courses.CONTENT_DIR, course_id, exam_key,
                        latest.get("attempt")):
                    return jsonify({"error": "Complete the gap review before retaking — that's the corrective step."}), 409
        finally:
            conn.close()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q`
Expected: all PASS (note `test_final_locked_until_all_modules_passed` must still pass — the final-lock 409 fires before the retake gate)

- [ ] **Step 7: Commit**

```bash
git add backend/remediation.py backend/app.py tests/test_remediation.py tests/test_courses_api.py
git commit -m "feat(exams): gate retakes behind a completed gap review (corrective-then-reassess)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend remediation — apply UI, event markers, retake unlock, builds-on chips

**Files:**
- Modify: `frontend/src/views/remediation.js`
- Modify: `frontend/src/app.js` (`showRemediation` line 467, `paintRemediation` lines 472-489, `answerPractice` lines 491-506)
- Modify: `frontend/src/courses.js` (append `gradeRemediationApply`)
- Modify: `frontend/styles.css` (append `.rem-apply`/`.rem-builds` idioms)
- Test: `frontend/tests/remediation.test.js`

**Interfaces:**
- Consumes: `POST .../remediation/grade` (Task 3) -> `{verdict, note, modelAnswer}`; Task 4's marker contract: `lesson_check` payload `{index, type, correct, source: "remediation", examKey, attempt}`; `lesson_explained` payload `{verdict, source: "remediation", examKey, attempt, index: <gapIndex>}` with `topicId` = the gap's lessonId
- Produces:
  - `remediationHTML(session, state, manifest) -> string` (third param NEW; `undefined` manifest must not crash — tests call it without one)
  - `remediationComplete(session, state) -> bool` (exported; drives the retake button)
  - `lessonIndexFrom(manifest) -> {id: {title, prereqs}}` (exported for tests)
  - state shape consumed by the view: `{answers, results, applyAnswers, applyResults, applyBusy}`
  - `gradeRemediationApply({fetch, courseId, examKey, gapIndex, answer}) -> result | {error}`

- [ ] **Step 1: Update the fixture and write the failing view tests**

In `frontend/tests/remediation.test.js`, give the SESSION fixture an apply item on gap 0 only (gap 1 stays apply-less, standing in for a legacy session gap) and an `attempt`. Replace the SESSION constant:

```js
const SESSION = {
  examKey: "m1", attempt: 1,
  gaps: [
    { lessonId: "c1-l1", lessonTitle: "Lesson <1>", objectives: ["obj <a>"],
      explanationHtml: "<p>An <em>analogy</em></p>",
      practice: [
        { type: "mcq", prompt: "<p>Pick</p>", choices: ["<code>a</code>", "b"], answer: 0, explanation: "why" },
        { type: "fill", prompt: "Blank?", answer: "w", explanation: "because" },
      ],
      apply: { prompt: "<p>A <em>novel</em> scenario</p>", modelAnswer: "Covers <strong>X</strong>" } },
    { lessonId: "c1-l2", lessonTitle: "L2", objectives: [],
      explanationHtml: "<p>Contrast</p>",
      practice: [
        { type: "mcq", prompt: "<p>Q2</p>", choices: ["x", "y"], answer: 1, explanation: "e" },
        { type: "mcq", prompt: "<p>Q3</p>", choices: ["x", "y"], answer: 0, explanation: "e" },
      ] },
  ],
};

const EMPTY = { answers: {}, results: {}, applyAnswers: {}, applyResults: {}, applyBusy: {} };
```

Update the two existing `remediationHTML(SESSION, {...})` calls to pass `{ ...EMPTY }` / `{ ...EMPTY, answers: { 0: 1 }, results: { 0: { correct: false } } }` respectively, then append:

```js
import { remediationComplete, lessonIndexFrom } from "../src/views/remediation.js";

const MANIFEST = { modules: [
  { id: "m1", title: "Mod", lessons: [
    { id: "c1-l0", title: "Roots <b>", prereqs: [] },
    { id: "c1-l1", title: "Lesson One", prereqs: ["c1-l0", "ghost"] },
    { id: "c1-l2", title: "Lesson Two", prereqs: [] },
  ] },
] };

test("apply block renders for gaps that have one, with server HTML raw", () => {
  const html = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(html.includes("<p>A <em>novel</em> scenario</p>"));       // raw
  assert.ok(html.includes('data-rem-apply="0"'));                      // textarea for gap 0
  assert.ok(html.includes('data-action="rem-apply"') && html.includes('data-gap="0"'));
  assert.ok(!html.includes('data-gap="1"'));                           // legacy gap: no block
  assert.ok(!html.includes("Covers <strong>X</strong>"));              // model answer hidden pre-grade
});

test("graded apply shows verdict, note and model answer, and locks the input", () => {
  const state = { ...EMPTY,
    applyAnswers: { 0: "my answer" },
    applyResults: { 0: { verdict: "close", note: "Nearly <em>there</em>", modelAnswer: "Covers <strong>X</strong>" } } };
  const html = remediationHTML(SESSION, state, MANIFEST);
  assert.ok(html.includes("Almost there"));
  assert.ok(html.includes("Nearly <em>there</em>"));                   // note raw (server-sanitized)
  assert.ok(html.includes("Covers <strong>X</strong>"));               // model answer revealed
  assert.ok(/data-rem-apply="0"[^>]*disabled/.test(html) || /disabled[^>]*data-rem-apply="0"/.test(html));
});

test("remediationComplete needs all practice plus every present apply", () => {
  const allPractice = { 0: { correct: true }, 1: { correct: true }, 2: { correct: true }, 3: { correct: true } };
  assert.equal(remediationComplete(SESSION, { ...EMPTY }), false);
  assert.equal(remediationComplete(SESSION, { ...EMPTY, results: allPractice }), false);   // apply missing
  assert.equal(remediationComplete(SESSION, { ...EMPTY, results: allPractice,
    applyResults: { 0: { verdict: "correct" } } }), true);
  const legacy = { ...SESSION, gaps: SESSION.gaps.map((g) => { const { apply, ...rest } = g; return rest; }) };
  assert.equal(remediationComplete(legacy, { ...EMPTY, results: allPractice }), true);      // no apply anywhere
});

test("retake button is disabled with unlock copy until the session is complete", () => {
  const locked = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(/data-action="retake-exam"[^>]*disabled/.test(locked));
  assert.ok(locked.includes("Answer everything above to unlock the retake"));
  const done = { ...EMPTY,
    results: { 0: { correct: true }, 1: { correct: true }, 2: { correct: true }, 3: { correct: true } },
    applyResults: { 0: { verdict: "correct" } } };
  const open = remediationHTML(SESSION, done, MANIFEST);
  assert.ok(!/data-action="retake-exam"[^>]*disabled/.test(open));
  assert.ok(open.includes("Retake with fresh questions"));
});

test("builds-on chips resolve prereq titles, escape them, and skip unknown ids", () => {
  const html = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(html.includes("Builds on:"));
  assert.ok(html.includes('data-lesson="c1-l0"'));
  assert.ok(html.includes("Roots &lt;b&gt;"));                         // title escaped
  assert.ok(!html.includes("ghost"));                                  // unknown id skipped
  const bare = remediationHTML(SESSION, { ...EMPTY });                 // no manifest: no crash, no chips
  assert.ok(!bare.includes("Builds on:"));
});

test("lessonIndexFrom maps ids to titles and prereqs, tolerating null", () => {
  const idx = lessonIndexFrom(MANIFEST);
  assert.deepEqual(idx["c1-l1"], { title: "Lesson One", prereqs: ["c1-l0", "ghost"] });
  assert.deepEqual(lessonIndexFrom(null), {});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: FAIL — `remediationComplete`/`lessonIndexFrom` not exported; apply/chips assertions unmatched

- [ ] **Step 3: Implement the view**

Replace `frontend/src/views/remediation.js` with:

```js
import { esc } from "../escape.js";

// A corrective session after a failed exam: per gap, a new-angle explanation
// (server-sanitized, renders raw) plus fresh practice items graded client-side
// exactly like lesson checks, plus ONE free-response "Apply it" task graded by
// the backend (legacy sessions on the Pi lack it — rendered only when present).
// Practice state is keyed by FLAT index across gaps; apply state by gap index.

export function flatPractice(session) {
  const out = [];
  (session.gaps || []).forEach((g, gi) =>
    (g.practice || []).forEach((check) => out.push({ gapIndex: gi, lessonId: g.lessonId, check })));
  return out;
}

export function lessonIndexFrom(manifest) {
  const idx = {};
  ((manifest && manifest.modules) || []).forEach((m) =>
    (m.lessons || []).forEach((l) => { idx[l.id] = { title: l.title || "", prereqs: l.prereqs || [] }; }));
  return idx;
}

// The retake unlock (Item B): every practice item answered and every present
// apply task graded. The backend detector is authoritative; this mirrors it.
export function remediationComplete(session, state) {
  const total = flatPractice(session).length;
  for (let k = 0; k < total; k++) {
    if (!(state.results && state.results[k])) return false;
  }
  return (session.gaps || []).every((g, gi) =>
    !g.apply || !!(state.applyResults && state.applyResults[gi] && state.applyResults[gi].verdict));
}

function practiceItem(check, k, state) {
  const result = state.results && state.results[k];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state.answers[k])) cls = "choice wrong";
        }
        return `<button class="${cls}" data-rq="${k}" data-rq-choice="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state.answers && state.answers[k] != null ? state.answers[k] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input data-rq-input="${k}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="rq-fill" data-rq="${k}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}

const APPLY_LABEL = { correct: "Correct", close: "Almost there", incorrect: "Not quite" };

function applyBlock(gap, gi, state) {
  if (!gap.apply || !gap.apply.prompt) return "";
  const res = state.applyResults && state.applyResults[gi];
  const busy = !!(state.applyBusy && state.applyBusy[gi]);
  const done = !!(res && res.verdict);
  const val = state.applyAnswers && state.applyAnswers[gi] != null ? state.applyAnswers[gi] : "";
  let feedback = "";
  if (busy) {
    feedback = `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Checking your answer…</span></div>`;
  } else if (res && res.error) {
    feedback = `<div class="grade grade-soft">${esc(res.error)}</div>`;
  } else if (done) {
    const v = APPLY_LABEL[res.verdict] ? res.verdict : "close";
    feedback =
      `<div class="grade grade-${v}" aria-live="polite">` +
      `<div class="grade-verdict">${APPLY_LABEL[v]}</div>` +
      `<div class="grade-note">${res.note || ""}</div></div>` +
      `<div class="rem-model"><b>A correct answer covers:</b> ${res.modelAnswer || ""}</div>`;
  }
  const canSend = !!val.trim() && !busy && !done;
  return (
    `<div class="rem-apply"><div class="checks-title">Apply it</div>` +
    `<div class="rem-apply-prompt">${gap.apply.prompt}</div>` +
    `<textarea data-rem-apply="${gi}" placeholder="Work it through…"${done ? " disabled" : ""}>${esc(val)}</textarea>` +
    `<button class="btn-secondary" data-action="rem-apply" data-gap="${gi}"${canSend ? "" : " disabled"}>` +
    `${done ? "Answered" : busy ? "Checking…" : "Check my answer"}</button>${feedback}</div>`
  );
}

// Item D: trace the weakness to its root — chips open the upstream lesson.
function buildsOnChips(lessonId, lessonIndex) {
  const entry = lessonIndex[lessonId];
  const chips = ((entry && entry.prereqs) || [])
    .filter((id) => lessonIndex[id])          // revised-away lessons: skipped silently
    .map((id) => `<button class="rem-chip" data-lesson="${esc(id)}">${esc(lessonIndex[id].title)}</button>`)
    .join("");
  return chips ? `<div class="rem-builds">Builds on: ${chips}</div>` : "";
}

export function remediationHTML(session, state, manifest) {
  const lessonIndex = lessonIndexFrom(manifest);
  let k = 0;
  const gaps = (session.gaps || [])
    .map((g, gi) => {
      const items = (g.practice || []).map((c) => practiceItem(c, k++, state)).join("");
      const objectives = (g.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("");
      return (
        `<section class="rem-gap"><h2>${esc(g.lessonTitle)}</h2>` +
        (objectives ? `<ul class="rem-objectives">${objectives}</ul>` : "") +
        buildsOnChips(g.lessonId, lessonIndex) +
        `<div class="rem-explain">${g.explanationHtml}</div>` +
        `<div class="rem-practice">${items}</div>` +
        applyBlock(g, gi, state) +
        `</section>`
      );
    })
    .join("");
  const complete = remediationComplete(session, state);
  return (
    `<div class="remediation">` +
    `<div class="eyebrow">GAP REVIEW</div>` +
    `<h1 class="session-topic">Fix the gaps</h1>` +
    `<div class="exam-note">Each gap is re-explained from a new angle, with fresh practice. ` +
    `When it clicks, retake the exam — new questions, same objectives.</div>` +
    gaps +
    `<div class="nav">` +
    `<button class="btn-primary" data-action="retake-exam"${complete ? "" : " disabled"}>` +
    `${complete ? "Retake with fresh questions" : "Answer everything above to unlock the retake"}</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
```

- [ ] **Step 4: Implement the fetch helper**

Append to `frontend/src/courses.js`:

```js
export async function gradeRemediationApply({ fetch, courseId, examKey, gapIndex, answer }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/remediation/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gapIndex, answer }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade this answer right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
```

- [ ] **Step 5: Wire app.js**

In `frontend/src/app.js`:

(a) Extend the courses.js import (line 7) with `gradeRemediationApply`:

```js
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply } from "./courses.js";
```

(b) In `showRemediation` (line 467), extend the state literal:

```js
    ui.remState = { examKey, session, items: flatPractice(session), answers: {}, results: {},
                    applyAnswers: {}, applyResults: {}, applyBusy: {} };
```

(c) Replace `paintRemediation` (lines 472-489):

```js
  function paintRemediation() {
    const st = ui.remState;
    const view = root.querySelector("#view");
    view.innerHTML = remediationHTML(st.session, st, ui.manifest);
    view.querySelectorAll("[data-rq-choice]").forEach((b) => {
      b.addEventListener("click", () =>
        answerPractice(Number(b.getAttribute("data-rq")), Number(b.getAttribute("data-rq-choice"))));
    });
    view.querySelectorAll('[data-action="rq-fill"]').forEach((b) => {
      b.addEventListener("click", () => {
        const k = Number(b.getAttribute("data-rq"));
        const inp = view.querySelector(`[data-rq-input="${k}"]`);
        answerPractice(k, inp ? inp.value : "");
      });
    });
    // Apply-it textareas update state without a repaint (a repaint would steal
    // focus on every keystroke); only their button's disabled state refreshes.
    view.querySelectorAll("textarea[data-rem-apply]").forEach((t) => {
      t.addEventListener("input", () => {
        const gi = Number(t.getAttribute("data-rem-apply"));
        st.applyAnswers[gi] = t.value;
        const btn = view.querySelector(`[data-action="rem-apply"][data-gap="${gi}"]`);
        if (btn) btn.disabled = !t.value.trim() || !!st.applyBusy[gi];
      });
    });
    view.querySelectorAll('[data-action="rem-apply"]').forEach((b) => {
      b.addEventListener("click", () => submitApply(Number(b.getAttribute("data-gap"))));
    });
    // Builds-on chips: trace the weakness to its upstream lesson (Item D).
    view.querySelectorAll("[data-lesson]").forEach((b) => {
      b.addEventListener("click", () => openLesson(b.getAttribute("data-lesson")));
    });
    view.querySelector('[data-action="retake-exam"]').addEventListener("click", () => showExam(st.examKey));
    view.querySelector('[data-action="back-curriculum"]').addEventListener("click", showCurriculum);
  }

  async function submitApply(gi) {
    const st = ui.remState;
    if (!st) return;
    const answer = (st.applyAnswers[gi] || "").trim();
    const prior = st.applyResults[gi];
    if (!answer || st.applyBusy[gi] || (prior && prior.verdict)) return; // one submission per gap
    st.applyBusy[gi] = true;
    paintRemediation();
    const result = await gradeRemediationApply({
      fetch, courseId: ui.courseId, examKey: st.examKey, gapIndex: gi, answer,
    });
    if (ui.screen !== "remediation" || ui.remState !== st) return; // navigated away mid-grade
    st.applyBusy[gi] = false;
    st.applyResults[gi] = result || { error: "Couldn't grade this answer right now." };
    if (result && result.verdict) {
      const gap = st.session.gaps[gi] || {};
      // Apply verdicts feed mastery through the lesson_explained pool; the
      // examKey/attempt/index markers are what the backend retake gate counts.
      log("lesson_explained", {
        courseId: ui.courseId, topicId: gap.lessonId,
        payload: { verdict: result.verdict, source: "remediation",
                   examKey: st.examKey, attempt: st.session.attempt, index: gi },
      });
    }
    paintRemediation();
  }
```

(d) In `answerPractice` (line 501), enrich the `lesson_check` payload with the retake-gate markers:

```js
    log("lesson_check", {
      courseId: ui.courseId, topicId: item.lessonId,
      payload: { index: k, type: item.check.type, correct: result.correct, source: "remediation",
                 examKey: st.examKey, attempt: st.session.attempt },
    });
```

(e) No code change is needed to surface the backend 409: if the gate fires despite the client-side unlock (spec: "backend 409 remains authoritative"), `showExam` already renders the response's `error` string in its error card (app.js lines 381-387).

- [ ] **Step 6: Add the CSS idioms**

Append to `frontend/styles.css` (custom properties --ok/--warn are NOT declared in :root — always use fallbacks):

```css
.rem-builds { font-size: 12px; color: var(--text-dim, #8a7d6d); margin: 0 0 8px; }
.rem-chip { display: inline-block; margin: 0 4px 4px 4px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--border-field, #d8cfc2); background: transparent; font-size: 12px; cursor: pointer; color: inherit; }
.rem-chip:hover { border-color: var(--purple, #7c6aff); }
.rem-apply { margin: 12px 0 4px; padding-top: 10px; border-top: 1px dashed var(--border-field, #d8cfc2); }
.rem-apply textarea { width: 100%; min-height: 72px; margin: 8px 0; }
.rem-apply-prompt { font-family: var(--serif); font-size: 15px; line-height: 1.55; }
.rem-model { margin-top: 8px; font-size: 14px; color: var(--text-2, inherit); }
```

- [ ] **Step 7: Run the tests and the import check**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: prints `imports ok`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/remediation.js frontend/src/app.js frontend/src/courses.js frontend/styles.css frontend/tests/remediation.test.js
git commit -m "feat(remediation): apply-it UI, retake unlock, gate markers, builds-on chips

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend capstone submission card + exam fail-screen retake replacement

**Files:**
- Modify: `frontend/src/views/capstone.js`
- Modify: `frontend/src/views/exam.js` (`examResultHTML`, lines 62-85)
- Modify: `frontend/src/app.js` (`showCapstone` lines 342-361, `submitCurrentExam` retake binding line 441)
- Modify: `frontend/src/courses.js` (append `submitCapstone`)
- Modify: `frontend/styles.css` (append `.cap-*` idioms)
- Test: `frontend/tests/views.test.js` (capstone card), `frontend/tests/exam.test.js` (fail-screen)

**Interfaces:**
- Consumes: `POST /api/courses/<cid>/capstone/<scope>/submit` (Task 2) -> `{scope, score, passed, attempt, perCriterion: [{index, met, note, evidence}], summary, rubric: [{criterion}]}` — criterion/note/summary server-sanitized (render raw), evidence is verbatim learner text (esc() client-side)
- Produces:
  - `capstoneHTML(capstone, state = {}) -> string` with state `{work, busy, result}` (existing callers/tests that pass no state must keep working)
  - `submitCapstone({fetch, courseId, scope, work}) -> result | {error}` in courses.js (the app.js local handler is named `submitCapstoneWork` to avoid shadowing this import)
  - `examResultHTML`: fail-with-weak-spots screens show "Fix the gaps" + "Retake unlocks after the gap review." and NO retake button; passed screens and fails without weak spots keep the retake button (resolved ambiguity 6). app.js must therefore null-guard the retake binding.

- [ ] **Step 1: Write the failing capstone view tests**

Append to `frontend/tests/views.test.js` (capstoneHTML is already imported there, line 8):

```js
const CAP = { scope: "m1", title: "Mod A", intro: "i",
  items: [{ title: "A", detail: "d", source: "s" }] };

test("capstone renders a submit-your-work card with busy and disabled states", () => {
  const empty = capstoneHTML(CAP, { work: "", busy: false, result: null });
  assert.match(empty, /data-field="cap-work"/);
  assert.match(empty, /data-action="cap-submit"[^>]*disabled/);
  const ready = capstoneHTML(CAP, { work: "my project", busy: false, result: null });
  assert.doesNotMatch(ready, /data-action="cap-submit"[^>]*disabled/);
  assert.ok(ready.includes("my project"));                            // textarea keeps the draft
  const busy = capstoneHTML(CAP, { work: "my project", busy: true, result: null });
  assert.ok(busy.includes("Grading…"));
  assert.match(busy, /data-action="cap-submit"[^>]*disabled/);
});

test("capstone renders the graded result: badges, raw notes, escaped evidence", () => {
  const result = {
    score: 0.625, passed: false, attempt: 1, summary: "Solid <em>start</em>",
    rubric: [{ criterion: "Uses &lt;b&gt;real&lt;/b&gt; data" }, { criterion: "C1" },
             { criterion: "C2" }, { criterion: "C3" }],
    perCriterion: [
      { index: 0, met: "met", note: "Good <em>use</em>", evidence: "I <scraped> the data" },
      { index: 1, met: "partial", note: "n", evidence: "" },
      { index: 2, met: "unmet", note: "n", evidence: "" },
      { index: 3, met: "partial", note: "n", evidence: "" },
    ],
  };
  const html = capstoneHTML(CAP, { work: "w", busy: false, result });
  assert.ok(html.includes("Uses &lt;b&gt;real&lt;/b&gt; data"));      // criterion raw (pre-escaped server-side)
  assert.ok(html.includes("Good <em>use</em>"));                       // note raw (server-sanitized)
  assert.ok(html.includes("I &lt;scraped&gt; the data"));              // evidence esc()'d
  assert.ok(html.includes("Not passed — 63% (70% needed)"));
  assert.ok(html.includes("Solid <em>start</em>"));                    // summary raw
  assert.ok(html.includes("Partially met") && html.includes("Not met") && html.includes("Met"));
  assert.ok(html.includes("Submit again"));                            // same textarea stays
  const passed = capstoneHTML(CAP, { work: "w", busy: false,
    result: { ...result, score: 0.75, passed: true } });
  assert.ok(passed.includes("Passed — 75%"));
});

test("capstone submit errors render softly and keep the card usable", () => {
  const html = capstoneHTML(CAP, { work: "w", busy: false, result: { error: "boom <x>" } });
  assert.ok(html.includes("boom &lt;x&gt;"));
  assert.doesNotMatch(html, /data-action="cap-submit"[^>]*disabled/);
});
```

- [ ] **Step 2: Write the failing exam-result tests**

Append to `frontend/tests/exam.test.js`:

```js
test("failed result with weak spots replaces retake with the unlock note", () => {
  const failed = { score: 0.5, passed: false, perQuestion: [],
    weakSpots: [{ lessonId: "l1", lessonTitle: "L", objectives: [] }] };
  const html = examResultHTML(failed);
  assert.ok(html.includes('data-action="fix-gaps"'));
  assert.ok(!html.includes('data-action="retake-exam"'));
  assert.ok(html.includes("Retake unlocks after the gap review."));
});

test("passed results and fails without weak spots keep the retake button", () => {
  const passed = examResultHTML({ score: 0.9, passed: true, perQuestion: [], weakSpots: [] });
  assert.ok(passed.includes('data-action="retake-exam"'));
  assert.ok(!passed.includes("Retake unlocks after the gap review."));
  const noSpots = examResultHTML({ score: 0.5, passed: false, perQuestion: [], weakSpots: [] });
  assert.ok(noSpots.includes('data-action="retake-exam"'));   // nothing to remediate: not gated
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test frontend/tests/*.test.js`
Expected: FAIL — no `cap-work` field; retake button still present on gated fails

- [ ] **Step 4: Implement the capstone view**

In `frontend/src/views/capstone.js`, replace the `capstoneHTML` export (keep `htmlDecode`/`exploreUrl` untouched) and add the result renderer above it:

```js
const MET_LABEL = { met: "Met", partial: "Partially met", unmet: "Not met" };

// criterion/note/summary arrive server-sanitized -> render raw; evidence is a
// verbatim quote of the learner's own submission -> esc() client-side.
function capResultHTML(result) {
  if (!result) return "";
  if (result.error) return `<div class="grade grade-soft">${esc(result.error)}</div>`;
  const rubric = result.rubric || [];
  const rows = (result.perCriterion || [])
    .map((g) => {
      const crit = rubric[g.index] ? rubric[g.index].criterion : "";
      const evidence = g.evidence ? `<div class="cap-evidence">"${esc(g.evidence)}"</div>` : "";
      return (
        `<div class="cap-crit">` +
        `<div class="cap-chead"><span class="cap-cname">${crit}</span>` +
        `<span class="cap-badge cap-badge-${esc(g.met)}">${MET_LABEL[g.met] || esc(g.met)}</span></div>` +
        `<div class="cap-note">${g.note || ""}</div>${evidence}</div>`
      );
    })
    .join("");
  const pct = Math.round((result.score || 0) * 100);
  const banner = result.passed
    ? `<div class="exam-banner pass">Passed — ${pct}%</div>`
    : `<div class="exam-banner fail">Not passed — ${pct}% (70% needed)</div>`;
  return `${banner}${rows}<div class="cap-summary">${result.summary || ""}</div>`;
}

function submitCardHTML(state) {
  const canSend = !!(state.work || "").trim() && !state.busy;
  const graded = !!(state.result && !state.result.error);
  const body = state.busy
    ? `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Grading against the rubric…</span></div>`
    : capResultHTML(state.result);
  return (
    `<section class="card cap-submit"><div class="checks-title">Submit your work</div>` +
    `<div class="pq-lead">Apply what you studied: write or paste a piece of your own work for this capstone. It is graded against a rubric — 70% passes, unlimited attempts.</div>` +
    `<textarea data-field="cap-work" placeholder="Your work…">${esc(state.work || "")}</textarea>` +
    `<button class="btn-primary" data-action="cap-submit"${canSend ? "" : " disabled"}>` +
    `${state.busy ? "Grading…" : graded ? "Submit again" : "Submit for grading"}</button>` +
    `${body}</section>`
  );
}

export function capstoneHTML(capstone, state = {}) {
  // title/detail/source/intro arrive server-sanitized; capstone.title is raw -> esc().
  const items = (capstone.items || [])
    .map((it) => {
      const src = it.source ? `<span class="cap-src">${it.source}</span>` : "";
      return (
        `<div class="cap-item">` +
        `<div class="cap-ihead"><span class="cap-ititle">${it.title}</span>${src}</div>` +
        `<div class="cap-detail">${it.detail}</div>` +
        `<a class="cap-explore" href="${esc(exploreUrl(it))}" target="_blank" rel="noopener noreferrer">Explore →</a>` +
        `</div>`
      );
    })
    .join("");
  return (
    `<div class="capstone">` +
    `<div class="greeting"><h1>Real-world connections</h1><span>${esc(capstone.title || "")}</span></div>` +
    `<section class="card"><span class="eyebrow">IN THE REAL WORLD</span>` +
    `<div class="cap-intro">${capstone.intro || ""}</div>${items}</section>` +
    submitCardHTML(state) +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div>` +
    `</div>`
  );
}
```

- [ ] **Step 5: Implement the exam-result change**

In `frontend/src/views/exam.js`, replace the tail of `examResultHTML` (lines 73-84):

```js
  // Item B: a gated fail routes through the corrective step — the retake button
  // only shows where the backend gate would allow it (pass, or nothing to remediate).
  const fixable = !result.passed && (result.weakSpots || []).length > 0;
  const fix = fixable
    ? `<button class="btn-primary" data-action="fix-gaps">Fix the gaps</button>` +
      `<div class="exam-note">Retake unlocks after the gap review.</div>`
    : `<button class="btn-secondary" data-action="retake-exam">Retake with fresh questions</button>`;
  return (
    `<div class="exam-result">${banner}` +
    (weak ? `<h2>Focus next on</h2>${weak}` : "") +
    (qs ? `<h2>Question by question</h2>${qs}` : "") +
    `<div class="nav">${fix}` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
```

- [ ] **Step 6: Implement the fetch helper and app.js wiring**

Append to `frontend/src/courses.js`:

```js
export async function submitCapstone({ fetch, courseId, scope, work }) {
  const resp = await fetch(`/api/courses/${courseId}/capstone/${scope}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ work }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade your capstone right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
```

In `frontend/src/app.js`:

(a) Extend the courses.js import (line 7, already extended in Task 5) with `submitCapstone`:

```js
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply, submitCapstone } from "./courses.js";
```

(b) In `showCapstone`, replace the two success lines (lines 359-360: `view.innerHTML = capstoneHTML(cap); ...`) with state init + paint, and add the two new functions after `showCapstone`:

```js
    ui.capState = { scope, cap, work: "", busy: false, result: null };
    paintCapstone();
  }

  function paintCapstone() {
    const st = ui.capState;
    const view = root.querySelector("#view");
    view.innerHTML = capstoneHTML(st.cap, st);
    view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
    // The textarea updates state without a repaint (a repaint would steal focus
    // on every keystroke); only the submit button's disabled state refreshes.
    const ta = view.querySelector('[data-field="cap-work"]');
    if (ta) ta.addEventListener("input", () => {
      st.work = ta.value;
      const btn = view.querySelector('[data-action="cap-submit"]');
      if (btn) btn.disabled = !ta.value.trim() || st.busy;
    });
    const submit = view.querySelector('[data-action="cap-submit"]');
    if (submit) submit.addEventListener("click", submitCapstoneWork);
  }

  // The server records capstone_result itself — the client logs no event here.
  async function submitCapstoneWork() {
    const st = ui.capState;
    if (!st || st.busy || !(st.work || "").trim()) return;
    st.busy = true;
    paintCapstone();
    const result = await submitCapstone({ fetch, courseId: ui.courseId, scope: st.scope, work: st.work.trim() });
    if (ui.screen !== "capstone" || ui.capState !== st) return; // navigated away mid-grade
    st.busy = false;
    st.result = result || { error: "Couldn't grade your capstone right now." };
    paintCapstone();
  }
```

(c) In `submitCurrentExam`, the retake button no longer always exists — replace line 441:

```js
    const rt = view.querySelector('[data-action="retake-exam"]');
    if (rt) rt.addEventListener("click", () => showExam(st.examKey));
```

- [ ] **Step 7: Add the CSS idioms**

Append to `frontend/styles.css`:

```css
.cap-submit textarea { width: 100%; min-height: 120px; margin: 8px 0; }
.cap-crit { padding: 10px 0; border-top: 1px solid var(--border-field, #d8cfc2); }
.cap-chead { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.cap-cname { font-size: 14px; font-weight: 600; }
.cap-badge { font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; }
.cap-badge-met { color: var(--ok, #2e7d4f); }
.cap-badge-partial { color: var(--warn, #b26a00); }
.cap-badge-unmet { color: var(--warn, #b26a00); }
.cap-note { font-family: var(--serif); font-size: 14px; line-height: 1.5; color: var(--text-2, inherit); }
.cap-evidence { font-size: 13px; font-style: italic; color: var(--text-dim, #8a7d6d); margin-top: 4px; }
.cap-summary { font-family: var(--serif); font-size: 14px; line-height: 1.55; margin-top: 12px; }
```

- [ ] **Step 8: Run the tests and the import check**

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS (including the pre-existing capstone explore-link and exam tests — the passed-result test at exam.test.js line 37 keeps its retake button)

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`
Expected: prints `imports ok`

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/capstone.js frontend/src/views/exam.js frontend/src/app.js frontend/src/courses.js frontend/styles.css frontend/tests/views.test.js frontend/tests/exam.test.js
git commit -m "feat(capstone): submission card with rubric verdicts; gate the exam-result retake

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Transcript capstone rows + attempts on passed rows + syllabus builds-on

**Files:**
- Modify: `backend/transcript.py` (`course_record` lines 29-59, new `_capstone_rows` helper)
- Modify: `frontend/src/views/transcript.js` (`examRow` lines 9-18, `courseBlock` line 21)
- Modify: `frontend/src/views/syllabus.js` (`moduleBlock` lines 11-16, `syllabusHTML` line 30)
- Modify: `frontend/styles.css` (one `.syl-builds` rule)
- Test: `tests/test_transcript.py` (append), `frontend/tests/transcript.test.js` (append), `frontend/tests/views.test.js` (append)

**Interfaces:**
- Consumes: `capstone_result` events (Task 1 payload: `{scope, score, passed, perCriterion, summary, attempt}`), manifest `lesson.prereqs` arrays
- Produces: `course_record(...)["capstones"] = [{scope, title, attempts, bestScore, passed, passedOn}]` in manifest-module order with the course scope last; transcript passed rows read `87% · 2026-07-14 · 3 attempts`; syllabus lessons show `Builds on: <title>, <title>`

- [ ] **Step 1: Write the failing backend tests**

Append to `tests/test_transcript.py`:

```python
def _cap_result(conn, cid, scope, score, passed, occurred, i=0):
    events.insert_events(conn, [{
        "client_event_id": f"cap-{scope}-{occurred}-{i}", "session_id": "server",
        "event_type": "capstone_result", "occurred_at": occurred,
        "course_id": cid, "topic_id": scope,
        "payload": {"scope": scope, "score": score, "passed": passed,
                    "perCriterion": [], "summary": "s", "attempt": i + 1},
    }])


def test_course_record_assembles_capstone_rows(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _cap_result(conn, "demo", "m1", 0.6, False, "2026-07-13T09:00:00+00:00", 0)
    _cap_result(conn, "demo", "m1", 0.8, True, "2026-07-14T09:00:00+00:00", 1)
    _cap_result(conn, "demo", "course", 0.9, True, "2026-07-15T09:00:00+00:00", 0)
    rec = transcript.course_record(conn, root, "demo", manifest)
    assert [r["scope"] for r in rec["capstones"]] == ["m1", "course"]   # manifest order, course last
    m1 = rec["capstones"][0]
    assert m1["title"] == "M1" and m1["attempts"] == 2 and m1["bestScore"] == 0.8
    assert m1["passed"] and m1["passedOn"] == "2026-07-14"              # first passing attempt
    assert rec["capstones"][1]["title"] == "Course capstone"


def test_course_record_capstones_empty_without_submissions(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    assert transcript.course_record(conn, root, "demo", manifest)["capstones"] == []


def test_course_record_capstones_skip_dropped_scopes_and_forged_payloads(tmp_path):
    conn = _conn()
    root = _course(tmp_path)
    manifest = json.loads((root / "demo" / "course.json").read_text())
    _cap_result(conn, "demo", "m9", 0.9, True, "2026-07-13T09:00:00+00:00", 0)  # dropped module
    events.insert_events(conn, [{                                                # forged payload
        "client_event_id": "cap-forged", "session_id": "s",
        "event_type": "capstone_result", "occurred_at": "2026-07-13T10:00:00+00:00",
        "course_id": "demo", "topic_id": "m1", "payload": "not-a-dict",
    }])
    _cap_result(conn, "demo", "m1", 0.6, False, "2026-07-13T11:00:00+00:00", 0)
    rec = transcript.course_record(conn, root, "demo", manifest)                 # must not raise
    assert [r["scope"] for r in rec["capstones"]] == ["m1"]
    assert rec["capstones"][0]["attempts"] == 1                                  # forged row skipped entirely
    assert rec["capstones"][0]["bestScore"] == 0.6 and not rec["capstones"][0]["passed"]
```

- [ ] **Step 2: Write the failing frontend tests**

Append to `frontend/tests/transcript.test.js`:

```js
test("passed exam rows include the attempt count", () => {
  const html = transcriptHTML(DATA);
  assert.ok(html.includes("90% · 2026-07-10 · 2 attempts"));
  assert.ok(html.includes("88% · 2026-07-12 · 1 attempt"));   // singular on the final
});

test("capstone rows render after the final with the same status treatment", () => {
  const withCaps = { courses: [{ ...DATA.courses[0], capstones: [
    { scope: "m1", title: "Sorting", attempts: 2, bestScore: 0.75, passed: true, passedOn: "2026-07-13" },
    { scope: "course", title: "Course capstone", attempts: 1, bestScore: 0.4, passed: false, passedOn: null },
  ] }] };
  const html = transcriptHTML(withCaps);
  assert.ok(html.includes("Capstone: Sorting"));
  assert.ok(html.includes("Course capstone"));
  assert.ok(!html.includes("Capstone: Course capstone"));      // course scope is not double-labelled
  assert.ok(html.includes("75% · 2026-07-13 · 2 attempts"));
  assert.ok(html.includes("best 40% · 1 attempt"));
  assert.ok(html.indexOf("Capstone: Sorting") > html.indexOf("Final exam"));
});

test("courses without capstone submissions show nothing new", () => {
  const html = transcriptHTML(DATA);                            // DATA has no capstones field
  assert.ok(!html.includes("Capstone"));
});
```

Append to `frontend/tests/views.test.js` (COURSE and OBJ constants exist near line 484):

```js
test("syllabusHTML renders builds-on lines from prereqs, skipping unknown ids", () => {
  const course = { ...COURSE, modules: [{ id: "m1", title: "Foundations", outcomes: [OBJ],
    lessons: [
      { id: "l1", title: "Vectors <b>", estMinutes: 90, objectives: [OBJ], prereqs: [] },
      { id: "l2", title: "Matrices", estMinutes: 90, objectives: [OBJ], prereqs: ["l1", "ghost"] },
    ] }] };
  const html = syllabusHTML(course);
  assert.ok(html.includes("Builds on: Vectors &lt;b&gt;"));     // resolved title, esc()'d
  assert.ok(!html.includes("ghost"));                            // unknown id skipped silently
});

test("syllabusHTML omits builds-on when prereqs are empty or absent", () => {
  assert.ok(!syllabusHTML(COURSE).includes("Builds on:"));       // COURSE's lesson has prereqs: []
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_transcript.py` — Expected: FAIL (`KeyError: 'capstones'`)
Run: `node --test frontend/tests/*.test.js` — Expected: FAIL (no attempt counts, no capstone rows, no builds-on)

- [ ] **Step 4: Implement the backend rows**

In `backend/transcript.py`, add after `_first_pass_dates`:

```python
def _capstone_rows(conn, course_id, manifest):
    """Transcript rows for graded capstones (Item E): one row per scope with at
    least one capstone_result event, in manifest-module order with the course
    scope last. Scopes dropped by a later revision are skipped, and payloads are
    server-written but still parsed defensively — a forged client event with this
    type must never 500 the transcript, so malformed rows are skipped entirely
    (mirrors exams.exam_status)."""
    rows = conn.execute(
        "SELECT topic_id, occurred_at, payload FROM events "
        "WHERE event_type = 'capstone_result' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    module_titles = {m.get("id"): m.get("title", "") for m in manifest.get("modules", [])}
    by_scope = {}
    for row in rows:
        scope = row["topic_id"]
        if scope != "course" and scope not in module_titles:
            continue
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = by_scope.setdefault(scope, {
            "scope": scope,
            "title": "Course capstone" if scope == "course" else module_titles[scope],
            "attempts": 0, "bestScore": 0.0, "passed": False, "passedOn": None,
        })
        entry["attempts"] += 1
        score = payload.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            entry["bestScore"] = max(entry["bestScore"], float(score))
        if payload.get("passed"):
            entry["passed"] = True
            if entry["passedOn"] is None:
                entry["passedOn"] = row["occurred_at"][:10]
    order = [m.get("id") for m in manifest.get("modules", [])] + ["course"]
    return [by_scope[s] for s in order if s in by_scope]
```

In `course_record`, add one key to the returned dict (after `"final": row("final", "Final exam"),`):

```python
        "capstones": _capstone_rows(conn, course_id, manifest),
```

- [ ] **Step 5: Implement the frontend transcript rows**

In `frontend/src/views/transcript.js`, replace `examRow` and the first line of `courseBlock`:

```js
function attemptsLabel(n) {
  return `${n} attempt${n === 1 ? "" : "s"}`;
}

function examRow(r) {
  let status = `<span class="tr-status">Not taken</span>`;
  if (r.passed) {
    status = `<span class="tr-status passed">${pct(r.bestScore)}` +
      `${r.passedOn ? ` · ${esc(r.passedOn)}` : ""}` +
      `${r.attempts ? ` · ${attemptsLabel(r.attempts)}` : ""}</span>`;
  } else if (r.attempts) {
    status = `<span class="tr-status failed">best ${pct(r.bestScore)} · ${attemptsLabel(r.attempts)}</span>`;
  }
  return `<div class="tr-row"><span class="tr-name">${esc(r.title)}</span>${status}</div>`;
}

// Capstone rows reuse the exam-row treatment; module scopes get a "Capstone:"
// prefix, the course scope's title is already "Course capstone".
function capstoneRow(r) {
  const title = r.scope === "course" ? r.title : `Capstone: ${r.title}`;
  return examRow({ ...r, title });
}
```

and in `courseBlock`:

```js
  const rows = (c.modules || []).map(examRow).join("") + examRow(c.final || {}) +
    (c.capstones || []).map(capstoneRow).join("");
```

- [ ] **Step 6: Implement the syllabus builds-on lines**

In `frontend/src/views/syllabus.js`, replace `moduleBlock` and the `modules` line in `syllabusHTML`:

```js
// Item D: the compiled prereq graph's first consumer. Plain text only — the
// syllabus renders pre-enrolment (and in the revision review), so no links.
function buildsOnLine(lesson, titles) {
  const names = (lesson.prereqs || []).map((id) => titles[id]).filter(Boolean);
  return names.length ? `<div class="syl-builds">Builds on: ${names.map(esc).join(", ")}</div>` : "";
}

function moduleBlock(module, titles) {
  const lessons = (module.lessons || [])
    .map((l) => `<div class="syl-lesson"><div class="syl-lesson-title">${esc(l.title || "")}</div>${objList(l.objectives)}${buildsOnLine(l, titles)}</div>`)
    .join("");
  return `<section class="syl-module"><h3>${esc(module.title || "")}</h3>${lessons}</section>`;
}
```

In `syllabusHTML`, replace `const modules = (course.modules || []).map(moduleBlock).join("");` with:

```js
  const titles = {};
  (course.modules || []).forEach((m) => (m.lessons || []).forEach((l) => { titles[l.id] = l.title || ""; }));
  const modules = (course.modules || []).map((m) => moduleBlock(m, titles)).join("");
```

Append to `frontend/styles.css`:

```css
.syl-builds { font-size: 12px; color: var(--text-dim, #8a7d6d); margin-top: 2px; }
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/pytest -q`
Expected: all PASS (existing transcript tests unaffected: the passed-row additions only append to the status string)

Run: `node --test frontend/tests/*.test.js`
Expected: all PASS

No app.js change in this task — no import check needed.

- [ ] **Step 8: Commit**

```bash
git add backend/transcript.py frontend/src/views/transcript.js frontend/src/views/syllabus.js frontend/styles.css tests/test_transcript.py frontend/tests/transcript.test.js frontend/tests/views.test.js
git commit -m "feat(transcript): capstone rows + attempts on passed rows; syllabus builds-on lines

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Final verification (after Task 7)

- [ ] Full suites one more time: `.venv/bin/pytest -q` and `node --test frontend/tests/*.test.js` — all PASS
- [ ] `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` — prints `imports ok`
- [ ] Deploy per `docs/DEPLOY.md` (NEVER `rsync --delete`). Legacy-data behavior on the Pi, per spec: cached capstones gain a rubric at first submission; legacy remediation sessions work without apply items; pre-existing failed exams require the gap review before retake immediately (intended); old remediation answers without markers do not count — the learner redoes the re-served session once.
