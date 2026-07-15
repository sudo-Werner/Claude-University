# Hardening Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the robustness and correctness defects found in the 2026-07-15 codebase audit — no new features, no behavior changes beyond removing failure modes.

**Architecture:** Small, mechanical fixes across the existing Flask backend (`backend/`) and plain-ES-module frontend (`frontend/src/`). Backend: a stream watchdog + process cleanup in the Claude CLI client, atomic content writes via a new 10-line `fsutil` helper, corrupt-cache self-heal in the course loaders, a per-key single-flight lock on expensive generation, and a per-module lesson-count check in the compiler. Frontend: escaping for the two manifest-title render sites that miss it, navigation guards after awaits, a bootstrap error boundary, and disabled/handled dead-end buttons.

**Tech Stack:** Python 3 / Flask / pytest; plain ES modules / `node --test`.

## Global Constraints

- Backend tests: `.venv/bin/pytest` (run from repo root `/Users/wernervanellewee/Projects/Claude_Education`).
- Frontend tests: `node --test frontend/tests/*.test.js` — ALWAYS the glob, NEVER the bare directory.
- All learner/model-visible text interpolated into HTML client-side goes through `esc()` from `frontend/src/escape.js` — EXCEPT fields the server already sanitizes/escapes (lesson `promptHtml`/`hintHtml`/`solutionAns`/`solutionNote`/`topic`/`eyebrow`, check `prompt`/`explanation`/`choices`, grade `note`, capstone fields, library/lesson source `title`/`note`). Do NOT add client-side `esc()` to those — it would double-escape.
- No emojis anywhere in code, copy, or commit messages.
- Never touch `content/` (course data) or `backend/data/` in code or tests; tests use `tmp_path`.
- Commit after each task with the message given in the task. Do NOT push, do NOT merge.
- Keep every fix minimal — no refactors beyond what the task states (YAGNI).

## File Structure

- Create: `backend/fsutil.py` (atomic write helper), `tests/test_fsutil.py`.
- Modify: `backend/claude_client.py`, `backend/generation.py`, `backend/courses.py`, `backend/notes.py`, `backend/compiler.py`, `frontend/src/views/dashboard.js`, `frontend/src/views/shell.js`, `frontend/src/views/chat.js`, `frontend/src/views/syllabus.js`, `frontend/src/app.js`, `frontend/src/profile.js`.
- Tests extended: `tests/test_claude_client.py`, `tests/test_generation.py`, `tests/test_courses.py`, `tests/test_courses_api.py`, `tests/test_compiler.py`, `frontend/tests/views.test.js`, `frontend/tests/chat.test.js`, `frontend/tests/profile.test.js`.

---

### Task 1: Stream watchdog timeout + process cleanup in `claude_client._spawn_cli`

The streaming CLI path (`_spawn_cli`) — used by every lesson generation, compile, revise, and chat — has NO timeout (`proc.wait()` can block forever) and leaks the CLI process if the consumer abandons the generator (e.g. browser disconnects mid-SSE). The non-streaming path already has `timeout=240`.

**Files:**
- Modify: `backend/claude_client.py` (function `_spawn_cli`, lines 69-84; add `import threading` and a `_STREAM_TIMEOUT` constant near `_TIMEOUT` at line 11)
- Test: `tests/test_claude_client.py`

