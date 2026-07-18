# Lesson Text Highlights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a learner drag-select any span of a lesson's prose, mark it as a persistent highlight (tap to remove), with the highlight surviving reload and reappearing at the right spot via text-search re-anchoring — purely visual, no downstream use.

**Architecture:** A third field `highlights: [{id, text, occurrence}]` is added to the existing per-lesson workspace JSON file (same file Notes/Chat already use), threaded through the existing `backend/notes.py` validate/save/load functions and the existing `GET`/`PUT /workspace` routes. On the frontend, a new pure-logic-plus-DOM module (`frontend/src/highlights.js`) implements occurrence-based text search and the split-and-wrap DOM mechanics; `frontend/src/app.js` wires selection capture (a floating "Highlight" button scoped to `.prompt`), creation, re-application on every lesson repaint, and tap-to-remove — mirroring the existing `hydrateFigures`/`seedWorkspace`/delegated-root-click patterns already in that file.

**Tech Stack:** Flask + stdlib JSON (backend, no new dependency), vanilla ES modules + native DOM `Selection`/`Range`/`Text.splitText` APIs (frontend, no new dependency, no framework).

## Global Constraints

- No new pip/npm dependencies anywhere in this plan.
- Pure DOM APIs only for selection/highlighting (`Selection`, `Range`, `Text.splitText`) — **never** `Range.surroundContents()` (it throws when a range only partially contains an element, which a free-form selection crossing a `<strong>`/`<em>` boundary makes routine).
- Storage: a third field `highlights: [{id, text, occurrence}]` on the EXISTING per-lesson workspace file at `content/courses/<course_id>/notes/<lesson_id>.json` — no new file, no new artifact directory.
- Reuses the EXISTING `_MAX_BYTES = 100_000` total-serialized-size cap in `backend/notes.py` — no new size constant for highlights specifically.
- Validation (`_valid_highlights` in `backend/notes.py`): list of dicts; each `id` a non-empty string ≤64 chars; `text` a non-empty string ≤2000 chars; `occurrence` a non-negative int with `bool` explicitly excluded (Python `bool` is an `int` subclass — must check `isinstance(x, bool)` BEFORE the int check).
- Anchoring rule (binding): `occurrence` = 0-based index of which match of `text` this highlight refers to, counted across the container's flattened text content at creation time. On render: find all occurrences of `text`, apply to the one at index `occurrence` if it exists, silently skip if not found or out of range — NEVER show a highlight in the wrong place.
- Scope (binding): highlighting only active inside `frontend/src/views/lesson.js`'s `<div class="prompt">` container — NOT `.lesson-side` (workspace/chat), NOT exercise/checks/solution. A selection that starts or ends outside `.prompt` never shows the highlight button.
- Save trigger: immediate PUT on add/remove (NOT debounced like Notes' typing) — same optimistic-local-cache-first pattern `saveWorkspace` already uses.
- Security: stored `text` is NEVER inserted as HTML/innerHTML — only used as a plain-text search key; DOM insertion only via `Text.splitText` + creating a `<mark>` element with safe DOM methods (`createElement`, `appendChild`, `setAttribute`, `textContent`) — never string concatenation into innerHTML.
- No emojis anywhere. Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Testing environment note (read before Task 3, 5, 6)

This repo's frontend tests run under **plain Node.js `node --test`** with no jsdom, no browser, and no DOM shim of any kind (`frontend/package.json` is just `{ "type": "module" }` — no devDependencies at all; confirmed by grepping the whole `frontend/` tree for `jsdom`/`document.`/`window.` — the only hit is `app.js` itself, never a test file). There is no global `document`, `Node`, `Text`, or `Element` in this test environment. This means:
- Pure string/array logic (no DOM) CAN be unit-tested with `node --test` — Task 3's `findNthOccurrence`/`countOccurrencesBefore`.
- Anything touching `Text.splitText`, `TreeWalker`, `createElement`, `Selection`/`Range` CANNOT be unit-tested here — no fake DOM is invented for it (a fake DOM would test the fake, not the real bug surface). Task 3's `flattenTextNodes`/`applyHighlight`/`applyHighlights`/`removeHighlightMarks`, and all of Task 5/6's `app.js` selection/paint wiring, are verified only via (a) an import-resolution check (`node -e "import(...)"`, catches typos/syntax errors) and (b) an explicit manual/Pi verification checklist — never a fake automated test standing in for real DOM behavior.

---

### Task 1: `backend/notes.py` — validate and persist `highlights`

**Files:**
- Modify: `backend/notes.py`
- Modify: `tests/test_notes.py`
- Modify: `tests/test_courses_api.py:518-519` (one-line fix — see Step 5 below; the shape change to `notes.load_workspace`'s return value breaks this pre-existing route test's hardcoded dict even before Task 2 touches the route code, since `get_workspace` already calls `load_workspace` directly)

**Interfaces:**
- Produces: `notes.load_workspace(content_dir, course_id, lesson_id) -> dict` with keys `{"notes": str, "chat": list, "highlights": list, "updatedAt": str|None}` (added `"highlights"` key).
- Produces: `notes.save_workspace(content_dir, course_id, lesson_id, notes, chat, highlights=None) -> dict` — same return shape; raises `ValueError` on any invalid shape (including invalid `highlights`), raises `notes.WorkspaceTooLarge` if the serialized record (now including `highlights`) exceeds `_MAX_BYTES`. `highlights` defaults to `[]` when omitted (backward-compatible with existing callers).
- Produces (private, used only inside this module): `notes._valid_highlights(highlights) -> bool`.
- Produces: `notes._EMPTY` now includes `"highlights": []`.

- [ ] **Step 1: Write the failing/updated tests**

Replace the full contents of `tests/test_notes.py` with:

```python
import json

import pytest
from backend import notes


def test_load_workspace_default_when_missing(tmp_path):
    assert notes.load_workspace(tmp_path, "c", "l1") == {
        "notes": "", "chat": [], "highlights": [], "updatedAt": None}


def test_save_and_load_roundtrip(tmp_path):
    rec = notes.save_workspace(tmp_path, "c", "l1", "my notes",
                               [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    assert rec["notes"] == "my notes"
    assert rec["updatedAt"]
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["notes"] == "my notes"
    assert ws["chat"][1] == {"role": "assistant", "content": "yo"}


def test_save_workspace_rejects_bad_shape(tmp_path):
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", "n", [{"role": "bad", "content": "x"}])
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", 123, [])


def test_save_workspace_enforces_size_cap(tmp_path):
    with pytest.raises(notes.WorkspaceTooLarge):
        notes.save_workspace(tmp_path, "c", "l1", "x" * 200000, [])


def test_load_workspace_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "c" / "notes" / "l1.json"
    p.parent.mkdir(parents=True)
    p.write_text("not json{")
    assert notes.load_workspace(tmp_path, "c", "l1")["notes"] == ""


def test_save_and_load_roundtrip_with_highlights(tmp_path):
    hl = [{"id": "h1", "text": "some phrase", "occurrence": 0}]
    rec = notes.save_workspace(tmp_path, "c", "l1", "n", [], hl)
    assert rec["highlights"] == hl
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["highlights"] == hl


def test_load_workspace_defaults_highlights_when_absent_from_file(tmp_path):
    # Simulates a workspace file written before this feature existed (no "highlights" key).
    p = tmp_path / "c" / "notes" / "l1.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"notes": "n", "chat": [], "updatedAt": "t"}))
    ws = notes.load_workspace(tmp_path, "c", "l1")
    assert ws["highlights"] == []


def test_save_workspace_defaults_highlights_when_omitted(tmp_path):
    # An old call site (or old client PUT body) that never passes highlights at all.
    rec = notes.save_workspace(tmp_path, "c", "l1", "n", [])
    assert rec["highlights"] == []


@pytest.mark.parametrize("bad_highlights", [
    "not-a-list",
    [{"id": "h1", "text": "x"}],                          # missing occurrence
    [{"id": "h1", "occurrence": 0}],                       # missing text
    [{"text": "x", "occurrence": 0}],                      # missing id
    [{"id": "", "text": "x", "occurrence": 0}],            # empty id
    [{"id": "h1", "text": "", "occurrence": 0}],           # empty text
    [{"id": "h1", "text": "x" * 2001, "occurrence": 0}],   # text over 2000 chars
    [{"id": "h" * 65, "text": "x", "occurrence": 0}],      # id over 64 chars
    [{"id": "h1", "text": "x", "occurrence": -1}],         # negative occurrence
    [{"id": "h1", "text": "x", "occurrence": 1.5}],        # non-int occurrence
    [{"id": "h1", "text": "x", "occurrence": True}],       # bool occurrence explicitly rejected
    [{"id": 1, "text": "x", "occurrence": 0}],             # non-string id
    [{"id": "h1", "text": 1, "occurrence": 0}],            # non-string text
    ["not-a-dict"],                                        # list of non-dicts
])
def test_save_workspace_rejects_bad_highlights(tmp_path, bad_highlights):
    with pytest.raises(ValueError):
        notes.save_workspace(tmp_path, "c", "l1", "n", [], bad_highlights)


def test_save_workspace_enforces_size_cap_via_highlights(tmp_path):
    big_highlights = [{"id": f"h{i}", "text": "x" * 500, "occurrence": 0} for i in range(300)]
    with pytest.raises(notes.WorkspaceTooLarge):
        notes.save_workspace(tmp_path, "c", "l1", "", [], big_highlights)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_notes.py -v`

Expected: **19 failed, 4 passed**. The 4 that still pass are the untouched pre-existing behaviors (roundtrip, bad-shape rejection, size cap via notes, corrupt-file tolerance). `test_load_workspace_default_when_missing` fails on the dict-equality assertion (actual dict has no `"highlights"` key yet). Every new test that calls `save_workspace(..., highlights)` fails with `TypeError: save_workspace() takes 5 positional arguments but 6 were given` (the current signature has no 6th parameter yet).

- [ ] **Step 3: Implement — replace the full contents of `backend/notes.py`**

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil

_MAX_BYTES = 100_000  # ~100 KB cap on the serialized notes + chat + highlights
_MAX_HIGHLIGHT_TEXT = 2000  # per-highlight text cap (design doc Decision 3)
_MAX_HIGHLIGHT_ID = 64  # generous cap on the client-generated id (ids.newId()), not a real limit
_EMPTY = {"notes": "", "chat": [], "highlights": [], "updatedAt": None}


class WorkspaceTooLarge(ValueError):
    pass


def _path(content_dir, course_id, lesson_id):
    return Path(content_dir) / course_id / "notes" / f"{lesson_id}.json"


def load_workspace(content_dir, course_id, lesson_id):
    path = _path(content_dir, course_id, lesson_id)
    if not path.exists():
        return dict(_EMPTY)
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    return {
        "notes": data["notes"] if isinstance(data.get("notes"), str) else "",
        "chat": data["chat"] if isinstance(data.get("chat"), list) else [],
        "highlights": data["highlights"] if isinstance(data.get("highlights"), list) else [],
        "updatedAt": data.get("updatedAt"),
    }


def _valid_chat(chat):
    if not isinstance(chat, list):
        return False
    for m in chat:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return False
        if not isinstance(m.get("content"), str):
            return False
    return True


def _valid_highlights(highlights):
    if not isinstance(highlights, list):
        return False
    for h in highlights:
        if not isinstance(h, dict):
            return False
        hid = h.get("id")
        if not isinstance(hid, str) or not hid or len(hid) > _MAX_HIGHLIGHT_ID:
            return False
        text = h.get("text")
        if not isinstance(text, str) or not text or len(text) > _MAX_HIGHLIGHT_TEXT:
            return False
        occurrence = h.get("occurrence")
        # bool is a subclass of int in Python -- must be excluded explicitly, checked
        # BEFORE the int check, or True/False would silently pass as 1/0.
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0:
            return False
    return True


def save_workspace(content_dir, course_id, lesson_id, notes, chat, highlights=None):
    if highlights is None:
        highlights = []
    if not isinstance(notes, str) or not _valid_chat(chat) or not _valid_highlights(highlights):
        raise ValueError("invalid workspace shape")
    record = {
        "notes": notes,
        "chat": [{"role": m["role"], "content": m["content"]} for m in chat],
        "highlights": [
            {"id": h["id"], "text": h["text"], "occurrence": h["occurrence"]} for h in highlights
        ],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    blob = json.dumps(record, ensure_ascii=False)
    if len(blob.encode("utf-8")) > _MAX_BYTES:
        raise WorkspaceTooLarge("workspace too large")
    path = _path(content_dir, course_id, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, blob)
    return record
```

Note: `load_workspace` intentionally does the same SHALLOW check for `highlights` as it already does for `chat` (`isinstance(..., list)`, not a full `_valid_highlights` re-validation) — `_valid_highlights` is only ever called as a write-time gate from `save_workspace`, exactly mirroring how `_valid_chat` is used today.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_notes.py -v`

Expected: `23 passed`.

- [ ] **Step 5: Fix the one pre-existing route test this shape change breaks**

`tests/test_courses_api.py`'s `test_workspace_get_default_and_put_roundtrip` (currently at line ~518-519) hardcodes the GET-default dict, and `get_workspace` calls `notes.load_workspace` directly — so this test breaks the moment Step 3 lands, independent of Task 2 (which hasn't touched `app.py` yet). Fix it now so the whole suite stays green after this task.

In `tests/test_courses_api.py`, change:

```python
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json() == {
        "notes": "", "chat": [], "updatedAt": None}
```

to:

```python
    assert client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json() == {
        "notes": "", "chat": [], "highlights": [], "updatedAt": None}
```

- [ ] **Step 6: Run the full backend suite to confirm no regressions**

Run: `python3 -m pytest -q`

Expected: `807 passed` (789 baseline + 18 new tests in `tests/test_notes.py`; `tests/test_courses_api.py`'s test count is unchanged — Step 5 only edited an existing test's assertion, it didn't add one).

- [ ] **Step 7: Commit**

```bash
git add backend/notes.py tests/test_notes.py tests/test_courses_api.py
git commit -m "$(cat <<'EOF'
feat(highlights): validate and persist a highlights field in the workspace store

Adds highlights: [{id, text, occurrence}] as a third field on the existing
per-lesson workspace JSON, reusing the same _MAX_BYTES cap and the same
is-called-from-save_workspace validation pattern _valid_chat already uses.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `backend/app.py` — thread `highlights` through the workspace routes

**Files:**
- Modify: `backend/app.py:601-615` (the `put_workspace` route)
- Modify: `tests/test_courses_api.py`

**Interfaces:**
- Consumes: `notes.save_workspace(content_dir, course_id, lesson_id, notes, chat, highlights=None)` from Task 1.
- Produces: `PUT /api/courses/<course_id>/lessons/<lesson_id>/workspace` now reads `body.get("highlights", [])` and passes it through; `GET` on the same route already returns `highlights` (via Task 1's `load_workspace`, no route code change needed for GET).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_courses_api.py`, directly after the existing `test_workspace_rejects_bad_ids` test:

```python
def test_workspace_put_roundtrips_highlights(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    hl = [{"id": "h1", "text": "a phrase", "occurrence": 0}]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [], "highlights": hl})
    assert r.status_code == 200 and r.get_json()["updatedAt"]
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["highlights"] == hl


def test_workspace_put_rejects_bad_highlights(client, tmp_path, monkeypatch):
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [], "highlights": [{"id": "h1", "text": "x", "occurrence": -1}]})
    assert r.status_code == 400


def test_workspace_put_without_highlights_key_still_works(client, tmp_path, monkeypatch):
    # Regression: an OLD client that never sends "highlights" at all must behave
    # exactly as before -- notes/chat unaffected, highlights silently defaults to [].
    from backend import courses
    root = tmp_path / "courses"; root.mkdir()
    monkeypatch.setattr(courses, "CONTENT_DIR", root)
    manifest, lesson_id = _fixture_course(courses, root)
    cid = manifest["id"]
    r = client.put(f"/api/courses/{cid}/lessons/{lesson_id}/workspace",
                   json={"notes": "n", "chat": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    got = client.get(f"/api/courses/{cid}/lessons/{lesson_id}/workspace").get_json()
    assert got["notes"] == "n" and got["chat"][0]["content"] == "hi" and got["highlights"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_courses_api.py -k "workspace" -v`

Expected: **2 failed, 4 passed**. `test_workspace_put_roundtrips_highlights` fails because the current route silently drops `highlights` (it isn't read from `body` yet), so `got["highlights"]` comes back `[]` instead of the sent list. `test_workspace_put_rejects_bad_highlights` fails because the invalid highlights are never even reached (status is `200`, not `400`) — the route doesn't pass `highlights` to `save_workspace` at all yet, so its validation never runs. `test_workspace_put_without_highlights_key_still_works` already passes at this checkpoint (it never round-trips a sent highlight, so Task 1 alone already satisfies it) — that's expected and fine for a regression-lock test.

- [ ] **Step 3: Implement — modify `put_workspace` in `backend/app.py`**

Find (around line 601-615):

```python
    @app.put("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def put_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            record = notes.save_workspace(
                courses.CONTENT_DIR, course_id, lesson_id,
                body.get("notes", ""), body.get("chat", []),
            )
        except notes.WorkspaceTooLarge:
            return jsonify({"error": "notes too large"}), 413
        except ValueError:
            return jsonify({"error": "invalid workspace"}), 400
        return jsonify({"updatedAt": record["updatedAt"]})
```

Replace with:

```python
    @app.put("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def put_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            record = notes.save_workspace(
                courses.CONTENT_DIR, course_id, lesson_id,
                body.get("notes", ""), body.get("chat", []), body.get("highlights", []),
            )
        except notes.WorkspaceTooLarge:
            return jsonify({"error": "notes too large"}), 413
        except ValueError:
            return jsonify({"error": "invalid workspace"}), 400
        return jsonify({"updatedAt": record["updatedAt"]})
```

(`get_workspace`, just above it, needs no change — it already returns `notes.load_workspace(...)` verbatim, which includes `highlights` as of Task 1.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_courses_api.py -k "workspace" -v`

Expected: `6 passed`.

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `python3 -m pytest -q`

Expected: `810 passed` (807 from Task 1 + 3 new tests here).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_courses_api.py
git commit -m "$(cat <<'EOF'
feat(highlights): thread highlights through the workspace PUT route

The GET route already returned highlights via Task 1's load_workspace change;
PUT now reads body.get("highlights", []) the same way it already reads notes
and chat, so a client can actually persist a highlight, not just receive one.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `frontend/src/highlights.js` — occurrence anchoring + DOM apply/remove mechanics

**Files:**
- Create: `frontend/src/highlights.js`
- Create: `frontend/tests/highlights.test.js`

**Interfaces:**
- Produces: `findNthOccurrence(haystack, needle, occurrence) -> [start, end] | null` — pure, DOM-free.
- Produces: `countOccurrencesBefore(haystack, needle, beforeIndex) -> number` — pure, DOM-free.
- Produces: `flattenTextNodes(container) -> { text: string, nodes: [{ node, start, end }] }` — DOM-dependent (needs `container.ownerDocument.createTreeWalker`).
- Produces: `applyHighlight(container, highlight) -> boolean` — DOM-dependent; `highlight` is `{id, text, occurrence}`; returns `true` if applied, `false` if silently skipped (not found / occurrence out of range).
- Produces: `applyHighlights(container, highlights) -> void` — DOM-dependent; applies every highlight in the array.
- Produces: `removeHighlightMarks(container, highlightId) -> void` — DOM-dependent; unwraps every `<mark class="highlight" data-highlight-id="...">` matching `highlightId` back into its parent as plain text.
- Consumed later by: Task 5 (`countOccurrencesBefore`, `flattenTextNodes`, `applyHighlight`) and Task 6 (`applyHighlights`, `removeHighlightMarks`) in `frontend/src/app.js`.

- [ ] **Step 1: Write the failing tests (pure functions only — see the testing-environment note above for why the DOM-dependent functions aren't unit-tested here)**

Create `frontend/tests/highlights.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { findNthOccurrence, countOccurrencesBefore } from "../src/highlights.js";

test("findNthOccurrence finds the first occurrence", () => {
  assert.deepEqual(findNthOccurrence("the cat sat on the mat near the door", "the", 0), [0, 3]);
});

test("findNthOccurrence finds a later occurrence by index", () => {
  assert.deepEqual(findNthOccurrence("the cat sat on the mat near the door", "the", 1), [15, 18]);
});

test("findNthOccurrence returns null when there is no such occurrence", () => {
  assert.equal(findNthOccurrence("the cat sat on the mat near the door", "the", 3), null);
  assert.equal(findNthOccurrence("no match here", "xyz", 0), null);
});

test("findNthOccurrence returns null for an empty needle", () => {
  assert.equal(findNthOccurrence("some text", "", 0), null);
});

test("countOccurrencesBefore counts non-overlapping matches before a position", () => {
  const text = "the cat sat on the mat near the door";
  assert.equal(countOccurrencesBefore(text, "the", 0), 0);
  assert.equal(countOccurrencesBefore(text, "the", 15), 1);
  assert.equal(countOccurrencesBefore(text, "the", 28), 2);
  assert.equal(countOccurrencesBefore(text, "the", 37), 3);
});

test("findNthOccurrence and countOccurrencesBefore agree with each other", () => {
  const text = "aa aa aa aa";
  const [start] = findNthOccurrence(text, "aa", 2);
  assert.equal(countOccurrencesBefore(text, "aa", start), 2);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test frontend/tests/highlights.test.js`

Expected: `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../src/highlights.js'` — the file doesn't exist yet.

- [ ] **Step 3: Implement — create `frontend/src/highlights.js`**

```javascript
// Lesson prose highlights — persistent, purely visual (design doc Decision 1-6).
// Anchoring: a highlight is {id, text, occurrence} where `occurrence` is the 0-based
// index of WHICH match of `text` this highlight refers to, counted across the
// container's flattened text content. This resolves the one real ambiguity in a
// text-search approach (the same phrase appearing twice) deterministically, and means
// a highlight either lands on the exact right sentence or doesn't show at all — never
// on the wrong one (unlike a stale character offset, which always lands on SOMETHING).

// Returns the [start, end) character range of the `occurrence`-th (0-based)
// non-overlapping match of `needle` in `haystack`, or null if there is no such match
// (fewer than occurrence+1 occurrences exist, or needle is empty).
export function findNthOccurrence(haystack, needle, occurrence) {
  if (!needle || occurrence < 0) return null;
  let from = 0;
  for (let i = 0; i <= occurrence; i++) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1) return null;
    if (i === occurrence) return [idx, idx + needle.length];
    from = idx + needle.length;
  }
  return null;
}

// Counts how many non-overlapping matches of `needle` occur in `haystack` strictly
// before `beforeIndex` -- used at highlight-creation time to compute the `occurrence`
// index for a freshly-selected span, given its start offset in the flattened text.
export function countOccurrencesBefore(haystack, needle, beforeIndex) {
  if (!needle) return 0;
  let count = 0;
  let from = 0;
  for (;;) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1 || idx >= beforeIndex) return count;
    count++;
    from = idx + needle.length;
  }
}

// Walks `container`'s text nodes in document order, returning the concatenated text
// plus a parallel list of {node, start, end} offset ranges (each node's slice of that
// concatenation). This is the "flattened text with an offset map" that apply/capture
// search and split against. DOM-dependent: needs a real Document (TreeWalker).
export function flattenTextNodes(container) {
  const walker = container.ownerDocument.createTreeWalker(container, 4 /* NodeFilter.SHOW_TEXT */);
  const nodes = [];
  let text = "";
  let node;
  while ((node = walker.nextNode())) {
    const start = text.length;
    text += node.nodeValue;
    nodes.push({ node, start, end: text.length });
  }
  return { text, nodes };
}

// Applies one highlight -- {id, text, occurrence} -- to `container` by finding the
// occurrence-th match of `text` in the container's flattened text content and wrapping
// the matching text-node portions in `<mark class="highlight"
// data-highlight-id="...">`. Splits any text node the match only partially covers
// (Text.splitText) so ONLY the matched substring is wrapped -- never
// Range.surroundContents(), which throws when a range partially contains an element
// (routine for a free-form selection that starts or ends mid-tag). Silently does
// nothing if the text/occurrence isn't found (the accepted trade-off: never show a
// highlight in the wrong place). Returns true if applied, false if skipped.
export function applyHighlight(container, highlight) {
  const { text, nodes } = flattenTextNodes(container);
  const range = findNthOccurrence(text, highlight.text, highlight.occurrence);
  if (!range) return false;
  const [start, end] = range;
  const doc = container.ownerDocument;
  for (const entry of nodes) {
    if (entry.end <= start || entry.start >= end) continue; // no overlap with [start, end)
    let node = entry.node;
    const localStart = Math.max(0, start - entry.start);
    const localEnd = Math.min(node.nodeValue.length, end - entry.start);
    if (localEnd < node.nodeValue.length) node.splitText(localEnd); // keep only the overlap
    if (localStart > 0) node = node.splitText(localStart);
    const mark = doc.createElement("mark");
    mark.className = "highlight";
    mark.setAttribute("data-highlight-id", highlight.id);
    node.parentNode.insertBefore(mark, node);
    mark.appendChild(node);
  }
  return true;
}

// Applies every highlight in `highlights` to `container` -- used both right after
// creating a new highlight and on every lesson render. Order doesn't matter: each
// call re-flattens the CURRENT text nodes, so an earlier highlight's inserted <mark>
// just becomes part of the next flattening pass (its wrapped text still contributes
// its own characters at its own offset, so later occurrence-counting is unaffected).
export function applyHighlights(container, highlights) {
  for (const h of highlights || []) applyHighlight(container, h);
}

// Removes one highlight's <mark> elements (there can be more than one per highlight --
// see applyHighlight's per-text-node wrapping) by unwrapping each back into its
// parent, given the highlight's id. Filters by dataset in JS rather than interpolating
// highlightId into a querySelectorAll selector string, so a highlight id can never be
// treated as selector syntax.
export function removeHighlightMarks(container, highlightId) {
  container.querySelectorAll("mark.highlight[data-highlight-id]").forEach((mark) => {
    if (mark.dataset.highlightId !== highlightId) return;
    const parent = mark.parentNode;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test frontend/tests/highlights.test.js`

Expected: `tests 6`, `pass 6`, `fail 0`.

- [ ] **Step 5: Note on the DOM-dependent functions (not a test step — read and move on)**

`flattenTextNodes`, `applyHighlight`, `applyHighlights`, and `removeHighlightMarks` are NOT exercised by any automated test in this repo (see the testing-environment note at the top of this plan). They are verified by (a) the import-resolution check in Tasks 5/6, and (b) the manual/Pi verification checklist in Task 6 — do not add a fake-DOM test here.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/highlights.js frontend/tests/highlights.test.js
git commit -m "$(cat <<'EOF'
feat(highlights): add occurrence-based text anchoring + DOM apply/remove helpers

findNthOccurrence/countOccurrencesBefore are pure and unit-tested. applyHighlight/
applyHighlights/removeHighlightMarks are the DOM mechanics (Text.splitText-based
wrap/unwrap, never Range.surroundContents()) that Tasks 5-6 wire into app.js; they
have no jsdom/browser test environment available in this repo, so they're verified
via the Task 6 manual/Pi checklist instead of a fake DOM test.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `frontend/src/notes.js` — thread `highlights` through `loadWorkspace`/`saveWorkspace`

**Files:**
- Modify: `frontend/src/notes.js`
- Modify: `frontend/tests/notes.test.js`

**Interfaces:**
- Produces: `saveWorkspace({ fetch, storage, courseId, lessonId, notes, chat, highlights = [] }) -> Promise<{ok: true, updatedAt} | {ok: false, error}>` — `highlights` is now threaded into both the PUT body and the optimistic localStorage cache write; defaults to `[]` when the caller omits it (so every existing call site that doesn't pass it yet keeps working unmodified).
- Produces: `loadWorkspace({ fetch, storage, courseId, lessonId })` — unchanged signature; now simply passes through whatever `highlights` the server/cache response contains (no server-shape assumption baked in here, matching how it already handles `notes`/`chat`).
- Consumed later by: Task 5/6 in `frontend/src/app.js` (`seedWorkspace`, `addHighlightFromSelection`, `removeHighlightAt`).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/notes.test.js` (after the existing 4 tests):

```javascript
test("saveWorkspace threads highlights into the PUT body and the cache", async () => {
  const storage = fakeStorage();
  let opts;
  const fetch = async (u, o) => { opts = o; return { ok: true, json: async () => ({ updatedAt: "t3" }) }; };
  const hl = [{ id: "h1", text: "a phrase", occurrence: 0 }];
  await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "n", chat: [], highlights: hl });
  assert.deepEqual(JSON.parse(opts.body).highlights, hl);
  assert.deepEqual(JSON.parse(storage.getItem("ws:c:l1")).highlights, hl);
});

test("saveWorkspace defaults highlights to an empty array when omitted", async () => {
  const storage = fakeStorage();
  let opts;
  const fetch = async (u, o) => { opts = o; return { ok: true, json: async () => ({ updatedAt: "t4" }) }; };
  await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "n", chat: [] });
  assert.deepEqual(JSON.parse(opts.body).highlights, []);
});

test("loadWorkspace passes highlights through from the server response", async () => {
  const storage = fakeStorage();
  const hl = [{ id: "h1", text: "a phrase", occurrence: 0 }];
  const fetch = async () => ({ ok: true, json: async () => ({ notes: "n", chat: [], highlights: hl, updatedAt: "t" }) });
  const ws = await loadWorkspace({ fetch, storage, courseId: "c", lessonId: "l1" });
  assert.deepEqual(ws.highlights, hl);
  assert.deepEqual(JSON.parse(storage.getItem("ws:c:l1")).highlights, hl);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test frontend/tests/notes.test.js`

Expected: `tests 7`, `pass 5`, `fail 2`. `"saveWorkspace threads highlights..."` and `"saveWorkspace defaults highlights..."` fail (`AssertionError: undefined !== [...]` / `undefined !== []`, since `saveWorkspace` doesn't read or send a `highlights` field yet). `"loadWorkspace passes highlights through..."` already passes at this checkpoint — `loadWorkspace` already returns the server response verbatim, so it needs no code change; that's expected and fine.

- [ ] **Step 3: Implement — replace the full contents of `frontend/src/notes.js`**

```javascript
const KEY = (courseId, lessonId) => `ws:${courseId}:${lessonId}`;
const EMPTY = { notes: "", chat: [], highlights: [], updatedAt: null };

function cacheGet(storage, courseId, lessonId) {
  try { return JSON.parse(storage.getItem(KEY(courseId, lessonId))); } catch (e) { return null; }
}
function cacheSet(storage, courseId, lessonId, ws) {
  try { storage.setItem(KEY(courseId, lessonId), JSON.stringify(ws)); } catch (e) {}
}

export async function loadWorkspace({ fetch, storage, courseId, lessonId }) {
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`);
    if (resp.ok) {
      const ws = await resp.json();
      cacheSet(storage, courseId, lessonId, ws);
      return ws;
    }
  } catch (e) {}
  return cacheGet(storage, courseId, lessonId) || { ...EMPTY };
}

export async function saveWorkspace({ fetch, storage, courseId, lessonId, notes, chat, highlights = [] }) {
  // Optimistic: write the local cache first so a failed/offline save never loses text
  // (or a just-created highlight -- see Task 6's addHighlightFromSelection).
  cacheSet(storage, courseId, lessonId, { notes, chat, highlights, updatedAt: new Date().toISOString() });
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, chat, highlights }),
    });
    if (!resp.ok) return { ok: false, error: `save failed (${resp.status})` };
    const body = await resp.json();
    return { ok: true, updatedAt: body.updatedAt };
  } catch (e) {
    return { ok: false, error: "offline" };
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test frontend/tests/notes.test.js`

Expected: `tests 7`, `pass 7`, `fail 0`.

- [ ] **Step 5: Run the full frontend suite to confirm no regressions**

Run: `node --test frontend/tests/*.test.js`

Expected: `tests 322`, `pass 322`, `fail 0` (313 baseline + 6 from Task 3 + 3 new here).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/notes.js frontend/tests/notes.test.js
git commit -m "$(cat <<'EOF'
feat(highlights): thread highlights through loadWorkspace/saveWorkspace

saveWorkspace now writes highlights into both the PUT body and the optimistic
local cache, mirroring exactly how notes/chat are already handled, so an
offline-created highlight is never silently lost.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Selection capture + "Highlight" button + create (`frontend/src/app.js`, `frontend/styles.css`)

This task makes it possible to select prose inside `.prompt`, see a "Highlight" button, tap it, and get the highlight saved and visually applied immediately. It does NOT yet make highlights reappear after a reload, or make tapping a `<mark>` remove it — that's Task 6. This task's own `seedWorkspace` change ensures previously-saved highlights are never silently dropped from local state (and therefore never clobbered on the next save) even before Task 6 lands the re-apply-on-render step.

**Files:**
- Modify: `frontend/src/app.js`
- Modify: `frontend/styles.css`

**Interfaces:**
- Consumes: `countOccurrencesBefore`, `flattenTextNodes`, `applyHighlight` from `frontend/src/highlights.js` (Task 3); `saveWorkspace({..., highlights})` from `frontend/src/notes.js` (Task 4); `newId` from `frontend/src/ids.js` (already imported in `app.js`).
- Produces: `ui.lessonState.ws.highlights` — array field, populated by `seedWorkspace` from `wsData.highlights || []`.
- Produces (module-scoped functions in `app.js`, consumed by Task 6): `promptContainer() -> Element | null`, `hideHighlightBtn() -> void`.
- Produces: CSS class `.highlight-btn`.
- No automated test (DOM-dependent — see the testing-environment note). Verified via the import-resolution check below and the Task 6 manual/Pi checklist (this task's slice: "select text inside `.prompt` → Highlight button appears → tap it → mark appears immediately").

- [ ] **Step 1: Add the `highlights.js` import**

In `frontend/src/app.js`, find (line 30):

```javascript
import { autoGrowTextarea } from "./autogrow.js";
```

Replace with:

```javascript
import { autoGrowTextarea } from "./autogrow.js";
import { countOccurrencesBefore, flattenTextNodes, applyHighlight } from "./highlights.js";
```

- [ ] **Step 2: Seed `highlights` into the workspace state**

Find (around line 1271-1279):

```javascript
  async function seedWorkspace(lesson, lessonState) {
    if (!lesson || lessonState.ws) return; // already seeded for this state
    const prefs = wsPrefs();
    const wsData = await loadWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: lesson.id });
    if (ui.lessonState !== lessonState) return; // navigated away while loading
    lessonState.ws = { open: !!prefs.open, tab: prefs.tab || "notes",
                       notes: wsData.notes || "", chat: wsData.chat || [], pending: false, saveStatus: "" };
    if (ui.screen === "lesson") paintLesson();
  }
```

Replace with:

```javascript
  async function seedWorkspace(lesson, lessonState) {
    if (!lesson || lessonState.ws) return; // already seeded for this state
    const prefs = wsPrefs();
    const wsData = await loadWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: lesson.id });
    if (ui.lessonState !== lessonState) return; // navigated away while loading
    lessonState.ws = { open: !!prefs.open, tab: prefs.tab || "notes",
                       notes: wsData.notes || "", chat: wsData.chat || [], highlights: wsData.highlights || [],
                       pending: false, saveStatus: "" };
    if (ui.screen === "lesson") paintLesson();
  }
```

- [ ] **Step 3: Add the capture/button/create block and register the listener**

Find (around line 196-202):

```javascript
  root.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      submitFeedback();
    }
  });

  // ---- diagnostic (unchanged flow, now lands on the home) ----
```

Replace with:

```javascript
  root.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      submitFeedback();
    }
  });

  // ---- lesson prose highlights: selection capture + "Highlight" button ----
  // Scoped ONLY to the lesson's own prose (.prompt inside #view) -- never the
  // exercise/solution/checks sections or the side chat/notes workspace. Purely
  // visual: nothing here reads or reacts to what's highlighted.
  let highlightBtn = null; // the floating button, created once and repositioned/reused
  function hideHighlightBtn() {
    if (highlightBtn) { highlightBtn.remove(); highlightBtn = null; }
  }
  function promptContainer() {
    const view = root.querySelector("#view");
    return view ? view.querySelector(".prompt") : null;
  }
  function showHighlightBtn(range) {
    if (!highlightBtn) {
      highlightBtn = doc.createElement("button");
      highlightBtn.type = "button";
      highlightBtn.className = "highlight-btn";
      highlightBtn.textContent = "Highlight";
      // Stop the button's own mousedown from collapsing the selection it needs to read.
      highlightBtn.addEventListener("mousedown", (e) => e.preventDefault());
      highlightBtn.addEventListener("click", addHighlightFromSelection);
      doc.body.appendChild(highlightBtn);
    }
    const rect = range.getBoundingClientRect();
    highlightBtn.style.top = `${Math.max(8, rect.top - 40)}px`;
    highlightBtn.style.left = `${rect.left}px`;
  }
  // Fires on every selectionchange -- covers both desktop click-drag and mobile
  // long-press-drag with one listener. Shows the button only when the selection is
  // non-collapsed AND fully contained within .prompt (the scope rule) -- a selection
  // touching the exercise, checks, or side-chat area never shows it.
  function captureSelectionForHighlight() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) { hideHighlightBtn(); return; }
    const container = promptContainer();
    if (!container) { hideHighlightBtn(); return; }
    const range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      hideHighlightBtn();
      return;
    }
    showHighlightBtn(range);
  }
  doc.addEventListener("selectionchange", captureSelectionForHighlight);

  // Tapping the floating button: reads the live selection, computes `occurrence`
  // (which match of the exact selected text this is, counted across the container's
  // flattened text at THIS moment -- the anchoring rule), saves it, and applies the
  // mark immediately.
  function addHighlightFromSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) { hideHighlightBtn(); return; }
    const container = promptContainer();
    if (!container) { hideHighlightBtn(); return; }
    const range = sel.getRangeAt(0);
    const text = sel.toString();
    const { text: fullText, nodes } = flattenTextNodes(container);
    const startEntry = nodes.find((n) => n.node === range.startContainer);
    hideHighlightBtn();
    sel.removeAllRanges();
    if (!text.trim() || !startEntry) return; // can't anchor it -> no-op, never guess
    const ws = ui.lessonState.ws;
    if (!ws) return;
    const startOffset = startEntry.start + range.startOffset;
    const occurrence = countOccurrencesBefore(fullText, text, startOffset);
    const highlight = { id: newId("hl-"), text, occurrence };
    ws.highlights = [...(ws.highlights || []), highlight];
    applyHighlight(container, highlight);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }

  // ---- diagnostic (unchanged flow, now lands on the home) ----
```

- [ ] **Step 4: Add the button's CSS**

In `frontend/styles.css`, find (around line 173-176):

```css
.prompt .box{background:var(--glass-inner); border:1px solid var(--border-field);
  border-radius:10px; padding:11px 13px; margin:0 0 12px; font-size:14px; line-height:1.55; color:var(--read)}

/* Lesson images — real figures resolved by backend/images.py */
```

Replace with:

```css
.prompt .box{background:var(--glass-inner); border:1px solid var(--border-field);
  border-radius:10px; padding:11px 13px; margin:0 0 12px; font-size:14px; line-height:1.55; color:var(--read)}

/* Lesson text highlights — persistent, purely visual (free-form selection inside
   .prompt only; never reads/reacts to what's highlighted). */
.highlight-btn{position:fixed; z-index:50;
  background:var(--grad); color:#fff; border:none; border-radius:999px; cursor:pointer;
  padding:7px 14px; font:600 12.5px/1 var(--ui); box-shadow:var(--sh-cta)}

/* Lesson images — real figures resolved by backend/images.py */
```

- [ ] **Step 5: Import-resolution check (catches typos/syntax errors — does NOT exercise DOM behavior)**

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`

Expected: `imports ok`.

- [ ] **Step 6: Run the full frontend suite to confirm no regressions**

Run: `node --test frontend/tests/*.test.js`

Expected: `tests 322`, `pass 322`, `fail 0` (unchanged from Task 4 — this task adds no new automated test).

- [ ] **Step 7: Manual verification (this task's slice only — the full checklist is in Task 6)**

This cannot be exercised by an automated test (no browser/DOM environment in this repo — see the testing-environment note). After deploying to the Pi (see `docs/DEPLOY.md`) or running the app against a browser some other way:
1. Open any lesson with real prose in `.prompt`.
2. Drag-select a phrase inside the lesson prose. Confirm a "Highlight" button appears near the selection.
3. Drag-select text that starts inside `.prompt` and continues into the exercise/checks area, or select text purely inside the workspace notes/chat panel. Confirm the button does NOT appear.
4. Tap the "Highlight" button. Confirm the selected phrase is immediately marked (visible highlight color) and the selection clears.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "$(cat <<'EOF'
feat(highlights): capture prose selections and create highlights from the Highlight button

Selection capture is scoped to .prompt only (never the exercise/checks/side-chat
areas). Tapping the floating button computes the occurrence index from the live
selection, saves immediately (no debounce, unlike Notes), and applies the mark
right away. DOM-dependent; no automated test here -- see the Task 6 manual/Pi
verification checklist.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Re-apply on render + remove on tap (`frontend/src/app.js`, `frontend/styles.css`)

**Files:**
- Modify: `frontend/src/app.js`
- Modify: `frontend/styles.css`

**Interfaces:**
- Consumes: `applyHighlights`, `removeHighlightMarks` from `frontend/src/highlights.js` (Task 3); `promptContainer()`, `hideHighlightBtn()`, `ui.lessonState.ws.highlights` from Task 5.
- Produces: every `paintLesson()` repaint re-applies all currently-stored highlights to the fresh `.prompt` DOM (mirroring how `hydrateFigures` already runs once per repaint).
- Produces: `removeHighlightAt(mark) -> void` — tapping any `<mark class="highlight">` anywhere in the app removes just that highlight.
- Produces: CSS class `mark.highlight`.
- No automated test (DOM-dependent). Verified via the import-resolution check and the manual/Pi checklist below.

- [ ] **Step 1: Extend the `highlights.js` import**

Find (added in Task 5, near line 31):

```javascript
import { countOccurrencesBefore, flattenTextNodes, applyHighlight } from "./highlights.js";
```

Replace with:

```javascript
import { countOccurrencesBefore, flattenTextNodes, applyHighlight, applyHighlights, removeHighlightMarks } from "./highlights.js";
```

- [ ] **Step 2: Re-apply highlights on every lesson repaint**

Find (around line 1484-1488):

```javascript
  function paintLesson() {
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    hydrateFigures(view, ui.lesson);
```

Replace with:

```javascript
  function paintLesson() {
    hideHighlightBtn(); // the DOM this button points at is about to be rebuilt
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    hydrateFigures(view, ui.lesson);
    const promptEl = view.querySelector(".prompt");
    if (promptEl && ui.lessonState.ws) applyHighlights(promptEl, ui.lessonState.ws.highlights);
```

(The rest of `paintLesson`'s body, below this point, is unchanged.)

- [ ] **Step 3: Wire tap-to-remove into the root click listener, and add `removeHighlightAt`**

First, find (added in Task 5, at the end of `addHighlightFromSelection`):

```javascript
    ws.highlights = [...(ws.highlights || []), highlight];
    applyHighlight(container, highlight);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }
```

Replace with:

```javascript
    ws.highlights = [...(ws.highlights || []), highlight];
    applyHighlight(container, highlight);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }
  // Tapping any <mark> removes just that highlight: drop its id from the stored list,
  // unwrap its mark(s) back into plain text (no re-render needed -- this mutates the
  // live DOM directly), and save immediately (same non-debounced trigger as creation).
  function removeHighlightAt(mark) {
    const container = promptContainer();
    const id = mark.dataset.highlightId;
    const ws = ui.lessonState.ws;
    if (!container || !id || !ws) return;
    ws.highlights = (ws.highlights || []).filter((h) => h.id !== id);
    removeHighlightMarks(container, id);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }
```

Then, find (the single delegated root click listener, around line 155-157):

```javascript
  root.addEventListener("click", (e) => {
    const fbToggle = e.target.closest('[data-action="feedback-toggle"]');
    if (fbToggle) {
```

Replace with:

```javascript
  root.addEventListener("click", (e) => {
    const mark = e.target.closest("mark.highlight");
    if (mark) { removeHighlightAt(mark); return; }
    const fbToggle = e.target.closest('[data-action="feedback-toggle"]');
    if (fbToggle) {
```

- [ ] **Step 4: Add the mark's CSS**

In `frontend/styles.css`, find (added in Task 5):

```css
.highlight-btn{position:fixed; z-index:50;
  background:var(--grad); color:#fff; border:none; border-radius:999px; cursor:pointer;
  padding:7px 14px; font:600 12.5px/1 var(--ui); box-shadow:var(--sh-cta)}

/* Lesson images — real figures resolved by backend/images.py */
```

Replace with:

```css
.highlight-btn{position:fixed; z-index:50;
  background:var(--grad); color:#fff; border:none; border-radius:999px; cursor:pointer;
  padding:7px 14px; font:600 12.5px/1 var(--ui); box-shadow:var(--sh-cta)}
mark.highlight{background:rgba(255,196,64,.45); color:inherit; border-radius:3px; padding:0 1px; cursor:pointer}

/* Lesson images — real figures resolved by backend/images.py */
```

- [ ] **Step 5: Import-resolution check**

Run: `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"`

Expected: `imports ok`.

- [ ] **Step 6: Run the full frontend suite to confirm no regressions**

Run: `node --test frontend/tests/*.test.js`

Expected: `tests 322`, `pass 322`, `fail 0`.

- [ ] **Step 7: Run the full backend suite to confirm no regressions (nothing in this task touches backend, but this is the last task in the plan — confirm the whole repo is green)**

Run: `python3 -m pytest -q`

Expected: `810 passed`.

- [ ] **Step 8: Manual/Pi verification (full checklist — supersedes Task 5's smaller one)**

This cannot be exercised by an automated test (no browser/DOM environment in this repo). After deploying to the Pi (see `docs/DEPLOY.md` for the canonical deploy + restart procedure) and opening the app in a real browser at the Pi's URL:
1. Open a lesson, highlight a phrase (drag-select, tap "Highlight"). Confirm it's marked immediately.
2. Reload the lesson (navigate away and back, or refresh). Confirm the same phrase is still marked in the same place.
3. Highlight a phrase that also appears elsewhere in the same lesson's prose (pick the SECOND occurrence). Reload. Confirm only the occurrence you selected is marked, not the other one.
4. Tap "Rusty on this? Explain it more deeply" to regenerate the lesson. Confirm no error occurs and no highlight appears in the wrong place — some or all highlights may simply no longer appear (expected and correct, since the prose text changed).
5. Tap an existing `<mark>`. Confirm it's immediately unmarked (unwrapped back to plain text) and stays gone after a reload.
6. Go offline (e.g. dev tools network throttling → offline), highlight a phrase, confirm it's still visually marked, then go back online and confirm it persists after the next reload (the save should have synced once connectivity returned, following the same optimistic-cache pattern Notes already relies on).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app.js frontend/styles.css
git commit -m "$(cat <<'EOF'
feat(highlights): re-apply highlights on render and remove them on tap

paintLesson() now re-applies every stored highlight to the fresh .prompt DOM on
every repaint (mirroring hydrateFigures' once-per-repaint pattern), and tapping
any <mark> removes it via the existing delegated root click listener. Completes
the lesson-highlights feature: create, persist across reload, disambiguate
same-text occurrences, tolerate regeneration, and remove -- all purely visual.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```
