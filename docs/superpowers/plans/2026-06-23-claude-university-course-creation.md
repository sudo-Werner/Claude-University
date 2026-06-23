# Claude University — Course Creation & JIT Lessons (Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Werner (plain-language review):** Each task opens with a **What / Why / Verify** line. Read those. Task 0 is a spike — a go/no-go experiment on the Pi before any feature code.

**Goal:** Make "Add a course" work — a streamed chat with Claude that proposes a curriculum you approve, plus lessons generated the moment you reach them — all via the Pi's Max-subscription Claude Code, no API key.

**Architecture:** A single `claude_client` boundary shells out to the Pi's `claude -p` (subscription auth) — one structured-JSON entry point (with one retry) and one streaming entry point. A chat endpoint relays turns to it as SSE and detects a fenced curriculum proposal; a create endpoint writes the manifest + a saved generation `brief`; the Slice 1 lesson endpoint generates-on-miss. Pure helpers (JSON extraction, proposal detection, slug, validation, prompt builders) are unit-tested with fakes; only the spike and the final run touch real Claude.

**Tech Stack:** Flask + SQLite + the `claude` CLI (Claude Code) on the Pi; plain ES modules with `node --test`; Playwright for the real-browser check. No new Python dependencies, no frontend framework.

## Global Constraints

- Claude is invoked **only** through the `claude_client` boundary, which runs the Pi's `claude -p` under the existing Max-subscription OAuth (`~/.claude/.credentials.json`). **No `ANTHROPIC_API_KEY`, no metered Messages API.**
- Default generation model is **`claude-sonnet-4-6`** (`--model`), to conserve Max usage limits. Configurable.
- Generated lessons conform to the **existing** lesson schema so the Slice 1 lesson screen renders them unchanged: `{ id, courseId, topic, step, totalSteps, eyebrow, promptHtml, hintHtml, solutionAns, solutionNote }`.
- Course manifests keep the Slice 1 shape and **add** a top-level `brief` string (saved generation context). Additive — Slice 1 read endpoints ignore it.
- The creation chat is **ephemeral**: only the confirmed outline + `brief` persist.
- Course/lesson ids are slugs matching `^[a-z0-9-]+$`.
- Testable logic takes its dependencies (the subprocess runner, the `generate` callable, `content_dir`, `conn`) as arguments — no hidden globals — matching the Slice 1 style. Unit tests never call real Claude.
- The Pi is **not** a git checkout — deploy by **rsync from Mac** (exclude `.venv/`, `backend/data/`), then `sudo systemctl restart claude-university`. Migrations/index gotcha: see Slice 1 plan.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure

**Backend**
- `backend/claude_client.py` (create) — the Claude boundary: `run_structured`, `stream`, and pure parse helpers `extract_json`, `extract_fenced_json`.
- `backend/generation.py` (create) — pure prompt builders + orchestration: `COURSE_SYSTEM_PROMPT`, `detect_proposal`, `lesson_prompt`, `valid_lesson`, `ensure_lesson`, `chat_sse`.
- `backend/courses.py` (modify) — add `slug_for` and `write_course`.
- `backend/app.py` (modify) — add `POST /api/courses`, `POST /api/courses/chat`, and generate-on-miss in the lesson route; validate route ids.
- `content/courses/` — new courses are written here at runtime.

**Frontend**
- `frontend/src/chat.js` (create) — `streamChat` client + pure `parseSSELines`.
- `frontend/src/views/chat.js` (create) — `chatHTML`.
- `frontend/src/views/home.js` (modify) — escape `title`/`subtitle`.
- `frontend/src/courses.js` (modify) — add `createCourse`.
- `frontend/src/app.js` (modify) — wire the chat screen + JIT loading state.
- `frontend/styles.css` (modify) — chat + loading styles.

**Tests**
- `tests/test_claude_client.py`, `tests/test_generation.py`, `tests/test_courses.py` (extend), `tests/test_courses_api.py` (extend)
- `frontend/tests/chat.test.js`, `frontend/tests/home.test.js` (extend)

---

### Task 0: Spike — prove headless subscription Claude on the Pi (GATE)

**What / Why / Verify:** Before any feature code, confirm a background process on the Pi can run `claude` non-interactively under Werner's Max login and get back (a) a structured JSON result and (b) a streamed result. *Verify:* two commands run over SSH as `werner` return real model output without an interactive login or an API key. **If this fails, STOP and report to Werner — do not start Task 1.**

**Files:** none committed to the app (this is verification; record findings in the report).

- [ ] **Step 1: Confirm the CLI + credentials are present and runnable as the service user**

Run (via `mcp__pi-ssh__exec`):
```
HOME=/home/werner PATH=/home/werner/.local/bin:$PATH claude --version
```
Expected: prints a version (e.g. `2.1.x`). If "command not found", locate it (`ls -l /home/werner/.local/bin/claude`) and use the full path in later steps.

- [ ] **Step 2: Structured (JSON) non-interactive call**

Run:
```
HOME=/home/werner PATH=/home/werner/.local/bin:$PATH \
  claude -p 'Reply with ONLY this JSON and nothing else: {"ok": true}' \
  --output-format json --model claude-sonnet-4-6
```
Expected: a JSON envelope on stdout whose result text contains `{"ok": true}`. **Record the exact top-level shape** (Claude Code prints an object with a `result` string field and metadata). If `--model claude-sonnet-4-6` errors, retry with `--model sonnet` and record which the CLI accepts. If it prompts for login or errors on auth, the OAuth token may be stale → run `claude` once interactively to refresh, then retry; record what was needed.

- [ ] **Step 3: Streaming call**

Run:
```
HOME=/home/werner PATH=/home/werner/.local/bin:$PATH \
  claude -p 'Count from 1 to 5, one number per line.' \
  --output-format stream-json --verbose --model claude-sonnet-4-6
```
Expected: multiple line-delimited JSON events on stdout as the reply is produced. **Record the event shape** — which event types carry assistant text and where the text delta lives (e.g. `type:"assistant"` messages with content blocks). Task 1's stream parser will target exactly this shape.

- [ ] **Step 4: Confirm it works from a non-login, non-interactive shell (as systemd would run it)**