**Interfaces:**
- Produces: `_spawn_cli(args)` — same generator contract as today (yields stdout lines, raises `ClaudeError`/`ClaudeAuthError` on failure). New behavior: raises `ClaudeError` containing `"timed out"` if the process outlives `_STREAM_TIMEOUT` seconds; always kills the child process when the generator exits for any reason. New module constant `_STREAM_TIMEOUT = int(os.environ.get("CLAUDE_STREAM_TIMEOUT", "540"))` (540s: just under waitress's `--channel-timeout=600`, and well above the ~110s a rich lesson takes).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_claude_client.py` (it already imports `claude_client` and `pytest`; add `import os`, `import time` at the top if missing):

```python
def test_spawn_cli_times_out_and_kills(monkeypatch, tmp_path):
    script = tmp_path / "fake-claude"
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    monkeypatch.setattr(claude_client, "CLAUDE_BIN", str(script))
    monkeypatch.setattr(claude_client, "_STREAM_TIMEOUT", 1)
    start = time.monotonic()
    with pytest.raises(claude_client.ClaudeError, match="timed out"):
        list(claude_client._spawn_cli(["-p", "x"]))
    assert time.monotonic() - start < 10  # killed, not waited out


def test_spawn_cli_kills_process_when_generator_abandoned(monkeypatch, tmp_path):
    pidfile = tmp_path / "pid"
    script = tmp_path / "fake-claude"
    script.write_text(f"#!/bin/sh\necho $$ > {pidfile}\necho line1\nsleep 30\n")
    script.chmod(0o755)
    monkeypatch.setattr(claude_client, "CLAUDE_BIN", str(script))
    gen = claude_client._spawn_cli(["-p", "x"])
    assert next(gen) == "line1\n"
    gen.close()  # simulates the SSE consumer disconnecting
    pid = int(pidfile.read_text().strip())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("CLI process still alive after generator close")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_claude_client.py -k "spawn_cli" -v`
Expected: `test_spawn_cli_times_out_and_kills` FAILS (hangs ~30s then exits nonzero without "timed out", or the sleep is not killed); `test_spawn_cli_kills_process_when_generator_abandoned` FAILS (process still alive).

- [ ] **Step 3: Implement**

In `backend/claude_client.py`, add `import threading` to the imports, add below `_TIMEOUT`:

```python
# The streaming path (lessons, compile, revise, chats) needs its own, longer ceiling:
# a rich lesson takes ~110s and a compile outline longer. 540s sits just under the
# waitress --channel-timeout=600, so the process dies before the HTTP channel does.
_STREAM_TIMEOUT = int(os.environ.get("CLAUDE_STREAM_TIMEOUT", "540"))
```

Replace `_spawn_cli` entirely with:

```python
def _spawn_cli(args):
    with tempfile.TemporaryFile(mode="w+") as tmpfile:
        proc = subprocess.Popen(
            [CLAUDE_BIN, *args], stdout=subprocess.PIPE, stderr=tmpfile,
            text=True, env=_env(),
        )
        timed_out = threading.Event()

        def _kill_on_timeout():
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(_STREAM_TIMEOUT, _kill_on_timeout)
        watchdog.start()
        try:
            for line in proc.stdout:
                yield line
            proc.wait()
            if timed_out.is_set():
                raise ClaudeError(f"claude stream timed out after {_STREAM_TIMEOUT}s")
            if proc.returncode != 0:
                tmpfile.seek(0)
                err = tmpfile.read() or ""
                reason = _auth_failure_reason("", err, scan_text=True)
                if reason:
                    raise ClaudeAuthError(reason)
                raise ClaudeError(f"claude stream exited {proc.returncode}: {err[:500]}")
        finally:
            # Runs on normal exit, on error, AND on GeneratorExit (consumer abandoned
            # the stream, e.g. browser disconnect) — never leave an orphan claude -p.
            watchdog.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_claude_client.py -v`
Expected: ALL tests in the file PASS (the two new ones plus every existing one — the existing suite injects fake `spawn`/`runner` callables and must be unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/claude_client.py tests/test_claude_client.py
git commit -m "fix(claude): watchdog timeout + guaranteed child cleanup on the streaming CLI path"
```

---

### Task 2: Atomic content writes via `backend/fsutil.py`

`apply_revision` and `migrate_courses` already write tmp+`os.replace`; lesson, capstone, library, notes, and `write_course` writes are in-place, so an interrupted write (Pi power loss) corrupts the file. One shared helper, adopted everywhere.

**Files:**
- Create: `backend/fsutil.py`
- Modify: `backend/generation.py` (lesson write at ~line 852, capstone write at ~line 439, library write at ~line 603), `backend/notes.py` (line 58), `backend/courses.py` (`write_course` line 144, and `apply_revision` lines 179-181 switch to the helper for DRY)
- Test: `tests/test_fsutil.py` (new)

**Interfaces:**
- Produces: `fsutil.write_text_atomic(path, text)` — writes `text` to `path` via a same-directory `<name>.tmp` + `os.replace`. Accepts `Path` or `str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fsutil.py`:

```python
from backend import fsutil


def test_write_text_atomic_creates_and_replaces(tmp_path):
    target = tmp_path / "course.json"
    fsutil.write_text_atomic(target, '{"a": 1}')
    assert target.read_text() == '{"a": 1}'
    fsutil.write_text_atomic(target, '{"a": 2}')
    assert target.read_text() == '{"a": 2}'
    assert list(tmp_path.iterdir()) == [target]  # no .tmp leftover
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_fsutil.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (no `backend.fsutil`).

- [ ] **Step 3: Implement**

Create `backend/fsutil.py`:

```python
import os
from pathlib import Path


def write_text_atomic(path, text):
    """Write via a same-directory temp file + os.replace, so a crash mid-write can
    never leave a truncated file at the destination — the old content survives."""
    path = Path(path)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_fsutil.py -v`
Expected: PASS.

- [ ] **Step 5: Adopt at every content write site**

In `backend/generation.py`, add `from backend import fsutil` to the imports, then replace the three write sites:

Lesson (~line 852): `path.write_text(json.dumps(lesson, indent=2, ensure_ascii=False))` becomes

```python
    fsutil.write_text_atomic(path, json.dumps(lesson, indent=2, ensure_ascii=False))
```

Capstone (~line 439): `path.write_text(json.dumps(capstone, indent=2, ensure_ascii=False))` becomes

```python
    fsutil.write_text_atomic(path, json.dumps(capstone, indent=2, ensure_ascii=False))
```

Library (~line 603): `path.write_text(json.dumps(library, indent=2, ensure_ascii=False))` becomes

```python
    fsutil.write_text_atomic(path, json.dumps(library, indent=2, ensure_ascii=False))
```

In `backend/notes.py`, add `from backend import fsutil` and replace `path.write_text(blob)` (line 58) with:

```python
    fsutil.write_text_atomic(path, blob)
```

In `backend/courses.py`, add `from backend import fsutil` and:

`write_course` (line 144): `(course_dir / "course.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))` becomes

```python
    fsutil.write_text_atomic(course_dir / "course.json", json.dumps(manifest, indent=2, ensure_ascii=False))
```

`apply_revision` (lines 179-181): replace

```python
    tmp = course_dir / "course.json.tmp"
    tmp.write_text(json.dumps(revised, indent=2, ensure_ascii=False))
    os.replace(tmp, manifest_path)
```

with

```python
    fsutil.write_text_atomic(manifest_path, json.dumps(revised, indent=2, ensure_ascii=False))
```

(The `import os` at the top of `courses.py` becomes unused ONLY if nothing else in the file uses `os` — check before removing.)

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/pytest`
Expected: ALL PASS (writes produce identical file contents; only the mechanism changed).

- [ ] **Step 7: Commit**

```bash
git add backend/fsutil.py tests/test_fsutil.py backend/generation.py backend/notes.py backend/courses.py
git commit -m "fix(storage): atomic tmp+replace writes for all course content (lesson/capstone/library/notes/manifest)"
```

---

### Task 3: Corrupt-cache self-heal in `courses.load_lesson` / `courses.load_manifest`

A partially-written lesson file currently 500s forever: the file exists so `ensure_lesson` never regenerates, and `load_lesson` raises `JSONDecodeError` uncaught. Capstone (`generation.py:398-401`) and library already self-heal — mirror that. A corrupt `course.json` should read as missing (404) rather than a 500.

**Files:**
- Modify: `backend/courses.py` (`load_manifest` lines 10-14, `load_lesson` lines 17-21)
- Test: `tests/test_courses.py`, `tests/test_generation.py`

**Interfaces:**
- Produces: `load_manifest(content_dir, course_id)` and `load_lesson(content_dir, course_id, lesson_id)` — unchanged signatures; now return `None` (instead of raising) when the file contains invalid JSON.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_courses.py` (uses the existing `tmp_path` conventions in that file):

```python
def test_load_manifest_returns_none_on_corrupt_json(tmp_path):
    course_dir = tmp_path / "c1"
    course_dir.mkdir()
    (course_dir / "course.json").write_text('{"id": "c1", "title": ')  # truncated write
    assert courses.load_manifest(tmp_path, "c1") is None


def test_load_lesson_returns_none_on_corrupt_json(tmp_path):
    lessons = tmp_path / "c1" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "c1-l1.json").write_text('{"id": "c1-l1"')  # truncated write
    assert courses.load_lesson(tmp_path, "c1", "c1-l1") is None
```

Append to `tests/test_generation.py` a regeneration test. **Adapt the manifest/lesson fixtures to the ones the existing `ensure_lesson` tests in this file already use** (there are passing `ensure_lesson` tests with a stub `generate` — copy their setup verbatim); the essential assertions are:

```python
def test_ensure_lesson_regenerates_corrupt_cache(tmp_path):
    # setup: same manifest + stub generate as the existing ensure_lesson happy-path test
    # ... existing setup here ...
    lesson_path = tmp_path / COURSE_ID / "lessons" / f"{LESSON_ID}.json"
    lesson_path.parent.mkdir(parents=True, exist_ok=True)
    lesson_path.write_text('{"truncated": ')  # corrupt cache — must NOT be a dead end
    lesson = generation.ensure_lesson(tmp_path, COURSE_ID, LESSON_ID, {}, generate=stub_generate)
    assert lesson is not None
    assert json.loads(lesson_path.read_text())  # cache repaired with valid JSON
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_courses.py tests/test_generation.py -k "corrupt" -v`
Expected: the two loader tests FAIL with `json.decoder.JSONDecodeError`; the regeneration test FAILS the same way.

- [ ] **Step 3: Implement**

In `backend/courses.py` replace both loaders:

```python
def load_manifest(content_dir, course_id):
    path = Path(content_dir) / course_id / "course.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None  # corrupt manifest reads as missing (404), never a 500


def load_lesson(content_dir, course_id, lesson_id):
    path = Path(content_dir) / course_id / "lessons" / f"{lesson_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None  # corrupt cache reads as missing so ensure_lesson regenerates it
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_courses.py tests/test_generation.py -v`
Expected: ALL PASS (including `list_courses`' existing malformed-course skip, which now sees `None` progress and still skips via its `TypeError` catch — verify no existing test broke).

- [ ] **Step 5: Commit**

```bash
git add backend/courses.py tests/test_courses.py tests/test_generation.py
git commit -m "fix(courses): corrupt course.json/lesson caches self-heal instead of permanent 500"
```

---

### Task 4: Single-flight lock on expensive generation (`ensure_lesson`, `ensure_capstone`, `ensure_bibliography`)

Check-then-generate has no lock: a double-click on an uncached lesson fires two full ~110s web-search generations (real Max-plan cost). Waitress serves multiple threads, so this is a real race. Add a per-key lock; the second caller blocks, then finds the cache populated.

**Files:**
- Modify: `backend/generation.py` (`ensure_lesson` lines 856-864, `ensure_capstone` lines 395-440, `ensure_bibliography` lines 582-604; add `import threading` and the lock helpers near the top)
- Test: `tests/test_generation.py`

**Interfaces:**
- Produces: `_gen_lock(key)` returning a `threading.Lock` unique per key (internal). Public signatures unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py` (add `import threading` and `import time` if missing). **Reuse the existing `ensure_lesson` happy-path fixtures**; the stub generate is wrapped to be slow and counted:

```python
def test_ensure_lesson_single_flight(tmp_path):
    # setup: same manifest as the existing ensure_lesson happy-path test
    # ... existing setup here ...
    calls = []

    def slow_generate(prompt):
        calls.append(1)
        time.sleep(0.3)
        return stub_generate(prompt)  # the same valid-lesson stub the existing test uses

    results = [None, None]

    def hit(i):
        results[i] = generation.ensure_lesson(tmp_path, COURSE_ID, LESSON_ID, {}, generate=slow_generate)

    t1 = threading.Thread(target=hit, args=(0,))
    t2 = threading.Thread(target=hit, args=(1,))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert len(calls) == 1  # second caller waited, then served the cache
    assert results[0] == results[1]
```

Note: if the existing stub pipeline routes through `run_sourced`-style `generate` returning `(obj, sources)`, match that shape exactly as the existing test does.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation.py -k "single_flight" -v`
Expected: FAIL with `assert len(calls) == 1` (both threads generated → 2).

- [ ] **Step 3: Implement**

In `backend/generation.py`, add `import threading` and, near the other module-level constants:

```python
# Single-flight: expensive generations (a lesson is ~110s of Max-plan web search) must
# never run twice concurrently for the same artifact. The second caller blocks on the
# per-key lock, then finds the cache the first caller just wrote.
_GEN_LOCKS = {}
_GEN_LOCKS_GUARD = threading.Lock()


def _gen_lock(key):
    with _GEN_LOCKS_GUARD:
        lock = _GEN_LOCKS.get(key)
        if lock is None:
            lock = _GEN_LOCKS[key] = threading.Lock()
    return lock
```

Rewrite `ensure_lesson`:

```python
def ensure_lesson(content_dir, course_id, lesson_id, profile, *, generate, performance="",
                  verify_generate=None):
    existing = courses.load_lesson(content_dir, course_id, lesson_id)
    if existing is not None:
        return existing
    with _gen_lock(("lesson", course_id, lesson_id)):
        existing = courses.load_lesson(content_dir, course_id, lesson_id)
        if existing is not None:
            return existing  # a concurrent request generated it while we waited
        return _generate_and_store_lesson(
            content_dir, course_id, lesson_id, profile, generate=generate,
            performance=performance, verify_generate=verify_generate,
        )
```

In `ensure_capstone`, wrap the body after the initial fast-path cache check: keep lines 396-401 (the existing `path` + cached-return block) as the fast path, then indent everything from `manifest = courses.load_manifest(...)` through the final `return capstone` inside:

```python
    with _gen_lock(("capstone", course_id, scope)):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except ValueError:
                pass  # regenerate a corrupt cache
        # ... existing body unchanged, one indent level deeper ...
```

In `ensure_bibliography`, same shape: keep the fast-path check (lines 583-588), then:

```python
    with _gen_lock(("library", course_id)):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except ValueError:
                pass  # regenerate a corrupt cache
        # ... existing body unchanged, one indent level deeper ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_generation.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "fix(generation): single-flight lock so concurrent requests can't double-generate a lesson/capstone/library"
```

---

### Task 5: Compiler — reject per-module objectives responses that drop lessons

`valid_module_objectives` doesn't require the response to carry the same number of lessons as the module sent in. A model response that drops a lesson passes validation, leaves that lesson with `objectives: []`, and the WHOLE compile 502s at final validation — instead of the cheap targeted per-module retry that `run_structured` already provides.

**Files:**
- Modify: `backend/compiler.py` (`_objectives_and_graph`, line ~160)
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `verify(prompt, validate)` — the injected structured-generation callable (existing).
- Produces: unchanged public API; the validator passed to `verify` for each module now also requires `len(obj["lessons"]) == len(module_in["lessons"])`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_compiler.py`:

```python
def test_module_objectives_validator_rejects_dropped_lessons():
    outline = {
        "title": "T",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "l1", "title": "A", "estMinutes": 30},
            {"id": "l2", "title": "B", "estMinutes": 30},
        ]}],
    }
    captured = {}

    def fake_verify(prompt, validate):
        captured["validate"] = validate
        return {
            "outcomes": [{"text": "Do X", "bloom": "apply", "knowledge": "procedural"}],
            "lessons": [
                {"id": "l1", "title": "A",
                 "objectives": [{"text": "Calc", "bloom": "apply", "knowledge": "procedural"}],
                 "prereqs": []},
                {"id": "l2", "title": "B",
                 "objectives": [{"text": "Calc", "bloom": "apply", "knowledge": "procedural"}],
                 "prereqs": []},
            ],
        } if "roll" not in prompt.lower() else {
            "outcomes": [{"text": "Do X", "bloom": "apply", "knowledge": "procedural"}],
            "skills": ["x"],
        }

    compiler._objectives_and_graph(outline, verify=fake_verify)
    validate = captured["validate"]
    full = fake_verify("module", lambda o: True)
    assert validate(full) is True
    short = {**full, "lessons": full["lessons"][:1]}  # model dropped a lesson
    assert validate(short) is False
