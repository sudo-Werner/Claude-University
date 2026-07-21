# Live Lesson-Generation Progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake lesson-generation wait with a background job on the Pi plus a real, polled activity feed and a topbar status chip.

**Architecture:** New in-memory job registry (`backend/jobs.py`) runs `generation.ensure_lesson` on a daemon thread; `claude_client.run_sourced` forwards its (currently discarded) stream-json events to a callback; three new Flask routes expose start/join, progress-since-N, and running-jobs; the frontend polls every 2s, renders a feed view, and paints a topbar chip. `generation.py` is untouched.

**Tech Stack:** Flask + waitress (Pi), vanilla-JS ESM frontend (no framework), pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-07-21-lesson-generation-progress-design.md`

## Global Constraints

- Never commit unless Werner explicitly asks. Never `rsync --delete` (see `docs/DEPLOY.md`).
- No emojis anywhere in code, UI copy, or commit messages.
- API JSON keys are camelCase (`courseId`, `lessonId`); Python identifiers snake_case.
- Event kinds are exactly: `stage`, `search`, `read`, `think`, `say`.
- Job snapshot shape is exactly: `{"status", "error", "courseId", "lessonId", "elapsed", "events", "next"}`; each event is `{"n", "kind", "text"}`; `status` is one of `running | done | error` (routes may also answer `done`/`none` without a job).
- Poll interval 2000 ms; job stream timeout 1200 s; finished-job linger 600 s.
- All user-visible strings rendered from JS go through `esc()` (`frontend/src/escape.js`).
- Backend suite must stay green: `cd /Users/wernervanellewee/Projects/Claude_Education && python -m pytest tests/ -q` (910 tests passed before this feature).
- Frontend suite: `cd frontend && node --test 'tests/*.test.js'` (358 tests passed before this feature). Note the quotes — bare `tests/` fails.
- `generation.py` must not be modified.

---

### Task 1: Job registry (`backend/jobs.py`)

**Files:**
- Create: `backend/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Produces: `jobs.start(course_id, lesson_id, run, describe_error=str) -> Job` (joins a running job instead of duplicating), `jobs.get(course_id, lesson_id) -> Job | None`, `jobs.running() -> list[Job]`, `jobs.reset()` (test helper), `Job.emit(kind, text)`, `Job.snapshot(since=0) -> dict` (shape per Global Constraints), `Job.thread` (worker `threading.Thread`, for tests to join).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jobs.py`:

```python
import threading

import pytest

from backend import jobs


@pytest.fixture(autouse=True)
def clean_registry():
    jobs.reset()
    yield
    jobs.reset()


def test_start_runs_job_and_records_done():
    done = threading.Event()

    def run(job):
        job.emit("stage", "working")
        done.set()

    job = jobs.start("c1", "l1", run)
    assert done.wait(2)
    job.thread.join(2)
    snap = job.snapshot()
    assert snap["status"] == "done"
    assert snap["error"] is None
    assert snap["courseId"] == "c1"
    assert snap["lessonId"] == "l1"
    assert snap["events"] == [{"n": 0, "kind": "stage", "text": "working"}]
    assert snap["next"] == 1
    assert snap["elapsed"] >= 0


def test_snapshot_since_returns_only_new_events():
    def run(job):
        job.emit("stage", "one")
        job.emit("say", "two")
        job.emit("read", "three")

    job = jobs.start("c1", "l1", run)
    job.thread.join(2)
    snap = job.snapshot(since=1)
    assert [e["text"] for e in snap["events"]] == ["two", "three"]
    assert snap["next"] == 3


def test_start_joins_running_job_instead_of_duplicating():
    release = threading.Event()
    started = threading.Event()
    calls = []

    def run(job):
        calls.append(1)
        started.set()
        release.wait(5)

    first = jobs.start("c1", "l1", run)
    assert started.wait(2)
    second = jobs.start("c1", "l1", run)
    assert second is first
    release.set()
    first.thread.join(2)
    assert calls == [1]


def test_error_is_translated_by_describe_error():
    def run(job):
        raise ValueError("boom")

    job = jobs.start("c1", "l1", run, describe_error=lambda e: f"friendly: {e}")
    job.thread.join(2)
    snap = job.snapshot()
    assert snap["status"] == "error"
    assert snap["error"] == "friendly: boom"


def test_get_and_running():
    release = threading.Event()

    def run(job):
        release.wait(5)

    job = jobs.start("c1", "l1", run)
    assert jobs.get("c1", "l1") is job
    assert jobs.get("c1", "other") is None
    assert jobs.running() == [job]
    release.set()
    job.thread.join(2)
    assert jobs.running() == []


def test_finished_jobs_linger_then_prune(monkeypatch):
    def run(job):
        pass

    job = jobs.start("c1", "l1", run)
    job.thread.join(2)
    assert jobs.get("c1", "l1") is job  # lingers within the window
    job.finished_at -= jobs._LINGER + 1  # age it past the window
    assert jobs.get("c1", "l1") is None