Run:
```
env -i HOME=/home/werner PATH=/home/werner/.local/bin:/usr/bin:/bin \
  claude -p 'Reply with ONLY {"ok": true}' --output-format json --model claude-sonnet-4-6
```
Expected: same as Step 2. This proves it works with a minimal environment (the systemd service has no login shell). Record any extra env var the CLI needed (e.g. it must find `~/.claude`).

- [ ] **Step 5: Record findings and decide the gate**

Write to the report: the working binary path, the exact flags, the model alias accepted, the JSON envelope shape, the stream event shape, and any env requirements. **Decision:** if Steps 2–4 succeeded, the gate is GREEN — proceed to Task 1 using these confirmed details. If any failed and couldn't be resolved, the gate is RED — STOP and report to Werner with the failure detail; do not write feature code.

*(No commit — this task produces knowledge, recorded in the report, that Tasks 1, 5, and 7 consume.)*

---

### Task 1: `claude_client` boundary (structured + streaming)

**What / Why / Verify:** The one place that knows how to call Claude. *Verify:* with a fake subprocess runner, a structured call returns parsed/validated JSON and retries once on bad JSON; the JSON extractors pull objects out of fenced and unfenced text.

**Files:**
- Create: `backend/claude_client.py`
- Test: `tests/test_claude_client.py`