```

Note: `fake_verify` distinguishes the roll-up call by prompt text; check `_course_rollup_prompt`'s actual wording ("rolling module-level outcomes up") and adjust the `"roll" in prompt` test if needed so the module call and roll-up call each get a valid shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_compiler.py -k "dropped_lessons" -v`
Expected: FAIL at `assert validate(short) is False` (currently True — count not checked).

- [ ] **Step 3: Implement**

In `_objectives_and_graph`, replace the `res = verify(...)` line:

```python
        # Require the response to carry EVERY lesson we sent: a dropped lesson would pass
        # shape validation, get objectives: [], and 502 the whole compile downstream —
        # rejecting here converts that into run_structured's cheap targeted retry.
        expected = len(module_in["lessons"])
        res = verify(
            _module_objectives_prompt(module_in, earlier),
            lambda o: valid_module_objectives(o) and len(o.get("lessons", [])) == expected,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_compiler.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/compiler.py tests/test_compiler.py
git commit -m "fix(compiler): per-module validator rejects responses that drop lessons (targeted retry instead of whole-compile 502)"
```

---

### Task 6: Remove dead code — `generation.detect_proposal` and `generation.restore_entities`

Both are referenced only by tests (verified by grep on 2026-07-15): `detect_proposal` belonged to the pre-compile proposal flow; `restore_entities` was a one-off migration helper whose repair already ran.