def test_a_new_job_can_start_after_a_failed_one():
    def bad(job):
        raise RuntimeError("nope")

    first = jobs.start("c1", "l1", bad)
    first.thread.join(2)
    second = jobs.start("c1", "l1", lambda job: None)
    assert second is not first
    second.thread.join(2)
    assert second.snapshot()["status"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_jobs.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.jobs'` (import error counts as the red step here; every test errors).

- [ ] **Step 3: Implement `backend/jobs.py`**

```python
"""In-memory lesson-generation jobs. One job per (course_id, lesson_id); a second
start while one is running joins it — a mid-wait refresh must never spawn a second
nine-minute generation. In-memory on purpose: a service restart kills the underlying
claude process anyway, so surviving rows could only ever say "interrupted"; the
routes' `none` answer says that without the ceremony."""
import threading
import time

_lock = threading.Lock()
_jobs = {}

# Finished jobs linger so a briefly-disconnected client can still read the outcome.
_LINGER = 600


class Job:
    def __init__(self, course_id, lesson_id):
        self.course_id = course_id
        self.lesson_id = lesson_id
        self.status = "running"
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.thread = None
        self._events = []
        self._elock = threading.Lock()

    def emit(self, kind, text):
        with self._elock:
            self._events.append({"n": len(self._events), "kind": kind, "text": text})

    def snapshot(self, since=0):
        with self._elock:
            events = self._events[since:]
        end = self.finished_at or time.time()
        return {
            "status": self.status,
            "error": self.error,
            "courseId": self.course_id,
            "lessonId": self.lesson_id,
            "elapsed": end - self.started_at,
            "events": events,
            "next": since + len(events),
        }


def start(course_id, lesson_id, run, describe_error=str):
    with _lock:
        _prune()
        existing = _jobs.get((course_id, lesson_id))
        if existing is not None and existing.status == "running":
            return existing
        job = Job(course_id, lesson_id)
        _jobs[(course_id, lesson_id)] = job

    def _worker():
        try:
            run(job)
            job.status = "done"
        except Exception as exc:
            job.error = describe_error(exc)
            job.status = "error"
        finally:
            job.finished_at = time.time()

    job.thread = threading.Thread(target=_worker, daemon=True)
    job.thread.start()
    return job


def get(course_id, lesson_id):
    with _lock:
        _prune()
        return _jobs.get((course_id, lesson_id))


def running():
    with _lock:
        _prune()
        return [j for j in _jobs.values() if j.status == "running"]


def _prune():
    # Callers hold _lock. Drop finished jobs older than the linger window.
    now = time.time()
    for key, job in list(_jobs.items()):
        if job.status != "running" and job.finished_at and now - job.finished_at > _LINGER:
            del _jobs[key]


def reset():
    """Test helper: forget every job."""
    with _lock:
        _jobs.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_jobs.py -q`
Expected: 7 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (910 + 7 new).

---

### Task 2: Event forwarding and translation (`backend/claude_client.py`)

**Files:**
- Modify: `backend/claude_client.py` (`_spawn_cli`, `run_sourced`; add `progress_events`)
- Test: `tests/test_claude_client.py` (append)

**Interfaces:**
- Consumes: existing `_spawn_cli`, `run_sourced` (module currently at `backend/claude_client.py`; `run_sourced` signature today: `(prompt, *, model=DEFAULT_MODEL, validate=None, spawn=_spawn_cli)`).
- Produces: `run_sourced(prompt, *, model=DEFAULT_MODEL, validate=None, spawn=None, timeout=None, on_event=None)` — `on_event` receives every parsed dict stream event; `timeout` overrides the 540s watchdog when `spawn` is not supplied. `progress_events(ev) -> list[dict]` returning `{"kind", "text"}` lines. `_spawn_cli(args, timeout=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claude_client.py` (it already imports the module as `cc` and defines `_sourced_lines()` near line 183 — reuse both):

```python
# ---- progress_events: stream-json -> user-facing feed lines ----

def _assistant(blocks):
    return {"type": "assistant", "message": {"content": blocks}}


def test_progress_events_translates_web_search():
    ev = _assistant([{"type": "tool_use", "name": "WebSearch", "input": {"query": "hormone signaling speed"}}])
    assert cc.progress_events(ev) == [{"kind": "search", "text": "Searching: hormone signaling speed"}]


def test_progress_events_translates_web_fetch_to_host():
    ev = _assistant([{"type": "tool_use", "name": "WebFetch", "input": {"url": "https://www.khanacademy.org/science/x1"}}])
    assert cc.progress_events(ev) == [{"kind": "read", "text": "Reading: www.khanacademy.org"}]


def test_progress_events_passes_narration_and_thinking():
    ev = _assistant([
        {"type": "thinking", "thinking": "The learner knows neurons already."},
        {"type": "text", "text": "Let me check the hormone half-life numbers."},
    ])
    assert cc.progress_events(ev) == [
        {"kind": "think", "text": "The learner knows neurons already."},
        {"kind": "say", "text": "Let me check the hormone half-life numbers."},
    ]


def test_progress_events_drops_json_payload_and_noise():
    assert cc.progress_events(_assistant([{"type": "text", "text": '{"id": "l4"}'}])) == []
    assert cc.progress_events(_assistant([{"type": "text", "text": "```json\n{}\n```"}])) == []
    assert cc.progress_events(_assistant([{"type": "text", "text": "   "}])) == []
    assert cc.progress_events({"type": "result", "result": "{}"}) == []
    assert cc.progress_events("not a dict") == []


def test_progress_events_clips_long_text():
    ev = _assistant([{"type": "text", "text": "x" * 500}])
    (line,) = cc.progress_events(ev)
    assert len(line["text"]) <= 200
    assert line["text"].endswith("…")


# ---- run_sourced: on_event forwarding and timeout plumbing ----

def test_run_sourced_forwards_parsed_events():
    seen = []
    cc.run_sourced("p", spawn=lambda args: iter(_sourced_lines()), on_event=seen.append)
    assert len(seen) == len([l for l in _sourced_lines()])
    assert all(isinstance(e, dict) for e in seen)


def test_run_sourced_default_spawn_carries_timeout(monkeypatch):
    captured = {}

    def fake_spawn_cli(args, timeout=None):
        captured["timeout"] = timeout
        line = '{"type": "result", "result": "{\\"ok\\": true}"}'
        return iter([line])

    monkeypatch.setattr(cc, "_spawn_cli", fake_spawn_cli)
    obj, sources = cc.run_sourced("p", timeout=1200)
    assert obj == {"ok": True}
    assert captured["timeout"] == 1200
```

Note: `test_run_sourced_forwards_parsed_events` assumes every `_sourced_lines()` line is valid JSON; if any line in that helper is deliberately malformed, assert `len(seen)` equals the count of parseable lines instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_claude_client.py -q`
Expected: new tests FAIL (`AttributeError: ... has no attribute 'progress_events'`, `TypeError: run_sourced() got an unexpected keyword argument`); existing tests still pass.

- [ ] **Step 3: Implement**

In `backend/claude_client.py`:

(a) Add `import urllib.parse` to the imports at the top.

(b) Change `_spawn_cli`'s signature and watchdog to accept an override:

```python
def _spawn_cli(args, timeout=None):
    wait = timeout or _STREAM_TIMEOUT
```

Inside, replace both uses of `_STREAM_TIMEOUT`: `watchdog = threading.Timer(wait, _kill_on_timeout)` and the raise becomes `raise ClaudeError(f"claude stream timed out after {wait}s")`. Nothing else in the function changes.

(c) Add the translator after `_extract_stream_text` (it owns CLI event shapes, so it lives in this module):

```python
def _clip(text, limit=200):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def progress_events(ev):
    """Translate one parsed stream-json event into 0..n user-facing feed lines
    ({"kind", "text"}). Only assistant events carry anything worth narrating;
    the model's JSON payload (the lesson itself) is deliberately dropped — the
    feed shows what the model is DOING, the lesson view shows the result."""
    if not isinstance(ev, dict) or ev.get("type") != "assistant":
        return []
    lines = []
    for block in ev.get("message", {}).get("content", []):
        btype = block.get("type")
        if btype == "tool_use":
            name = block.get("name")
            inp = block.get("input") or {}
            if name == "WebSearch" and inp.get("query"):
                lines.append({"kind": "search", "text": "Searching: " + _clip(inp["query"], 160)})
            elif name == "WebFetch" and inp.get("url"):
                host = urllib.parse.urlparse(inp["url"]).netloc or inp["url"]
                lines.append({"kind": "read", "text": "Reading: " + _clip(host, 160)})
        elif btype == "thinking":
            text = (block.get("thinking") or "").strip()
            if text:
                lines.append({"kind": "think", "text": _clip(text)})
        elif btype == "text":
            text = (block.get("text") or "").strip()
            if text and not text.startswith("{") and not text.startswith("```"):
                lines.append({"kind": "say", "text": _clip(text)})
    return lines
```

(d) Rework `run_sourced`'s signature and loop. Full replacement of the function:

```python
def run_sourced(prompt, *, model=DEFAULT_MODEL, validate=None, spawn=None, timeout=None, on_event=None):
    """Web-search-grounded structured generation. Runs the CLI with WebSearch/WebFetch
    and stream-json, returning (parsed_final_json, captured_sources) where captured_sources
    are the real {title, url} pairs retrieved from the actual search results.
    on_event (if given) receives every parsed stream event — the progress feed's tap.
    timeout overrides the module watchdog (a background job has no HTTP channel to race)."""
    if spawn is None:
        spawn = lambda a: _spawn_cli(a, timeout=timeout)
    args_for = lambda p: [
        "-p", p, "--allowedTools", "WebSearch", "WebFetch",
        "--output-format", "stream-json", "--verbose", "--model", model,
    ]
    for attempt in range(2):
        sources, seen, result_text = [], set(), ""
        for line in spawn(args_for(prompt)):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("api_error_status") in (401, 403):
                raise ClaudeAuthError(ev.get("result") or "Claude authentication failed.")
            if on_event is not None:
                on_event(ev)
            _collect_sources(ev, sources, seen)
            if isinstance(ev, dict) and ev.get("type") == "result" and ev.get("result"):
                result_text = ev["result"]
        obj = extract_json(result_text)
        if obj is not None and (validate is None or validate(obj)):
            return obj, sources
        prompt = (
            prompt
            + "\n\nYour previous reply was not valid JSON matching the required shape. "
            "Reply again with ONLY the JSON object, no prose, no code fence."
        )
    raise ClaudeError("sourced generation failed after retry")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_claude_client.py -q`
Expected: all pass (existing + 8 new).

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: all pass.

---

### Task 3: API routes (`backend/app.py`)

**Files:**
- Modify: `backend/app.py` (refactor `get_lesson` lines ~297-305 into a helper; add three routes after `lesson_status`, which ends at line ~341)
- Test: `tests/test_generation_jobs.py` (create)

**Interfaces:**
- Consumes: `jobs.start/get/running` (Task 1), `claude_client.run_sourced(on_event=, timeout=)` and `claude_client.progress_events` (Task 2), existing `generation.ensure_lesson`, `courses.load_lesson/load_manifest/flatten_lessons`, `_ID_RE`.
- Produces: `POST /api/courses/<c>/lessons/<l>/generate` (202 + snapshot; `{"status": "done", ...}` 200 if cached), `GET /api/courses/<c>/lessons/<l>/generate?since=N` (snapshot | `done` | `none`), `GET /api/generation-jobs` (`{"jobs": [{courseId, lessonId, status, elapsed}]}`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generation_jobs.py`. Model the fixture on `tests/test_api.py`'s `client` fixture; write real course content the way `test_api.py` does with `monkeypatch.setattr(courses, "CONTENT_DIR", ...)` (copy its manifest-writing helper shape — read that file first and reuse its idiom):

```python
import json

import pytest

from backend import claude_client, courses, jobs


@pytest.fixture(autouse=True)
def clean_registry():
    jobs.reset()
    yield
    jobs.reset()


@pytest.fixture
def client(tmp_path):
    from backend.app import create_app

    db_path = tmp_path / "test_jobs.db"
    app = create_app(db_path=db_path)
    app.config.update(TESTING=True, DB_PATH=db_path)
    return app.test_client()


def _write_course(root, course_id="humanbody", lesson_id="humanbody-l1"):
    cdir = root / "courses" / course_id
    (cdir / "lessons").mkdir(parents=True)
    manifest = {
        "id": course_id, "title": "Human Body", "version": 2,
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": lesson_id, "title": "Cells", "topic": "Cells"},
        ]}],
    }
    (cdir / "course.json").write_text(json.dumps(manifest))
    return cdir


def _lesson_json(course_id, lesson_id):
    return {"id": lesson_id, "courseId": course_id, "topic": "Cells"}


def test_post_starts_job_and_get_polls_it(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fake_ensure(content_dir, course_id, lesson_id, prof, *, generate, **kw):
        kw["verify_generate"]("audit prompt", lambda o: True)
        (cdir / "lessons" / f"{lesson_id}.json").write_text(
            json.dumps(_lesson_json(course_id, lesson_id)))
        return _lesson_json(course_id, lesson_id)

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fake_ensure)
    monkeypatch.setattr(claude_client, "structured_generate", lambda p, v: {"ok": True})

    resp = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] in ("running", "done")

    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)

    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate?since=0")
    body = resp.get_json()
    assert body["status"] == "done"
    texts = [e["text"] for e in body["events"]]
    assert "Researching and drafting the lesson…" in texts
    assert "Fact-check audit…" in texts
    assert "Lesson saved." in texts
    assert body["next"] == len(texts)


def test_post_dedups_a_running_job(client, tmp_path, monkeypatch):
    import threading
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson",
                        lambda *a, **k: release.wait(5))

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    first = jobs.get("humanbody", "humanbody-l1")
    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert jobs.get("humanbody", "humanbody-l1") is first
    release.set()
    first.thread.join(5)


def test_post_on_cached_lesson_returns_done_without_job(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    (cdir / "lessons" / "humanbody-l1.json").write_text(
        json.dumps(_lesson_json("humanbody", "humanbody-l1")))
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "done"
    assert jobs.get("humanbody", "humanbody-l1") is None


def test_get_without_job_says_done_or_none(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    cdir = _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.get_json()["status"] == "none"

    (cdir / "lessons" / "humanbody-l1.json").write_text(
        json.dumps(_lesson_json("humanbody", "humanbody-l1")))
    resp = client.get("/api/courses/humanbody/lessons/humanbody-l1/generate")
    assert resp.get_json()["status"] == "done"


def test_auth_failure_surfaces_reauth_message(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fail(*a, **k):
        raise claude_client.ClaudeAuthError("expired")

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fail)

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)
    body = client.get(
        "/api/courses/humanbody/lessons/humanbody-l1/generate").get_json()
    assert body["status"] == "error"
    assert "re-authentication" in body["error"]


def test_timeout_failure_says_took_too_long(client, tmp_path, monkeypatch):
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    def fail(*a, **k):
        raise claude_client.ClaudeError("claude stream timed out after 1200s")

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson", fail)

    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    job = jobs.get("humanbody", "humanbody-l1")
    job.thread.join(5)
    body = client.get(
        "/api/courses/humanbody/lessons/humanbody-l1/generate").get_json()
    assert body["status"] == "error"
    assert "too long" in body["error"]


def test_unknown_ids_404(client):
    assert client.post("/api/courses/nope/lessons/x/generate").status_code == 404
    assert client.get("/api/courses/nope/lessons/x/generate").status_code == 404


def test_generation_jobs_lists_running_only(client, tmp_path, monkeypatch):
    import threading
    root = tmp_path / "content"
    _write_course(root)
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    release = threading.Event()

    from backend import generation
    monkeypatch.setattr(generation, "ensure_lesson",
                        lambda *a, **k: release.wait(5))

    assert client.get("/api/generation-jobs").get_json() == {"jobs": []}
    client.post("/api/courses/humanbody/lessons/humanbody-l1/generate")
    body = client.get("/api/generation-jobs").get_json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["courseId"] == "humanbody"
    assert body["jobs"][0]["lessonId"] == "humanbody-l1"
    assert body["jobs"][0]["status"] == "running"
    release.set()
    jobs.get("humanbody", "humanbody-l1").thread.join(5)
```

Adjust `_write_course` to whatever manifest shape `courses.load_manifest`/`flatten_lessons` actually require — copy the working helper from `tests/test_api.py` rather than trusting the sketch above; the assertions are the contract, the fixture shape is not.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generation_jobs.py -q`
Expected: FAIL — POST/GET routes return 404 (routes don't exist yet).

- [ ] **Step 3: Implement in `backend/app.py`**

(a) Add `jobs` to the existing `from backend import ...` (or `import` block) at the top.

(b) Module-level constant near the other constants:

```python
# A background job has no HTTP channel to race (the old 540s watchdog existed only
# to die before waitress's --channel-timeout). This is purely a hung-CLI guard.
_JOB_TIMEOUT = 1200
```

(c) Extract the input-building block of `get_lesson` (currently lines ~297-305: the `db.get_connection` block plus `prof_data` and `misconception_texts`) into a helper inside `create_app` (it closes over `path`), and call it from `get_lesson` so behaviour is identical:

```python
    def _lesson_gen_inputs(course_id, lesson_id):
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            performance = mastery.performance_summary(conn, courses.CONTENT_DIR, course_id)
            prior_knowledge = queries.latest_prior_knowledge(conn, course_id, lesson_id)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        misconception_texts = [e["text"] for e in misconceptions.load_profile(courses.CONTENT_DIR, course_id)]
        return prof_data, performance, prior_knowledge, misconception_texts
```

In `get_lesson`, replace those lines with `prof_data, performance, prior_knowledge, misconception_texts = _lesson_gen_inputs(course_id, lesson_id)`.

(d) Error translation helper (module level or inside `create_app`, matching neighbours):

```python
def _job_error_message(exc):
    if isinstance(exc, claude_client.ClaudeAuthError):
        return "Claude needs re-authentication on the Pi — run `claude` there to log in again."
    if isinstance(exc, claude_client.ClaudeError):
        if "timed out" in str(exc):
            return "Generation took too long and was stopped — try again."
        return "The model couldn't produce a valid lesson after a retry — try again."
    return "Something unexpected went wrong during generation."
```

(e) The three routes, placed directly after `lesson_status`:

```python
    def _lesson_in_manifest(course_id, lesson_id):
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return False
        return lesson_id in {l["id"] for l in courses.flatten_lessons(manifest)}

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/generate")
    def start_lesson_generation(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        if not _lesson_in_manifest(course_id, lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        if courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id) is not None:
            return jsonify({"status": "done", "error": None, "courseId": course_id,
                            "lessonId": lesson_id, "elapsed": 0, "events": [], "next": 0})
        prof_data, performance, prior_knowledge, misconception_texts = \
            _lesson_gen_inputs(course_id, lesson_id)

        def run(job):
            job.emit("stage", "Researching and drafting the lesson…")

            def on_event(ev):
                for line in claude_client.progress_events(ev):
                    job.emit(line["kind"], line["text"])

            generate = lambda prompt: claude_client.run_sourced(
                prompt, validate=generation.valid_lesson,
                on_event=on_event, timeout=_JOB_TIMEOUT,
            )
            verify_calls = {"n": 0}

            def verify(prompt, validate):
                verify_calls["n"] += 1
                job.emit("stage", "Fact-check audit…" if verify_calls["n"] == 1
                         else "Revising flagged issues…")
                return claude_client.structured_generate(prompt, validate)

            generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance, verify_generate=verify,
                prior_knowledge=prior_knowledge, misconceptions=misconception_texts,
            )
            job.emit("stage", "Lesson saved.")

        job = jobs.start(course_id, lesson_id, run, describe_error=_job_error_message)
        return jsonify(job.snapshot(0)), 202

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/generate")
    def lesson_generation_progress(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        if not _lesson_in_manifest(course_id, lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        since = request.args.get("since", 0, type=int)
        job = jobs.get(course_id, lesson_id)
        if job is not None:
            return jsonify(job.snapshot(since))
        # No job in memory: the lesson file is the truth. Present -> done (job
        # already pruned); absent -> none (never started, or lost to a service
        # restart -- the client says "interrupted" and offers retry).
        done = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id) is not None
        return jsonify({"status": "done" if done else "none", "error": None,
                        "courseId": course_id, "lessonId": lesson_id,
                        "elapsed": 0, "events": [], "next": since})

    @app.get("/api/generation-jobs")
    def list_generation_jobs():
        return jsonify({"jobs": [
            {"courseId": j.course_id, "lessonId": j.lesson_id,
             "status": j.status, "elapsed": j.snapshot()["elapsed"]}
            for j in jobs.running()
        ]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generation_jobs.py -q`
Expected: 8 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: all pass — including every pre-existing `get_lesson` test (the refactor must not change its behaviour).

---

### Task 4: Frontend API helpers + feed view (`courses.js`, `views/genfeed.js`)

**Files:**
- Modify: `frontend/src/courses.js` (append three helpers)
- Create: `frontend/src/views/genfeed.js`
- Test: `frontend/tests/courses.test.js` (append), `frontend/tests/genfeed.test.js` (create)

**Interfaces:**
- Produces: `startLessonGeneration({fetch, courseId, lessonId})`, `getGenerationProgress({fetch, courseId, lessonId, since})`, `listGenerationJobs({fetch})`; `genFeedHTML(title)`, `genLineHTML(ev)`, `genErrorHTML(message)`, `genChipHTML(job)`, `formatElapsed(seconds)`.
- Consumes: snapshot shape from Task 3; `esc()` from `../escape.js`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/courses.test.js` (extend its import line with the three new names):

```js
test("startLessonGeneration POSTs and returns the snapshot", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ status: "running", events: [], next: 0 }) };
  };
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.equal(url, "/api/courses/c1/lessons/l1/generate");
  assert.equal(opts.method, "POST");
  assert.equal(snap.status, "running");
});

test("startLessonGeneration surfaces a server error message", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "lesson not found" }) });
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.equal(snap.error, "lesson not found");
});

test("startLessonGeneration never throws on network failure", async () => {
  const fetch = async () => { throw new Error("offline"); };
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.ok(snap.error);
});

test("getGenerationProgress passes since and returns the snapshot", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ status: "running", events: [{ n: 3 }], next: 4 }) };
  };
  const snap = await getGenerationProgress({ fetch, courseId: "c1", lessonId: "l1", since: 3 });
  assert.equal(url, "/api/courses/c1/lessons/l1/generate?since=3");
  assert.equal(snap.next, 4);
});

test("getGenerationProgress returns error on failure without throwing", async () => {
  const fetch = async () => { throw new Error("offline"); };
  const snap = await getGenerationProgress({ fetch, courseId: "c1", lessonId: "l1", since: 0 });
  assert.ok(snap.error);
});

test("listGenerationJobs returns jobs array, [] on failure", async () => {
  const good = async () => ({ ok: true, json: async () => ({ jobs: [{ courseId: "c1" }] }) });
  const bad = async () => { throw new Error("offline"); };
  assert.deepEqual((await listGenerationJobs({ fetch: good })).jobs, [{ courseId: "c1" }]);
  assert.deepEqual((await listGenerationJobs({ fetch: bad })).jobs, []);
});
```

Create `frontend/tests/genfeed.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { genFeedHTML, genLineHTML, genErrorHTML, genChipHTML, formatElapsed } from "../src/views/genfeed.js";

test("genFeedHTML includes escaped title, feed slot, elapsed slot", () => {
  const html = genFeedHTML("<b>Cells</b>");
  assert.ok(html.includes("&lt;b&gt;Cells&lt;/b&gt;"));
  assert.ok(html.includes("data-gen-feed"));
  assert.ok(html.includes("data-gen-elapsed"));
  assert.ok(!html.includes("<b>Cells</b>"));
});

test("genLineHTML sets the kind class and escapes text", () => {
  const html = genLineHTML({ kind: "search", text: "Searching: <x>" });
  assert.ok(html.includes("gen-search"));
  assert.ok(html.includes("Searching: &lt;x&gt;"));
});

test("genErrorHTML shows the message and a retry action", () => {
  const html = genErrorHTML("It broke");
  assert.ok(html.includes("It broke"));
  assert.ok(html.includes('data-action="gen-retry"'));
});

test("genChipHTML covers empty, running, done, error", () => {
  assert.equal(genChipHTML(null), "");
  assert.ok(genChipHTML({ status: "running", elapsed: 125 }).includes("2:05"));
  assert.ok(genChipHTML({ status: "done" }).includes('data-action="gen-open"'));
  assert.ok(genChipHTML({ status: "error" }).includes('data-action="gen-open"'));
});

test("formatElapsed renders m:ss", () => {
  assert.equal(formatElapsed(0), "0:00");
  assert.equal(formatElapsed(65), "1:05");
  assert.equal(formatElapsed(600.7), "10:00");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && node --test 'tests/*.test.js'`
Expected: FAIL — missing exports / missing `views/genfeed.js`.

- [ ] **Step 3: Implement**

Append to `frontend/src/courses.js` (same idiom as `getLessonStatus` — these must never throw):

```js
// Live generation progress (2026-07-21 design). All three never reject: a network
// blip mid-poll must read as "try again next tick", never a crashed feed.
export async function startLessonGeneration({ fetch, courseId, lessonId }) {
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/generate`, { method: "POST" });
    if (!resp.ok) {
      return { error: await parseErrorBody(resp, "Couldn't start generating this lesson.") };
    }
    return await resp.json();
  } catch (e) {
    return { error: "Couldn't start generating this lesson." };
  }
}

export async function getGenerationProgress({ fetch, courseId, lessonId, since = 0 }) {
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/generate?since=${since}`);
    if (!resp.ok) return { error: "progress unavailable" };
    return await resp.json();
  } catch (e) {
    return { error: "progress unavailable" };
  }
}

export async function listGenerationJobs({ fetch }) {
  try {
    const resp = await fetch("/api/generation-jobs");
    if (!resp.ok) return { jobs: [] };
    const body = await resp.json();
    return { jobs: body.jobs || [] };
  } catch (e) {
    return { jobs: [] };
  }
}
```

Create `frontend/src/views/genfeed.js`:

```js
import { esc } from "../escape.js";

// The live-generation screen: everything in it is a REAL event from the model's
// stream (searches, pages read, thinking, narration) or a pipeline stage marker.
// Never invent activity here — the whole point is replacing the fake cycled
// status with the truth.

export function formatElapsed(seconds) {
  const s = Math.floor(seconds || 0);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function genFeedHTML(title) {
  return (
    `<div class="card lesson gen-card">` +
    `<div class="gen-head"><span class="load-dot"></span>` +
    `<span class="gen-title">Generating: ${esc(title)}</span>` +
    `<span class="gen-elapsed" data-gen-elapsed></span></div>` +
    `<div class="gen-feed" data-gen-feed></div>` +
    `<p class="gen-note">This takes a few minutes. You can do reviews meanwhile or ` +
    `close the app entirely — generation continues on the server and the lesson ` +
    `will be waiting.</p>` +
    `</div>`
  );
}

export function genLineHTML(ev) {
  return `<div class="gen-line gen-${esc(ev.kind)}">${esc(ev.text)}</div>`;
}

export function genErrorHTML(message) {
  return (
    `<div class="card lesson gen-card">` +
    `<p class="gen-error">${esc(message)}</p>` +
    `<button class="gen-retry" data-action="gen-retry">Try again</button>` +
    `</div>`
  );
}

export function genChipHTML(job) {
  if (!job) return "";
  if (job.status === "done") {
    return `<button class="gen-chip gen-chip-ready" data-action="gen-open">Lesson ready — open</button>`;
  }
  if (job.status === "error") {
    return `<button class="gen-chip gen-chip-err" data-action="gen-open">Generation failed — retry</button>`;
  }
  return `<span class="gen-chip">Generating lesson… ${esc(formatElapsed(job.elapsed))}</span>`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && node --test 'tests/*.test.js'`
Expected: all pass (358 + 11 new).

---

### Task 5: Feed screen wiring in `app.js` + feed styles

**Files:**
- Modify: `frontend/src/app.js` (imports; `ui` state literal ~line 86; `paintActivate`'s `continueToLesson` ~line 1462; `openLesson` ~line 1414; new functions after `finishOpenLesson` ~line 1506)
- Modify: `frontend/styles.css` (append)

**Interfaces:**
- Consumes: Task 4 exports; existing `finishOpenLesson(lessonId, opts, seq)`, `startLoading`, `LESSON_STAGES`, `flatLessons()`, `ui.loadSeq` guard idiom, `root` DOM-presence idiom (`startLoading`'s `isConnected` self-clear).
- Produces: `ui.genJob` state (`{courseId, lessonId, next, status, elapsed}`), `startGenerationFeed(lessonId, seq)`, `scheduleGenPoll()`, `pollGeneration()`, `appendGenEvents(snap)`, `onGenerationDone(job)`, `onGenerationFailed(job, message)`, `ui.genRetry`. `paintGenChip()` is created here as a stub and completed in Task 6.

No unit-test harness exists for `app.js` (repo convention); verification for this task is the full frontend suite (no regressions), the import-resolution check, and Task 7's E2E.

- [ ] **Step 1: Add imports and state**

Extend the `./courses.js` import list with `startLessonGeneration, getGenerationProgress, listGenerationJobs`. Add below the views imports:

```js
import { genFeedHTML, genLineHTML, genErrorHTML, genChipHTML, formatElapsed } from "./views/genfeed.js";
```

In the `ui` state literal, add:

```js
    genJob: null,
    genRetry: null,
    genPollTimer: null,
```

- [ ] **Step 2: Add the feed functions** (after `finishOpenLesson`)

```js
  // ---- live generation feed (2026-07-21 design) ----
  // The job lives on the server; ui.genJob only mirrors it. The feed's DOM
  // presence (data-gen-feed) is the truth for "is the learner watching" — the
  // same idiom startLoading uses — so roaming needs no bookkeeping.
  function paintGenChip() {
    root.querySelectorAll("[data-gen-chip]").forEach((slot) => {
      slot.innerHTML = genChipHTML(ui.genJob);
    });
  }

  function appendGenEvents(snap) {
    if (ui.genJob) ui.genJob.next = snap.next;
    const feed = root.querySelector("[data-gen-feed]");
    if (feed && (snap.events || []).length) {
      for (const ev of snap.events) feed.insertAdjacentHTML("beforeend", genLineHTML(ev));
      feed.scrollTop = feed.scrollHeight;
    }
    const el = root.querySelector("[data-gen-elapsed]");
    if (el && snap.elapsed != null) el.textContent = formatElapsed(snap.elapsed);
  }

  function scheduleGenPoll() {
    // Clear-then-arm (same idiom as ui.arcadePollTimer): rejoining the feed calls
    // startGenerationFeed again, and without the clear the old chain and the new
    // one would BOTH tick — duplicate polls and duplicated feed lines.
    window.clearTimeout(ui.genPollTimer);
    ui.genPollTimer = window.setTimeout(pollGeneration, 2000);
  }

  async function pollGeneration() {
    const job = ui.genJob;
    if (!job) return; // opened/cleared — the chain ends here
    if (job.status !== "running") {
      // done/error while roaming: no network needed, but keep the chip painted
      // across shell repaints (navigation empties the slot).
      paintGenChip();
      scheduleGenPoll();
      return;
    }
    const snap = await getGenerationProgress({
      fetch, courseId: job.courseId, lessonId: job.lessonId, since: job.next,
    });
    if (ui.genJob !== job) return; // superseded while awaiting
    if (snap.error) { scheduleGenPoll(); return; } // network blip — next tick retries
    job.status = snap.status;
    job.elapsed = snap.elapsed;
    appendGenEvents(snap);
    paintGenChip();
    if (snap.status === "running") { scheduleGenPoll(); return; }
    if (snap.status === "done") { onGenerationDone(job); return; }
    onGenerationFailed(job, snap.error || (snap.status === "none"
      ? "Generation was interrupted on the server — try again."
      : "Something went wrong during generation."));
  }

  async function startGenerationFeed(lessonId, seq) {
    ui.screen = "generating";
    const found = flatLessons().find((l) => l.id === lessonId);
    const view = root.querySelector("#view");
    if (view) view.innerHTML = genFeedHTML(found ? found.title : lessonId);
    const snap = await startLessonGeneration({ fetch, courseId: ui.courseId, lessonId });
    if (ui.loadSeq !== seq) return; // navigated away — the job runs on regardless
    if (snap.error) {
      ui.genRetry = { lessonId };
      if (view && view.isConnected) view.innerHTML = genErrorHTML(snap.error);
      return;
    }
    ui.genJob = {
      courseId: ui.courseId, lessonId, next: 0,
      status: snap.status, elapsed: snap.elapsed || 0,
    };
    appendGenEvents(snap); // POST returns the snapshot from 0 — the backfill on rejoin
    paintGenChip();
    if (snap.status === "done") { onGenerationDone(ui.genJob); return; }
    scheduleGenPoll();
  }

  function onGenerationDone(job) {
    if (ui.screen === "generating" && root.querySelector("[data-gen-feed]")) {
      ui.genJob = null;
      paintGenChip();
      ui.screen = "lesson-loading";
      const v = root.querySelector("#view");
      if (v) startLoading(v, "lesson", LESSON_STAGES);
      finishOpenLesson(job.lessonId, {}, ui.loadSeq);
      return;
    }
    paintGenChip();
    scheduleGenPoll(); // keep the "ready" chip alive across navigations
  }

  function onGenerationFailed(job, message) {
    job.message = message;
    if (ui.screen === "generating" && root.querySelector("[data-gen-feed]")) {
      ui.genJob = null;
      paintGenChip();
      ui.genRetry = { lessonId: job.lessonId };
      const v = root.querySelector("#view");
      if (v) v.innerHTML = genErrorHTML(message);
      return;
    }
    paintGenChip();
    scheduleGenPoll(); // keep the "failed" chip alive across navigations
  }
```

- [ ] **Step 3: Route the uncached-lesson path through the feed**

In `paintActivate`'s `continueToLesson` (~line 1462), replace the body:

```js
    const continueToLesson = async () => {
      await startGenerationFeed(lessonId, seq);
    };
```

(The activate card only ever shows when the lesson is not yet generated, so continue always means "generate". The old skeleton path survives untouched for cached lessons and reviews via `finishOpenLesson`.)

In `openLesson`, directly after the `if (!lessonId) return;` line, add the rejoin branch:

```js
    // Rejoining a lesson whose generation is already running: skip the status
    // check and the prior-knowledge card (it was answered when the job started)
    // and drop straight back into the live feed.
    if (ui.genJob && ui.genJob.courseId === ui.courseId
        && ui.genJob.lessonId === lessonId && ui.genJob.status === "running") {
      ui.reviewQueue = [];
      ui.loadSeq = (ui.loadSeq || 0) + 1;
      startGenerationFeed(lessonId, ui.loadSeq);
      return;
    }
```

- [ ] **Step 4: Retry action in the root click delegation**

In the existing `root.addEventListener("click", ...)` block (the one handling `feedback-toggle`), add before the feedback branches:

```js
    if (e.target.closest('[data-action="gen-retry"]')) {
      const t = ui.genRetry;
      ui.genRetry = null;
      if (t) openLesson(t.lessonId);
      return;
    }
```

(`openLesson` re-runs the status check; the lesson is still ungenerated, so the learner passes the activate card again — skippable — and a fresh POST starts a new job, which the registry allows because the failed one is not `running`.)

- [ ] **Step 5: Feed styles**

Append to `frontend/styles.css`:

```css
/* ---- live generation feed (2026-07-21) ---- */
.gen-head{display:flex; align-items:center; gap:9px}
.gen-title{font-size:14px; font-weight:600; color:var(--text)}
.gen-elapsed{margin-left:auto; font-size:13px; color:var(--text-dim); font-variant-numeric:tabular-nums}
.gen-feed{margin-top:14px; max-height:340px; overflow-y:auto; display:flex; flex-direction:column; gap:5px}
.gen-line{font-size:13px; line-height:1.45; color:var(--text-2)}
.gen-line.gen-stage{font-weight:600; color:var(--text); margin-top:7px}
.gen-line.gen-think{font-style:italic; color:var(--text-dim)}
.gen-line.gen-search,.gen-line.gen-read{color:var(--blue-text)}
.gen-note{margin-top:12px; font-size:13px; color:var(--text-mut)}
.gen-error{font-size:14px; color:var(--text)}
.gen-retry{margin-top:10px}
```

(`--text`, `--text-2`, `--text-dim`, `--text-mut`, `--blue-text` are existing tokens in `:root`. `.gen-retry` inherits the app's default button styling; only add more if it renders unstyled.)

- [ ] **Step 6: Verify**

Run: `cd frontend && node --test 'tests/*.test.js'`
Expected: all pass.
Run the import-resolution check from the repo root:
`cd frontend && node -e "import('./src/app.js').catch(e => { console.error(e); process.exit(1); })"`
Expected: exits 0 (module graph resolves; DOM errors are fine only if the import itself resolved — if this harness errors on missing DOM globals before finishing imports, fall back to `node --check` on each changed file plus grep-verifying every imported name exists in its source module).

---

### Task 6: Topbar chip + boot reattach

**Files:**
- Modify: `frontend/src/views/shell.js` (topbar), `frontend/src/app.js` (click delegation + `init` tail), `frontend/styles.css` (chip styles)
- Test: `frontend/tests/shell.test.js` if it exists (append a slot assertion); otherwise covered by suite + E2E

**Interfaces:**
- Consumes: `paintGenChip`, `scheduleGenPoll`, `ui.genJob` (Task 5), `openCourse(courseId)` (app.js ~line 426), `listGenerationJobs` (Task 4).
- Produces: `<span data-gen-chip></span>` slot in every shell paint; `openGenTarget()`.

- [ ] **Step 1: Add the slot to the shell**

In `frontend/src/views/shell.js`, `shellHTML`, change the topbar to:

```js
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <span data-gen-chip></span>
      <button class="fb-toggle" data-action="feedback-toggle" data-fb-toggle="top">Feedback</button>
    </header>
```

If `frontend/tests/shell.test.js` exists, first add the failing assertion that `shellHTML({})` contains `data-gen-chip`, run it red, then make the change. If it does not exist, make the change directly (creating a test file for one static-markup assertion is not worth a new harness — the suite + E2E cover it).

Navigation repaints the shell with an empty slot; the poll chain repaints it within one tick (≤2s). That blink is accepted — it is how the feedback bar already behaves.

- [ ] **Step 2: Chip click opens the target lesson**

In `app.js`, add next to the feed functions:

```js
  async function openGenTarget() {
    const job = ui.genJob;
    if (!job) return;
    ui.genJob = null;
    paintGenChip();
    if (ui.courseId !== job.courseId) await openCourse(job.courseId);
    openLesson(job.lessonId);
  }
```

And in the root click delegation, alongside the gen-retry branch:

```js
    if (e.target.closest('[data-action="gen-open"]')) { openGenTarget(); return; }
```

(For a `done` job this opens a now-cached lesson instantly. For an `error` job it re-enters the normal uncached flow — status check, activate card, fresh POST — which is exactly the retry path.)

- [ ] **Step 3: Reattach on boot**

At the end of `init` in `app.js` (after the initial screen paint, before its `return`), add — deliberately not awaited, boot must not wait on it:

```js
  // A page reload must not orphan a running generation: rejoin it and show the
  // chip. Fire-and-forget — boot never blocks on this.
  listGenerationJobs({ fetch }).then((resp) => {
    const running = (resp.jobs || []).find((j) => j.status === "running");
    if (!running || ui.genJob) return;
    ui.genJob = {
      courseId: running.courseId, lessonId: running.lessonId,
      next: 0, status: "running", elapsed: running.elapsed || 0,
    };
    paintGenChip();
    scheduleGenPoll();
  });
```

- [ ] **Step 4: Chip styles**

Append to `frontend/styles.css`:

```css
.gen-chip{font-size:12px; font-weight:600; color:var(--text-dim); white-space:nowrap; font-variant-numeric:tabular-nums}
button.gen-chip{cursor:pointer; border:1px solid var(--border-glass); border-radius:var(--r-sm); padding:4px 10px; background:var(--glass-field); font-family:var(--ui)}
.gen-chip-ready{color:var(--purple-deep)}
.gen-chip-err{color:var(--text)}
```

- [ ] **Step 5: Verify**

Run: `cd frontend && node --test 'tests/*.test.js'` — all pass.
Re-run the Task 5 import-resolution check — resolves.

---

### Task 7: Full verification and Pi deployment

**Files:** none created; this task is verification and deployment.

- [ ] **Step 1: Full local verification**

```bash
cd /Users/wernervanellewee/Projects/Claude_Education
python -m pytest tests/ -q
cd frontend && node --test 'tests/*.test.js'
```

Expected: everything green (~925 backend, ~369 frontend).

- [ ] **Step 2: STOP — confirm with Werner before deploying**

Deployment restarts the live service. Confirm: (a) permission to deploy, (b) `pgrep -fa "claude -p"` on the Pi shows no in-flight generation about to be killed.

- [ ] **Step 3: Deploy** (canonical command from `docs/DEPLOY.md` — never `--delete`), restart `claude-university`, verify `/api/health` returns `{"status":"ok"}` and `/api/courses` is non-empty.

- [ ] **Step 4: E2E — real generation with the real feed**

On the Pi URL (Tailscale `http://100.99.33.106:8200` — plain HTTP; remember secure-context APIs are unavailable, don't add any):

1. `POST /api/courses/<course>/lessons/<next-ungenerated>/generate` via curl → 202, `status: running`.
2. Poll `GET .../generate?since=N` a few times → events accumulate: the initial stage line, then real `search`/`read`/`say` lines.
3. `GET /api/generation-jobs` → lists the job.
4. In the browser: open the generating lesson → live feed visible; navigate to the dashboard → chip shows "Generating lesson… m:ss"; reload the page → chip reattaches; return to the lesson → feed backfills.
5. Wait for completion → feed hands off to the rendered lesson; from elsewhere the chip flips to "Lesson ready — open" and clicking it opens the lesson.
6. Confirm the stored lesson file is valid and its spine entry exists (same checks as the 2026-07-21 l4 verification).

Report results with evidence (curl output, what the feed showed). Do not claim success without step 4.