**Interfaces:**
- Produces:
  - `extract_json(text) -> dict | None` — first JSON object in text (fenced ```json or bare `{...}`).
  - `extract_fenced_json(text, label) -> dict | None` — JSON inside a ```<label> fence.
  - `run_structured(prompt, *, model="claude-sonnet-4-6", validate=None, runner=_run_cli) -> dict` — invoke Claude, extract JSON, optionally `validate(obj)->bool`; on missing/invalid JSON retry once with a corrective suffix; raise `ClaudeError` on second failure. `runner(args:list[str]) -> str` returns stdout; injected for tests.
  - `stream(prompt, *, model="claude-sonnet-4-6", spawn=_spawn_cli) -> Iterator[str]` — yields assistant text deltas. `spawn(args) -> Iterable[str]` yields stdout lines; injected for tests.
  - `ClaudeError(Exception)`.

- [ ] **Step 1: Write the failing test** `tests/test_claude_client.py`:

```python
import json
import pytest
from backend import claude_client as cc


def test_extract_json_bare_and_fenced():
    assert cc.extract_json('noise {"a": 1} tail') == {"a": 1}
    assert cc.extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert cc.extract_json("no json here") is None


def test_extract_fenced_json_by_label():
    text = 'intro\n```course\n{"title": "X"}\n```\nouttro'
    assert cc.extract_fenced_json(text, "course") == {"title": "X"}
    assert cc.extract_fenced_json("nothing", "course") is None


def test_run_structured_returns_parsed_json():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": 'Here: {"ok": true}'})
    out = cc.run_structured("make json", runner=runner)
    assert out == {"ok": True}
    assert len(calls) == 1


def test_run_structured_retries_once_then_succeeds():
    outputs = iter([
        json.dumps({"result": "sorry no json"}),
        json.dumps({"result": '{"ok": true}'}),
    ])
    out = cc.run_structured("make json", runner=lambda args: next(outputs))
    assert out == {"ok": True}


def test_run_structured_raises_after_second_failure():
    with pytest.raises(cc.ClaudeError):
        cc.run_structured("x", runner=lambda args: json.dumps({"result": "nope"}))


def test_run_structured_applies_validator():
    good = json.dumps({"result": '{"id": "a"}'})
    with pytest.raises(cc.ClaudeError):
        cc.run_structured("x", runner=lambda args: good, validate=lambda o: "missing" in o)


def test_env_strips_anthropic_credentials(monkeypatch):
    # The Task 0 spike proved a stale ANTHROPIC_API_KEY shadows the Max OAuth and 401s.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-bad")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-bad")
    env = cc._env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_stream_yields_text_deltas():
    # Fake CLI stream-json lines: assistant messages carry text in content blocks.
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hel"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "lo"}]}}),
        json.dumps({"type": "result", "result": "Hello"}),
    ]
    got = list(cc.stream("hi", spawn=lambda args: iter(lines)))
    assert "".join(got) == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_claude_client.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.claude_client`.

- [ ] **Step 3: Write `backend/claude_client.py`**

> Use the exact CLI flags / envelope field / stream event shape **confirmed in Task 0**. The code below is the expected shape (Claude Code prints a `{"result": "..."}` envelope for `--output-format json`, and `--output-format stream-json` emits `assistant` events whose `message.content` holds `text` blocks). Adjust `_run_cli`/`_spawn_cli` and `_extract_stream_text` to match Task 0's findings if they differ.

```python
import json
import os
import subprocess

DEFAULT_MODEL = "claude-sonnet-4-6"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/werner/.local/bin/claude")
_TIMEOUT = 120


class ClaudeError(Exception):
    pass


def _env():
    env = dict(os.environ)
    # CRITICAL (confirmed in the Task 0 spike): a stale ANTHROPIC_API_KEY in the
    # environment makes Claude Code authenticate with that key instead of the Max
    # subscription OAuth — which 401s. Strip both so the subscription login is used.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.setdefault("HOME", "/home/werner")
    env["PATH"] = "/home/werner/.local/bin:" + env.get("PATH", "/usr/bin:/bin")
    return env


def _run_cli(args):
    proc = subprocess.run(
        [CLAUDE_BIN, *args], capture_output=True, text=True, env=_env(), timeout=_TIMEOUT
    )
    if proc.returncode != 0:
        raise ClaudeError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


def _spawn_cli(args):
    proc = subprocess.Popen(
        [CLAUDE_BIN, *args], stdout=subprocess.PIPE, text=True, env=_env()
    )
    for line in proc.stdout:
        yield line


def extract_json(text):
    fenced = extract_fenced_json(text, "json")
    if fenced is not None:
        return fenced
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except ValueError:
                    start = -1
    return None


def extract_fenced_json(text, label):
    fence = "```" + label
    i = text.find(fence)
    if i == -1:
        return None
    body_start = i + len(fence)
    j = text.find("```", body_start)
    if j == -1:
        return None
    try:
        return json.loads(text[body_start:j].strip())
    except ValueError:
        return None


def _result_text(stdout):
    try:
        return json.loads(stdout).get("result", "")
    except ValueError:
        return stdout  # tolerate a raw text result


def run_structured(prompt, *, model=DEFAULT_MODEL, validate=None, runner=_run_cli):
    args_for = lambda p: ["-p", p, "--output-format", "json", "--model", model]
    for attempt in range(2):
        text = _result_text(runner(args_for(prompt)))
        obj = extract_json(text)
        if obj is not None and (validate is None or validate(obj)):
            return obj
        prompt = (
            prompt
            + "\n\nYour previous reply was not valid JSON matching the required shape. "
            "Reply again with ONLY the JSON object, no prose, no code fence."
        )
    raise ClaudeError("structured generation failed after retry")


def _extract_stream_text(line):
    try:
        ev = json.loads(line)
    except ValueError:
        return ""
    if ev.get("type") == "assistant":
        blocks = ev.get("message", {}).get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return ""


def stream(prompt, *, model=DEFAULT_MODEL, spawn=_spawn_cli):
    args = ["-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model]
    for line in spawn(args):
        text = _extract_stream_text(line)
        if text:
            yield text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_claude_client.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/claude_client.py tests/test_claude_client.py
git commit -m "feat(backend): claude_client boundary (structured + streaming via claude -p)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Course slug + manifest writing

**What / Why / Verify:** Turn an approved proposal into stored course files. *Verify:* slugs are URL-safe and de-duplicated; writing a proposal produces a manifest with `brief`, stable module/lesson ids, and an empty `lessons/` dir.

**Files:**
- Modify: `backend/courses.py`
- Test: `tests/test_courses.py` (extend)

**Interfaces:**
- Consumes: `CONTENT_DIR`, `load_manifest` (Slice 1).
- Produces (in `backend/courses.py`):
  - `slug_for(title, existing_ids) -> str` — lowercased `^[a-z0-9-]+$`, de-duped with `-2`, `-3`, …; falls back to `course` if empty.
  - `write_course(content_dir, proposal) -> dict` — `proposal` is `{title, subtitle, brief, modules:[{title, lessons:[{title}]}]}`; assigns `id` (slug, unique vs existing dirs), module ids `m1…`, lesson ids `<slug>-l1, -l2…`; writes `course.json` (with `brief`) and creates `lessons/`; returns the written manifest.

- [ ] **Step 1: Write the failing test** — append to `tests/test_courses.py`:

```python
def test_slug_for_is_url_safe_and_deduped():
    from backend import courses
    assert courses.slug_for("Linear Algebra for ML!", set()) == "linear-algebra-for-ml"
    assert courses.slug_for("Go", {"go"}) == "go-2"
    assert courses.slug_for("Go", {"go", "go-2"}) == "go-3"
    assert courses.slug_for("***", set()) == "course"


def test_write_course_creates_manifest_with_brief_and_ids(tmp_path):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    proposal = {
        "title": "Intro Stats",
        "subtitle": "From scratch",
        "brief": "Beginner, 2h/week, wants intuition first.",
        "modules": [
            {"title": "Basics", "lessons": [{"title": "Mean & median"}, {"title": "Variance"}]},
        ],
    }
    manifest = courses.write_course(root, proposal)
    assert manifest["id"] == "intro-stats"
    assert manifest["brief"] == "Beginner, 2h/week, wants intuition first."
    assert manifest["modules"][0]["id"] == "m1"
    ids = [l["id"] for l in manifest["modules"][0]["lessons"]]
    assert ids == ["intro-stats-l1", "intro-stats-l2"]
    # persisted + lessons dir created
    on_disk = courses.load_manifest(root, "intro-stats")
    assert on_disk["title"] == "Intro Stats"
    assert (root / "intro-stats" / "lessons").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_courses.py -k "slug or write_course" -v`
Expected: FAIL — `AttributeError: module 'backend.courses' has no attribute 'slug_for'`.

- [ ] **Step 3: Add to `backend/courses.py`** (after the imports, alongside the other functions):

```python
import re


def slug_for(title, existing_ids):
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if not base:
        base = "course"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


def write_course(content_dir, proposal):
    content_dir = Path(content_dir)
    existing = {p.name for p in content_dir.iterdir()} if content_dir.exists() else set()
    course_id = slug_for(proposal["title"], existing)

    modules = []
    counter = 1
    for m_idx, module in enumerate(proposal.get("modules", []), start=1):
        lessons = []
        for lesson in module.get("lessons", []):
            lessons.append({"id": f"{course_id}-l{counter}", "title": lesson["title"]})
            counter += 1
        modules.append({"id": f"m{m_idx}", "title": module["title"], "lessons": lessons})

    manifest = {
        "id": course_id,
        "title": proposal["title"],
        "subtitle": proposal.get("subtitle", ""),
        "brief": proposal.get("brief", ""),
        "modules": modules,
    }
    course_dir = content_dir / course_id
    (course_dir / "lessons").mkdir(parents=True, exist_ok=True)
    (course_dir / "course.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_courses.py -v`
Expected: PASS (all Slice 1 course tests + the 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/courses.py tests/test_courses.py
git commit -m "feat(backend): course slug + manifest writing with saved brief

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Generation helpers — proposal detection, lesson prompt, validation

**What / Why / Verify:** The pure pieces that shape Claude's prompts and read its output. *Verify:* a proposal fence is detected and parsed; a lesson object is validated against the required schema; the lesson prompt includes the course brief, profile, and lesson context.

**Files:**
- Create: `backend/generation.py`
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `claude_client.extract_fenced_json` (Task 1).
- Produces (in `backend/generation.py`):
  - `COURSE_SYSTEM_PROMPT: str`.
  - `detect_proposal(text) -> dict | None` — parses a ```course fenced block.
  - `LESSON_KEYS: tuple` and `valid_lesson(obj) -> bool`.
  - `lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total) -> str`.

- [ ] **Step 1: Write the failing test** `tests/test_generation.py`:

```python
from backend import generation as gen


def test_detect_proposal_parses_course_fence():
    text = 'Sounds good!\n```course\n{"title": "Stats", "modules": []}\n```'
    p = gen.detect_proposal(text)
    assert p["title"] == "Stats"
    assert gen.detect_proposal("just chatting, no proposal yet") is None


def test_valid_lesson_requires_all_keys():
    good = {k: "x" for k in gen.LESSON_KEYS}
    assert gen.valid_lesson(good) is True
    missing = dict(good)
    del missing["promptHtml"]
    assert gen.valid_lesson(missing) is False
    assert gen.valid_lesson("not a dict") is False


def test_lesson_prompt_includes_context():
    prompt = gen.lesson_prompt(
        brief="Beginner, wants intuition.",
        profile={"analogies": True},
        lesson_id="stats-l1",
        lesson_title="Mean & median",
        module_title="Basics",
        position=1,
        total=8,
    )
    assert "Beginner, wants intuition." in prompt
    assert "Mean & median" in prompt
    assert "Basics" in prompt
    assert "stats-l1" in prompt
    assert "promptHtml" in prompt  # tells the model the required shape
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.generation`.

- [ ] **Step 3: Write `backend/generation.py`** (the orchestration functions `ensure_lesson`/`chat_sse` are added in Tasks 5 and 7; this task is the pure helpers):

```python
import json

from backend import claude_client

COURSE_SYSTEM_PROMPT = (
    "You are a curriculum designer building a personalized course for a single learner "
    "on their personal learning platform. Have a short, friendly conversation to understand "
    "their goal, prior knowledge, desired depth, and how intensively they want to study. "
    "Ask one or two focused questions per turn. When you have enough to propose a curriculum, "
    "reply with a brief sentence and then a fenced code block labelled `course` containing ONLY "
    "JSON of this shape:\n"
    "```course\n"
    '{"title": "...", "subtitle": "...", "brief": "<one paragraph capturing audience level, '
    'depth, pace, and goals for later lesson generation>", '
    '"modules": [{"title": "...", "lessons": [{"title": "..."}]}]}\n'
    "```\n"
    "Keep the course focused: 3-6 modules, 3-6 lessons each. Do not emit the course block until "
    "you have enough information."
)

LESSON_KEYS = (
    "id", "courseId", "topic", "step", "totalSteps",
    "eyebrow", "promptHtml", "hintHtml", "solutionAns", "solutionNote",
)


def detect_proposal(text):
    return claude_client.extract_fenced_json(text, "course")


def valid_lesson(obj):
    return isinstance(obj, dict) and all(k in obj for k in LESSON_KEYS)


def lesson_prompt(*, brief, profile, lesson_id, lesson_title, module_title, position, total):
    return (
        "You are writing one self-contained lesson for a personalized course.\n"
        f"Course context: {brief}\n"
        f"Learner preferences (JSON): {json.dumps(profile or {})}\n"
        f"This is lesson {position} of {total}. Module: {module_title}. "
        f"Lesson title: {lesson_title}.\n\n"
        "Write a single exercise-style lesson. Reply with ONLY a JSON object (no prose, no fence) "
        "with exactly these keys:\n"
        f'  id: "{lesson_id}"\n'
        "  courseId, topic (short), step (integer 1), totalSteps (integer 1), "
        'eyebrow ("EXERCISE"), promptHtml (the question as HTML, may use <code>), '
        "hintHtml (a hint as HTML), solutionAns (the answer), solutionNote (one-sentence why).\n"
        "Shape every learner-facing field to the learner preferences above."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "feat(backend): generation helpers (proposal detection, lesson prompt, validation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `POST /api/courses` create endpoint

**What / Why / Verify:** Persist an approved proposal as a course. *Verify:* posting a proposal writes the course and it then appears via `GET /api/courses`; a bad body is rejected.

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_courses_api.py` (extend)

**Interfaces:**
- Consumes: `courses.write_course` (Task 2), `courses.CONTENT_DIR`.
- Produces: `POST /api/courses` — body `{title, subtitle?, brief?, modules:[...]}` → writes the course, returns `{ "course": <manifest> }` with 201; missing `title`/`modules` → 400.

- [ ] **Step 1: Write the failing test** — append to `tests/test_courses_api.py`:

```python
def test_post_course_creates_and_lists(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)

    resp = client.post("/api/courses", json={
        "title": "Test Course",
        "subtitle": "sub",
        "brief": "ctx",
        "modules": [{"title": "M1", "lessons": [{"title": "L1"}]}],
    })
    assert resp.status_code == 201
    created = resp.get_json()["course"]
    assert created["id"] == "test-course"

    listed = client.get("/api/courses").get_json()["courses"]
    assert any(c["id"] == "test-course" for c in listed)


def test_post_course_rejects_missing_fields(client, tmp_path, monkeypatch):
    from backend import courses
    monkeypatch.setattr(courses, "CONTENT_DIR", tmp_path / "courses")
    assert client.post("/api/courses", json={"title": "x"}).status_code == 400
    assert client.post("/api/courses", json={"modules": []}).status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_courses_api.py -k post_course -v`
Expected: FAIL — `POST /api/courses` returns 405 (no such route).

- [ ] **Step 3: Add the route to `backend/app.py`** (after the `get_courses` route):

```python
    @app.post("/api/courses")
    def post_course():
        body = request.get_json(silent=True) or {}
        if not body.get("title") or not body.get("modules"):
            return jsonify({"error": "title and modules are required"}), 400
        manifest = courses.write_course(courses.CONTENT_DIR, body)
        return jsonify({"course": manifest}), 201
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_courses_api.py -v`
Expected: PASS (Slice 1 API tests + the 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "feat(backend): POST /api/courses create endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Chat SSE relay + `POST /api/courses/chat`

**What / Why / Verify:** Stream Claude's chat reply to the browser and surface a curriculum proposal. *Verify:* with a fake stream, the relay emits SSE `delta` events for text and a final `proposal` event when a course fence appears, then `done`.

**Files:**
- Modify: `backend/generation.py` (add `chat_sse`)
- Modify: `backend/app.py` (add the route)
- Test: `tests/test_generation.py` (extend)

**Interfaces:**
- Consumes: `claude_client.stream` (Task 1), `detect_proposal` (Task 3), `COURSE_SYSTEM_PROMPT`.
- Produces:
  - `generation.build_chat_prompt(messages, profile) -> str` — system prompt + profile + the running transcript.
  - `generation.chat_sse(messages, profile, *, stream_fn) -> Iterator[str]` — yields SSE strings: `event: delta` per text chunk, then either `event: proposal` (if a course fence is in the full text) or none, then `event: done`. `stream_fn(prompt) -> Iterable[str]` is injected.
  - `POST /api/courses/chat` — body `{messages:[{role,content}]}` → `text/event-stream` from `chat_sse` wired to `claude_client.stream`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_generation.py`:

```python
def _events(sse_chunks):
    # parse "event: X\ndata: Y\n\n" chunks into (event, data) tuples
    out = []
    for chunk in sse_chunks:
        ev = data = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if ev:
            out.append((ev, data))
    return out


def test_chat_sse_streams_deltas_then_done():
    def fake_stream(prompt):
        yield "Hi! "
        yield "What do you want to learn?"
    chunks = list(gen.chat_sse([{"role": "user", "content": "hello"}], {}, stream_fn=fake_stream))
    evs = _events(chunks)
    assert ("delta", "Hi! ") in evs
    assert evs[-1][0] == "done"


def test_chat_sse_emits_proposal_when_course_fence_present():
    def fake_stream(prompt):
        yield "Great, here is a plan.\n```course\n"
        yield '{"title": "Stats", "modules": []}\n```'
    chunks = list(gen.chat_sse([{"role": "user", "content": "stats"}], {}, stream_fn=fake_stream))
    evs = _events(chunks)
    proposal = [d for (e, d) in evs if e == "proposal"]
    assert proposal and '"title": "Stats"' in proposal[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k chat_sse -v`
Expected: FAIL — `AttributeError: ... has no attribute 'chat_sse'`.

- [ ] **Step 3: Add to `backend/generation.py`:**

```python
def build_chat_prompt(messages, profile):
    lines = [COURSE_SYSTEM_PROMPT, "", f"Learner preferences (JSON): {json.dumps(profile or {})}", ""]
    for m in messages:
        who = "Learner" if m.get("role") == "user" else "You"
        lines.append(f"{who}: {m.get('content', '')}")
    lines.append("You:")
    return "\n".join(lines)


def _sse(event, data):
    return f"event: {event}\ndata: {data}\n\n"


def chat_sse(messages, profile, *, stream_fn):
    prompt = build_chat_prompt(messages, profile)
    full = []
    for chunk in stream_fn(prompt):
        full.append(chunk)
        yield _sse("delta", chunk)
    proposal = detect_proposal("".join(full))
    if proposal is not None:
        yield _sse("proposal", json.dumps(proposal))
    yield _sse("done", "{}")
```

- [ ] **Step 4: Add the route to `backend/app.py`** — add the import and route:

Change the import line:
```python
from backend import db, events, profile, queries, courses, claude_client, generation
```

Add the route (after `post_course`):
```python
    @app.post("/api/courses/chat")
    def post_course_chat():
        body = request.get_json(silent=True) or {}
        messages = body.get("messages", [])
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data") if isinstance(prof, dict) else None
        stream_fn = lambda prompt: claude_client.stream(prompt)
        sse = generation.chat_sse(messages, prof_data, stream_fn=stream_fn)
        return app.response_class(sse, mimetype="text/event-stream")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: PASS (Task 3 tests + the 2 new).
Run: `.venv/bin/pytest -q` (whole backend suite) — PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/generation.py backend/app.py tests/test_generation.py
git commit -m "feat(backend): chat SSE relay and /api/courses/chat endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: JIT lesson generation in the lesson endpoint

**What / Why / Verify:** Generate a lesson the first time it's opened, then cache it. *Verify:* a missing lesson is generated (fake client), validated, written, and served; a present lesson is served without generating; invalid generation writes nothing and surfaces an error.

**Files:**
- Modify: `backend/generation.py` (add `ensure_lesson`)
- Modify: `backend/app.py` (generate-on-miss in the lesson route)
- Test: `tests/test_generation.py` (extend)

**Interfaces:**
- Consumes: `courses.load_manifest`, `courses.load_lesson`, `courses.flatten_lessons` (Slice 1); `valid_lesson`, `lesson_prompt` (Task 3).
- Produces: `generation.ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate) -> dict | None` — returns the existing lesson if present; else builds the prompt from the manifest's `brief`/lesson context, calls `generate(prompt) -> dict`, validates, writes `content/courses/<id>/lessons/<lessonId>.json`, and returns it; returns `None` if the course/lesson id isn't in the manifest; raises `claude_client.ClaudeError` if generation is invalid. `generate` is injected.

- [ ] **Step 1: Write the failing test** — append to `tests/test_generation.py`:

```python
import json as _json
import pytest
from backend import claude_client


def _course(tmp_path):
    from backend import courses
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(_json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "beginner friendly",
        "modules": [{"id": "m1", "title": "Basics",
                     "lessons": [{"id": "demo-l1", "title": "First"}]}],
    }))
    return root


def test_ensure_lesson_generates_validates_and_caches(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return made
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=generate)
    assert out["id"] == "demo-l1"
    assert "beginner friendly" in calls[0]  # brief fed into the prompt
    # cached: file now exists and a second call does not regenerate
    assert (root / "demo" / "lessons" / "demo-l1.json").exists()
    out2 = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: (_ for _ in ()).throw(AssertionError("regenerated")))
    assert out2["id"] == "demo-l1"


def test_ensure_lesson_unknown_id_returns_none(tmp_path):
    root = _course(tmp_path)
    assert gen.ensure_lesson(root, "demo", "demo-l9", {}, generate=lambda p: {}) is None


def test_ensure_lesson_invalid_generation_raises_and_writes_nothing(tmp_path):
    root = _course(tmp_path)
    with pytest.raises(claude_client.ClaudeError):
        gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: {"bad": 1})
    assert not (root / "demo" / "lessons" / "demo-l1.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k ensure_lesson -v`
Expected: FAIL — `AttributeError: ... has no attribute 'ensure_lesson'`.

- [ ] **Step 3: Add to `backend/generation.py`** (add `from pathlib import Path` and `from backend import courses` at the top):

```python
def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return None
    flat = courses.flatten_lessons(manifest)
    meta = next((l for l in flat if l["id"] == lesson_id), None)
    if meta is None:
        return None
    position = [l["id"] for l in flat].index(lesson_id) + 1
    prompt = lesson_prompt(
        brief=manifest.get("brief", ""),
        profile=profile,
        lesson_id=lesson_id,
        lesson_title=meta["title"],
        module_title=meta["moduleTitle"],
        position=position,
        total=len(flat),
    )
    lesson = generate(prompt)
    if not valid_lesson(lesson):
        raise claude_client.ClaudeError("generated lesson failed validation")
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    path.write_text(json.dumps(lesson, indent=2, ensure_ascii=False))
    return lesson
```

- [ ] **Step 4: Wire generate-on-miss into `backend/app.py`** — replace the `get_lesson` route body:

```python
    @app.get("/api/courses/<course_id>/lessons/<lesson_id>")
    def get_lesson(course_id, lesson_id):
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is not None:
            return jsonify(lesson)
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data") if isinstance(prof, dict) else None
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_lesson)
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data, generate=generate
            )
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_generation.py -v` → PASS.
Run: `.venv/bin/pytest -q` (whole backend suite) → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/generation.py backend/app.py tests/test_generation.py
git commit -m "feat(backend): just-in-time lesson generation on first open

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Chat frontend + JIT loading state + create wiring

**What / Why / Verify:** The "Add a course" chat screen, rendering streamed replies and the proposal card, and a loading state while a lesson generates. *Verify (unit):* the pure SSE-line parser splits framed events correctly and all frontend unit tests pass. *Verify (real app):* deferred to Task 9.

**Files:**
- Create: `frontend/src/chat.js`
- Create: `frontend/src/views/chat.js`
- Modify: `frontend/src/courses.js` (add `createCourse`)
- Modify: `frontend/src/app.js` (chat screen + JIT loading)
- Modify: `frontend/styles.css`
- Test: `frontend/tests/chat.test.js`

**Interfaces:**
- Produces:
  - `frontend/src/chat.js`: `parseSSELines(buffer) -> { events: [{event, data}], rest: string }` (pure; splits on blank lines, keeps a trailing partial in `rest`); `streamChat({ fetch, messages, onDelta, onProposal, onDone })` (POSTs to `/api/courses/chat`, reads the response stream, drives callbacks).
  - `frontend/src/views/chat.js`: `chatHTML(messages, { pending }) -> string`.
  - `frontend/src/courses.js`: `createCourse({ fetch, proposal }) -> Promise<object>` (POSTs `/api/courses`, returns the created course).

- [ ] **Step 1: Write the failing test** `frontend/tests/chat.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSSELines } from "../src/chat.js";

test("parseSSELines extracts complete events and keeps the partial tail", () => {
  const buffer =
    "event: delta\ndata: Hi\n\n" +
    "event: proposal\ndata: {\"title\":\"X\"}\n\n" +
    "event: done\ndata: {}";  // no trailing blank line yet
  const { events, rest } = parseSSELines(buffer);
  assert.deepEqual(events[0], { event: "delta", data: "Hi" });
  assert.deepEqual(events[1], { event: "proposal", data: '{"title":"X"}' });
  assert.equal(events.length, 2);          // "done" is incomplete
  assert.match(rest, /event: done/);       // retained for the next chunk
});

test("parseSSELines returns no events for an empty buffer", () => {
  assert.deepEqual(parseSSELines(""), { events: [], rest: "" });
});

test("parseSSELines joins multiple data lines in one frame (multi-line delta)", () => {
  const { events } = parseSSELines("event: delta\ndata: Line one.\ndata: Line two.\n\n");
  assert.deepEqual(events[0], { event: "delta", data: "Line one.\nLine two." });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/chat.test.js`
Expected: FAIL — cannot find `../src/chat.js`.

- [ ] **Step 3: Write `frontend/src/chat.js`:**

```javascript
export function parseSSELines(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop(); // last item is an incomplete frame (or "")
  for (const frame of parts) {
    let event = null;
    const dataLines = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      // Per the SSE spec, a frame may carry multiple data: lines (the backend
      // emits one per newline of a multi-line chat delta). Join them with "\n"
      // and strip only the single framing space after "data:" — not all
      // whitespace — so payload whitespace and newlines survive intact.
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (event) events.push({ event, data: dataLines.join("\n") });
  }
  return { events, rest };
}

export async function streamChat({ fetch, messages, onDelta, onProposal, onDone }) {
  const resp = await fetch("/api/courses/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSSELines(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "delta") onDelta(data);
      else if (event === "proposal") onProposal(JSON.parse(data));
      else if (event === "done") onDone();
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/chat.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Write `frontend/src/views/chat.js`:**

```javascript
function bubble(m) {
  const who = m.role === "user" ? "me" : "claude";
  return `<div class="msg ${who}">${m.html || m.content}</div>`;
}

export function chatHTML(messages, { pending = false } = {}) {
  const thread = messages.map(bubble).join("");
  const dots = pending ? `<div class="msg claude pending">…</div>` : "";
  return `
    <div class="chat-col">
      <div class="greeting"><h1>Add a course</h1><span>Tell Claude what you want to learn</span></div>
      <div class="chat-thread">${thread}${dots}</div>
      <div class="chat-input">
        <textarea data-field="chat" placeholder="e.g. intermediate linear algebra for ML, ~3h/week"></textarea>
        <button class="btn-primary" data-action="send">Send</button>
      </div>
    </div>
  `;
}
```

- [ ] **Step 6: Add `createCourse` to `frontend/src/courses.js`:**

```javascript
export async function createCourse({ fetch, proposal }) {
  const resp = await fetch("/api/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(proposal),
  });
  if (!resp.ok) return null;
  const body = await resp.json();
  return body.course;
}
```

- [ ] **Step 7: Wire the chat screen into `frontend/src/app.js`** — update the imports and the `add-course` handler, and add a chat screen + a JIT loading state.

Update imports:
```javascript
import { listCourses, loadCourse, loadLesson, createCourse } from "./courses.js";
import { chatHTML } from "./views/chat.js";
import { streamChat } from "./chat.js";
```

Replace the `add-course` click handler in `showHome` with:
```javascript
    view.querySelector('[data-action="add-course"]').addEventListener("click", () => {
      log("add_course_clicked");
      showChat();
    });
```

Add these functions (near the other screens):
```javascript
  // ---- course creation chat ----
  function showChat() {
    ui.screen = "chat";
    ui.chat = { messages: [], proposal: null, pending: false };
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintChat();
  }

  function paintChat() {
    const view = root.querySelector("#view");
    view.innerHTML = chatHTML(ui.chat.messages, { pending: ui.chat.pending });
    if (ui.chat.proposal) {
      const card = doc.createElement("div");
      card.className = "card proposal";
      card.innerHTML =
        `<div class="eyebrow">PROPOSED COURSE</div>` +
        `<h2 class="session-topic">${escapeHtml(ui.chat.proposal.title)}</h2>` +
        `<div class="session-sub">${escapeHtml(ui.chat.proposal.subtitle || "")}</div>` +
        `<button class="btn-primary" data-action="create-course">Create this course</button>`;
      view.querySelector(".chat-thread").appendChild(card);
      card.querySelector('[data-action="create-course"]').addEventListener("click", createFromProposal);
    }
    const send = view.querySelector('[data-action="send"]');
    if (send) send.addEventListener("click", sendChat);
  }

  async function sendChat() {
    const ta = root.querySelector('[data-field="chat"]');
    const text = ta.value.trim();
    if (!text || ui.chat.pending) return;
    ui.chat.messages.push({ role: "user", content: escapeHtml(text) });
    ui.chat.messages.push({ role: "assistant", content: "", html: "" });
    ui.chat.pending = true;
    paintChat();
    const reply = ui.chat.messages[ui.chat.messages.length - 1];
    await streamChat({
      fetch,
      messages: ui.chat.messages
        .filter((m) => m.content !== "" || m !== reply)
        .map((m) => ({ role: m.role, content: m.content })),
      onDelta: (d) => { reply.html += escapeHtml(d); paintChat(); },
      onProposal: (p) => { ui.chat.proposal = p; },
      onDone: () => { ui.chat.pending = false; paintChat(); },
    });
  }

  async function createFromProposal() {
    const course = await createCourse({ fetch, proposal: ui.chat.proposal });
    if (course) { log("course_created", { courseId: course.id }); openCourse(course.id); }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
```

Add a JIT loading state to `startLesson` (so the few-second wait shows feedback):
```javascript
  async function startLesson() {
    const next = ui.summary && ui.summary.nextLesson;
    if (!next) return;
    const view = root.querySelector("#view");
    if (view) view.innerHTML = `<div class="card lesson loading">Preparing your lesson…</div>`;
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: next.id });
    if (!ui.lesson) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
    log("lesson_view", { courseId: ui.courseId, topicId: next.id });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

Add `chat: null` to the `ui` object initializer.

- [ ] **Step 8: Add chat + loading styles** — append to `frontend/styles.css`:

```css
/* =================  COURSE-CREATION CHAT  ================= */
.chat-col{display:flex; flex-direction:column; gap:14px}
.chat-thread{display:flex; flex-direction:column; gap:10px}
.msg{max-width:85%; padding:11px 14px; border-radius:var(--r-lg); font-size:14px; line-height:1.5}
.msg.me{align-self:flex-end; background:var(--grad); color:#fff}
.msg.claude{align-self:flex-start; background:var(--glass-card-2); border:1px solid var(--border-glass); color:var(--text)}
.msg.pending{color:var(--text-mut)}
.chat-input{display:flex; gap:8px; align-items:flex-end}
.chat-input textarea{flex:1; min-height:48px}
.card.proposal{margin-top:6px}
.card.lesson.loading{display:flex; align-items:center; justify-content:center; min-height:200px; color:var(--text-mut)}
```

- [ ] **Step 9: Run the full frontend suite**

Run: `cd frontend && node --test`
Expected: PASS (all suites incl. the new `chat.test.js`).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/chat.js frontend/src/views/chat.js frontend/src/courses.js frontend/src/app.js frontend/styles.css frontend/tests/chat.test.js
git commit -m "feat(frontend): course-creation chat, proposal card, JIT loading state

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Hardening — escape generated titles, validate route ids

**What / Why / Verify:** Generated text and slugs now flow into HTML and filesystem paths. *Verify:* `home.js` escapes a title containing `<`; the course/lesson routes 404 on ids with illegal characters.

**Files:**
- Modify: `frontend/src/views/home.js`
- Modify: `backend/app.py`
- Test: `frontend/tests/home.test.js` (extend), `tests/test_courses_api.py` (extend)

**Interfaces:**
- Produces: `home.js` HTML-escapes `title`/`subtitle`; `get_course`/`get_lesson`/JIT path reject ids not matching `^[a-z0-9-]+$` with 404.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/home.test.js`:
```javascript
test("home escapes HTML in course title and subtitle", () => {
  const html = homeHTML([{
    id: "x", title: "<script>alert(1)</script>", subtitle: "a & b",
    progress: { done: 0, total: 1, pct: 0 }, nextLesson: null, reviewsDue: 0,
  }]);
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /a &amp; b/);
});
```

Append to `tests/test_courses_api.py`:
```python
def test_routes_reject_illegal_ids(client):
    assert client.get("/api/courses/Bad_Id").status_code == 404
    assert client.get("/api/courses/machine-learning/lessons/..%2fsecret").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && node --test tests/home.test.js` → FAIL (raw `<script>` present).
Run: `.venv/bin/pytest tests/test_courses_api.py -k illegal -v` → FAIL (returns 200/other, not 404).

- [ ] **Step 3: Escape in `frontend/src/views/home.js`** — add an `esc` helper and use it in `courseCard`:

```javascript
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function courseCard(c) {
  return `
    <button class="course-card" data-course="${c.id}">
      <div class="course-title">${esc(c.title)}</div>
      <div class="course-sub">${esc(c.subtitle)}</div>
      <div class="bar"><i style="width:${c.progress.pct}%"></i></div>
      <div class="course-meta">${c.progress.done} of ${c.progress.total} lessons · ${c.reviewsDue} reviews due</div>
      <span class="course-continue">Continue →</span>
    </button>`;
}
```
(`c.id` is a server-generated slug matching `^[a-z0-9-]+$`, so it's safe as an attribute value.)

- [ ] **Step 4: Validate ids in `backend/app.py`** — add a helper near the top of `create_app` and guard the three course/lesson routes:

```python
    import re as _re
    _ID_RE = _re.compile(r"^[a-z0-9-]+$")
```

In `get_course`, `get_lesson`, and `post`-less GET paths, return 404 when an id is illegal — add at the start of `get_course`:
```python
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
```
and at the start of `get_lesson`:
```python
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && node --test` → PASS (all suites).
Run: `.venv/bin/pytest -q` → PASS (all backend).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/home.js backend/app.py frontend/tests/home.test.js tests/test_courses_api.py
git commit -m "feat(security): escape generated titles and validate course/lesson ids

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification on the Pi + deploy

**What / Why / Verify:** Prove the whole feature works against real Claude on the Pi, then ship it. *Verify:* on the Pi, a chat creates a course, opening a lesson generates real content, and the new course persists.

**Files:** none changed (verification + deploy).

- [ ] **Step 1: Full local test sweep**

Run: `.venv/bin/pytest -q` → PASS (all backend, incl. claude_client/generation/courses_api).
Run: `cd frontend && node --test` → PASS (all frontend).

- [ ] **Step 2: Deploy to the Pi** (rsync — the Pi is not a git checkout):

```bash
cd "$(git rev-parse --show-toplevel)"
rsync -az --exclude '.git/' --exclude '.venv/' --exclude 'backend/data/' \
  --exclude '.DS_Store' --exclude '.remember/' --exclude '.superpowers/' \
  --exclude '.playwright-mcp/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  ./ werner@192.168.2.69:/home/werner/claude_university/
```
Then: `mcp__pi-ssh__sudo-exec: systemctl restart claude-university` and confirm `systemctl is-active claude-university` → `active`.

- [ ] **Step 3: Real-Claude smoke test on the Pi (API level)**

```
mcp__pi-ssh__exec: curl -s -X POST http://localhost:8200/api/courses/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"I want a tiny 1-module course on the Python print function, just 2 lessons, beginner."}]}' --max-time 120
```
Expected: an SSE stream with `event: delta` chunks and (if Claude proposes) an `event: proposal` near the end. This confirms real subscription-auth streaming works in the service.

- [ ] **Step 4: Real-browser end-to-end (Playwright, against the Pi URL `http://100.99.33.106:8200/`)**

1. Open the Pi URL; complete the diagnostic if shown → home.
2. Click "Add a course"; send a short request ("a 1-module, 2-lesson beginner course on the Python print function"); watch the reply stream; when the proposal card appears, click "Create this course".
3. Confirm you land on the new course screen and it appears on the home grid.
4. Click "Start session" → the "Preparing your lesson…" state shows, then a generated lesson renders (real content matching the lesson screen).
5. Read it back: `curl -s http://100.99.33.106:8200/api/courses` shows the new course; `curl -s http://100.99.33.106:8200/api/courses/<id>` shows its manifest with a `brief`; the generated lesson file now exists under `content/courses/<id>/lessons/`.

- [ ] **Step 5: Confirm the service survived and is enabled**

`mcp__pi-ssh__exec: systemctl is-active claude-university && systemctl is-enabled claude-university` → `active` + `enabled`.

---

## Self-Review

**1. Spec coverage:**
- `claude_client` boundary (structured + streaming, subscription auth) → Tasks 0, 1. ✓
- Conversational chat, streamed, proposal-on-ready, confirm-to-create → Tasks 5 (relay), 7 (UI), 4 (create). ✓
- Curriculum proposal contract (```course fence) + saved `brief` → Tasks 3 (detect), 2 (write_course). ✓
- JIT lesson generation conforming to the existing lesson schema, cached on write → Task 6. ✓
- Personalization (profile fed to chat + lesson prompts) → Tasks 3, 5, 6. ✓
- Hardening (escape titles, validate ids) → Task 8. ✓
- Spike-first gate on headless subscription auth → Task 0. ✓
- Default model Sonnet 4.6, configurable → Global Constraints + `claude_client.DEFAULT_MODEL`. ✓
- *Correctly deferred:* look-ahead, outline editing, regeneration, FSRS, streaming the structured artifacts, multi-user.

**2. Placeholder scan:** No "TBD/TODO". Task 0 is a verification procedure (its deliverable is the confirmed invocation that Tasks 1/5/7 reference) — not a placeholder. Task 1's CLI code is the expected shape with an explicit "match Task 0's findings" instruction, which is the correct way to express a spike-gated dependency.

**3. Type consistency:** `claude_client.run_structured(prompt, *, model, validate, runner)` and `.stream(prompt, *, model, spawn)` are used with those exact kwargs in Tasks 5 (`stream`) and 6 (`run_structured(..., validate=generation.valid_lesson)`). `generation.ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate)` and `chat_sse(messages, profile, *, stream_fn)` match their call sites in `app.py`. `courses.write_course(content_dir, proposal)` returns the manifest consumed by the create route and `createCourse`. The proposal shape `{title, subtitle, brief, modules:[{title, lessons:[{title}]}]}` is consistent across `COURSE_SYSTEM_PROMPT` (Task 3), `write_course` (Task 2), the create route (Task 4), and the frontend create flow (Task 7). `LESSON_KEYS` (Task 3) is the single source for `valid_lesson` (Task 6) and the lesson-prompt shape. The frontend `parseSSELines`/`streamChat` (Task 7) consume the exact `event: delta|proposal|done` frames produced by `chat_sse` (Task 5). ✓