**Files:**
- Modify: `backend/generation.py` (delete `restore_entities` at ~line 54 and `detect_proposal` at ~line 178, including their comments/docstrings)
- Modify: `tests/test_generation.py` (delete the tests that exercise ONLY these two functions)

- [ ] **Step 1: Verify they are still unreferenced**

Run: `grep -rn "detect_proposal\|restore_entities" backend/ frontend/ --include="*.py" --include="*.js"`
Expected: hits ONLY in `backend/generation.py` (the definitions). If any production reference appears, STOP and report BLOCKED.

- [ ] **Step 2: Delete the two functions and their tests**

Delete both function definitions from `backend/generation.py`. In `tests/test_generation.py`, delete every test whose only subject is `detect_proposal` or `restore_entities` (find them with `grep -n "detect_proposal\|restore_entities" tests/test_generation.py`). Do not touch tests that merely mention them in passing alongside other assertions — if any exist, remove only the dead assertions.

- [ ] **Step 3: Run the full backend suite**

Run: `.venv/bin/pytest`
Expected: ALL PASS, no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/generation.py tests/test_generation.py
git commit -m "refactor(generation): drop dead detect_proposal + restore_entities (test-only references)"
```

---

### Task 7: View hardening — escaping gaps, dead-end buttons, refine placeholder, source-link scheme filter

Four small view fixes. Server-side escaping context (IMPORTANT, from Global Constraints): manifest/course **titles are NOT server-escaped** — every other view escapes them client-side (`home.js:6`, `curriculum.js:65`, `syllabus.js:34`); `dashboard.js` and `shell.js` are the two misses.

**Files:**
- Modify: `frontend/src/views/dashboard.js` (escape `data.topic`/`data.sub` lines 56-57; disable Start/Review buttons lines 61, 77), `frontend/src/views/shell.js` (escape `back`), `frontend/src/views/chat.js` (placeholder param), `frontend/src/views/syllabus.js` (`sourceList` scheme filter line 19-21), `frontend/src/app.js` (ONLY two one-line data changes: `complete` flag in `sessionData`, refine placeholder in `paintRefine`)
- Test: `frontend/tests/views.test.js`, `frontend/tests/chat.test.js`

**Interfaces:**
- Produces: `chatHTML(messages, { pending, placeholder })` — new optional `placeholder` string, defaulting to the current course-creation copy (existing callers unchanged). `dashboardHTML` consumes new `data.complete` boolean.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/views.test.js` (match the file's existing import/assert style):

```js
test("dashboardHTML escapes model-derived topic and sub", () => {
  const html = dashboardHTML(
    { topic: "<script>x</script>", sub: "<img src=x onerror=1>", durationMin: 90,
      progressPct: 0, lessonsDone: 0, lessonsTotal: 2, reviewsDue: 0,
      masteryCounts: {}, contract: null, complete: false },
    { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" },
  );
  assert.ok(!html.includes("<script>x</script>"));
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("dashboardHTML disables Start session when the course is complete", () => {
  const data = { topic: "Course complete", sub: "T", durationMin: 90, progressPct: 100,
    lessonsDone: 2, lessonsTotal: 2, reviewsDue: 0, masteryCounts: {}, contract: null,
    complete: true };
  const tv = { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" };
  const html = dashboardHTML(data, tv);
  assert.match(html, /data-action="start-session"[^>]*disabled/);
});

test("dashboardHTML disables Review when nothing is due", () => {
  const data = { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
    lessonsTotal: 2, reviewsDue: 0, masteryCounts: {}, contract: null, complete: false };
  const tv = { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" };
  const html = dashboardHTML(data, tv);
  assert.match(html, /data-action="review"[^>]*disabled/);
  const due = dashboardHTML({ ...data, reviewsDue: 3 }, tv);
  assert.ok(!/data-action="review"[^>]*disabled/.test(due));
});

test("shellHTML escapes the back label", () => {
  const html = shellHTML({ back: '<img src=x onerror=1>' });
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;img"));
});

test("syllabusHTML drops non-http(s) source URLs", () => {
  const course = { title: "T", subtitle: "", level: {}, modules: [],
    groundingSources: [
      { url: "javascript:alert(1)", title: "evil", type: "other" },
      { url: "https://ok.example/x", title: "fine", type: "university" },
    ] };
  const html = syllabusHTML(course);
  assert.ok(!html.includes("javascript:alert"));
  assert.ok(html.includes("https://ok.example/x"));
});
```

Append to `frontend/tests/chat.test.js` (add the `chatHTML` import from `../src/views/chat.js`):

```js
test("chatHTML escapes message content", () => {
  const html = chatHTML([{ role: "assistant", content: "<script>x</script>" }]);
  assert.ok(!html.includes("<script>x</script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("chatHTML accepts a custom placeholder", () => {
  const html = chatHTML([], { placeholder: "describe your change" });
  assert.ok(html.includes('placeholder="describe your change"'));
  const dflt = chatHTML([]);
  assert.ok(dflt.includes("intermediate linear algebra"));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/tests/views.test.js frontend/tests/chat.test.js`
Expected: the new tests FAIL (raw interpolation, no disabled attrs, no placeholder param).

- [ ] **Step 3: Implement**

`frontend/src/views/dashboard.js` — lines 56-57 become:

```js
      <h2 class="session-topic">${esc(data.topic)}</h2>
      <div class="session-sub">${esc(data.sub)}</div>
```

Line 61 (Start button):

```js
      <button class="btn-primary" data-action="start-session"${data.complete ? " disabled" : ""}>${PLAY_ICON} Start session</button>
```

Line 77 (Review button):

```js
        <button class="btn-secondary" data-action="review"${data.reviewsDue ? "" : " disabled"}>Review</button>
```

`frontend/src/views/shell.js` — becomes:

```js
import { esc } from "../escape.js";

export function shellHTML({ back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${esc(back)}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
    </header>
    ${backBtn}
    <div id="view"></div>
  `;
}
```

`frontend/src/views/chat.js` — signature and textarea become:

```js
export function chatHTML(messages, {
  pending = false,
  placeholder = "e.g. intermediate linear algebra for ML, ~3 hours a week — I know basic calculus",
} = {}) {
```

```js
        <textarea data-field="chat" rows="3" placeholder="${esc(placeholder)}"></textarea>
```

`frontend/src/views/syllabus.js` — `sourceList` filter (line 20) becomes:

```js
  const items = (sources || [])
    .filter((s) => s && typeof s.url === "string" && /^https?:\/\//.test(s.url))
```

`frontend/src/app.js` — in `sessionData()` add one field after `topic`/`sub`:

```js
      complete: !next,
```

In `paintRefine()` (line 183), the `chatHTML` call becomes:

```js
    view.innerHTML = chatHTML(msgs, {
      pending: false,
      placeholder: "e.g. add a module on transformers, drop the intro lesson, go deeper in module 2",
    });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test frontend/tests/*.test.js`
Expected: ALL PASS (including every pre-existing view test — the default placeholder keeps the creation chat byte-identical).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/dashboard.js frontend/src/views/shell.js frontend/src/views/chat.js frontend/src/views/syllabus.js frontend/src/app.js frontend/tests/views.test.js frontend/tests/chat.test.js
git commit -m "fix(views): escape manifest titles on dashboard/shell, disable dead-end buttons, refine placeholder, http(s)-only source links"
```

---

### Task 8: app.js navigation guards + bootstrap error boundary + create-course error state

Flows that await and then paint without checking whether the user navigated away: `sendChat` (streams over whatever screen is showing), `openLesson`, `startReviewSession`, `advanceAfterLesson`, `acceptSyllabus`. Sibling flows (`sendWsChat` at line 444, `deepenCurrentLesson` at 375, check-answer at 514, `proposeRevision` at 225) already guard — copy their pattern. Plus: `init()` has no error boundary (a failed profile fetch leaves the app stuck on "Loading…" forever), and `acceptSyllabus` fails silently.

**Files:**
- Modify: `frontend/src/app.js` (functions `openLesson` ~346, `startReviewSession` ~618, `advanceAfterLesson` ~604, `sendChat` ~659, `acceptSyllabus` ~712, init tail ~751), `frontend/src/profile.js` (`loadProfile` line 74)
- Test: `frontend/tests/profile.test.js` (app.js itself has no unit-test harness — verification is the full frontend suite + the import-resolution check in Step 5)

**Interfaces:**
- Produces: `loadProfile({ fetch, endpoint })` now THROWS on a non-ok response (still returns `null` when the server has no profile). `init` catches that and renders a retry screen.

- [ ] **Step 1: Write the failing test**

Append to `frontend/tests/profile.test.js` (match its existing fake-fetch style):

```js
test("loadProfile throws on a non-ok response instead of parsing it", async () => {
  const fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  await assert.rejects(() => loadProfile({ fetch, endpoint: "/api/profile" }));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/profile.test.js`
Expected: FAIL (current code calls `resp.json()` regardless and resolves).

- [ ] **Step 3: Implement**

`frontend/src/profile.js` — `loadProfile` becomes:

```js
export async function loadProfile({ fetch, endpoint }) {
  const resp = await fetch(endpoint);
  if (!resp.ok) throw new Error(`profile fetch failed: ${resp.status}`);
  const body = await resp.json();
  return body && body.data ? body.data : null;
}
```

`frontend/src/app.js` — the init tail (lines 751-753) becomes:

```js
  let profile;
  try {
    profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  } catch (e) {
    root.innerHTML =
      `<div class="card"><div class="prompt">Couldn't reach the server. Check that the service is running, then retry.</div>` +
      `<div class="nav"><button class="btn-primary" data-action="retry">Retry</button></div></div>`;
    root.querySelector('[data-action="retry"]').addEventListener("click", () => window.location.reload());
    return;
  }
  if (profile) showHome();
  else showDiagnostic();
```

`sendChat` — the streaming callbacks gain the same guard `sendWsChat` uses (capture the chat object so a NEW chat session isn't painted over either):

```js
  async function sendChat() {
    const ta = root.querySelector('[data-field="chat"]');
    const text = ta.value.trim();
    if (!text || ui.chat.pending) return;
    const chat = ui.chat;
    const onScreen = () => ui.screen === "chat" && ui.chat === chat;
    chat.messages.push({ role: "user", content: text });       // raw
    const reply = { role: "assistant", content: "" };
    chat.messages.push(reply);
    chat.pending = true;
    paintChat();
    const history = chat.messages
      .filter((m) => m !== reply)                                  // exclude the in-progress placeholder
      .map((m) => ({ role: m.role, content: m.content }));
    await streamChat({
      fetch,
      messages: history,
      onDelta: (d) => { reply.content += d; if (onScreen()) paintChat(); },
      onBrief: (b) => { chat.brief = b; },
      onDone: () => { chat.pending = false; if (onScreen()) paintChat(); },
      onError: (e) => { reply.content = "⚠️ " + (e.message || "Claude is unavailable right now."); chat.pending = false; if (onScreen()) paintChat(); },
    });
  }
```

(Note: the existing "⚠️" glyph is pre-existing copy — keep it as-is; the no-emoji rule applies to NEW copy.)

`openLesson` — becomes (a `loadSeq` token disambiguates two racing openLesson calls; any navigation changes `ui.screen` away from `"lesson-loading"`):

```js
  async function openLesson(lessonId) {
    if (!lessonId) return;
    ui.reviewQueue = [];
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "lesson-loading";
    const view = root.querySelector("#view");
    if (view) startLoading(view, "lesson", LESSON_STAGES);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId });
    if (ui.screen !== "lesson-loading" || ui.loadSeq !== seq) return; // navigated away mid-load
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showLessonError(ui.lesson && ui.lesson.error || "Couldn't load this lesson."); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: lessonId });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

`startReviewSession` — becomes:

```js
  async function startReviewSession() {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "review-loading";
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }
```

`advanceAfterLesson` — becomes (rating happens ON the lesson screen; any navigation flips `ui.screen`):

```js
  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (ui.screen !== "lesson") return; // navigated away while loading the next review
      ui.lesson = lesson;
      if (lessonFailed(ui.lesson)) { await refreshSummary(); if (ui.screen !== "lesson") return; showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    if (ui.screen !== "lesson") return; // navigated away — don't yank them to the dashboard
    showCourse();
  }
```

`acceptSyllabus` — becomes (mirrors `buildProgram`'s error card):

```js
  async function acceptSyllabus() {
    const proposed = ui.proposedCourse;
    const course = await createCourse({ fetch, proposal: proposed });
    if (ui.screen !== "syllabus") return; // navigated away mid-create
    if (!course) {
      const view = root.querySelector("#view");
      view.innerHTML =
        `<div class="card"><div class="prompt">Couldn't create the course right now. Your proposal is still here — try again.</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back to proposal</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", () => showSyllabus(proposed));
      return;
    }
    log("course_created", { courseId: course.id });
    openCourse(course.id);
  }
```

- [ ] **Step 4: Run the full frontend suite**

Run: `node --test frontend/tests/*.test.js`
Expected: ALL PASS.

- [ ] **Step 5: Import-resolution check on app.js and profile.js**

Run: `node --input-type=module -e "import('./frontend/src/app.js').then(() => console.log('app OK')); import('./frontend/src/profile.js').then(() => console.log('profile OK'))"`
Expected: both `OK` lines, no syntax/import errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app.js frontend/src/profile.js frontend/tests/profile.test.js
git commit -m "fix(app): navigation guards after every await, bootstrap error boundary, create-course error state"
```

---

## Explicitly NOT in this pass (audit items judged not-bugs or deferred)

- Lesson `topic`/`eyebrow`, check text, grade note, capstone/library text raw in views: **server-escaped/sanitized** (`generation.py:837-848`, `:345`, `:428-437`, `_resolve_sources`) — client `esc()` would double-escape.
- "Step 1 of 1": false positive — `generation.py:830-831` overwrites with real course position post-generation.
- `lesson_completed` in `courses.completed_lesson_ids`: legacy event type from early slices; production DB may hold such events — keep reading it.
- Auth-marker text heuristic breadth: only consulted on nonzero exit; misclassification just changes one error message into another. Not worth the regression risk.
- `pre-revise-*` backup accumulation, workspace id-existence checks, app.js module split: deferred (YAGNI until they hurt).
