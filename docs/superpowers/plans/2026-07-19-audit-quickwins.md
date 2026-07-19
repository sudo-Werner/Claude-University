# Audit Quick-Wins Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three approved sweep fixes: Arcade play counts toward the dashboard streak and Recent Activity; Arcade round results list which lessons the misses came from (tappable); cached lessons open without a skeleton flash.

**Architecture:** Task 1 is backend (`stats.py` event lists + `recent_activity` payload surfacing) plus one frontend view branch. Task 2 is frontend-only (`arcade.js` result renderer + `app.js` title fetch and tap-through). Task 3 is a surgical `app.js` change (delay the skeleton paint behind the existing seq/screen guards). Spec: `docs/superpowers/specs/2026-07-19-audit-quickwins-design.md`.

**Tech Stack:** Flask + SQLite (pytest), vanilla ES modules (node --test; NO DOM/jsdom — app.js wiring is verified by import-check + live Pi testing, never by fake DOM tests).

## Global Constraints

- No new dependencies. No emojis anywhere in UI copy.
- The events ledger is client-writable: any read of `quiz_round` payload fields must tolerate missing/malformed values (render safely, never crash).
- `frontend/src/app.js` has no unit tests in this repo — do NOT invent DOM tests for it; the verification for app.js changes is `node -e "import('./frontend/src/app.js').then(() => console.log('imports ok'))"` (run from repo root: `cd frontend && node -e "import('./src/app.js').then(() => console.log('imports ok'))"`).
- Copy style: match surrounding code's comment density and idiom.

---

### Task 1: Arcade rounds count toward streak + Recent Activity

**Files:**
- Modify: `backend/stats.py` (STUDY_EVENTS line 9-10, ACTIVITY_EVENTS line 14-15, `recent_activity` entry-building ~line 95-106)
- Modify: `frontend/src/views/activity.js` (`entryHTML`, add a `quiz_round` branch before the generic fallback)
- Test: `tests/test_stats.py`, `frontend/tests/activity.test.js`

**Interfaces:**
- Consumes: `quiz_round` events written by `backend/quiz.py:submit_results` with payload `{"format": str, "score": int, "total": int, "missed": {...}}`, `course_id` set, `topic_id` = round id (NOT a lesson id).
- Produces: activity entries `{type: "quiz_round", courseTitle, score?: int, total?: int}` — raw counts, unlike `exam_result`'s 0-1 fraction. `lessonTitle` stays None (round id resolves to nothing — that is correct).

- [ ] **Step 1: Write the failing backend tests** — append to `tests/test_stats.py`, mirroring the existing `_ev`/`_write_course` fixtures already in that file:

```python
def test_streak_counts_an_arcade_only_day(conn):
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T09:00:00+00:00", topic_id="r-abc123")])
    assert stats.streak_days(conn, today=TODAY) == 1


def test_activity_includes_quiz_round_with_score(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T10:00:00+00:00", topic_id="r-abc123")])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e1'",
        (json.dumps({"format": "rapid_fire", "score": 7, "total": 8, "missed": {}}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "quiz_round"
    assert out[0]["courseTitle"] == "Machine Learning"
    assert out[0]["lessonTitle"] is None
    assert out[0]["score"] == 7 and out[0]["total"] == 8


def test_activity_quiz_round_tolerates_malformed_payload(conn, tmp_path):
    content = _write_course(tmp_path)
    events.insert_events(conn, [
        _ev(1, "quiz_round", "2026-07-15T10:00:00+00:00", topic_id="r-abc123")])
    conn.execute(
        "UPDATE events SET payload = ? WHERE client_event_id = 'e1'",
        (json.dumps({"score": "seven", "total": 0}),),
    )
    conn.commit()
    out = stats.recent_activity(conn, content, limit=10)
    assert out[0]["type"] == "quiz_round"
    assert "score" not in out[0] or out[0]["score"] is None
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_stats.py -q`
Expected: the three new tests FAIL (quiz_round filtered out of both queries today).

- [ ] **Step 3: Implement `backend/stats.py`**

Add `"quiz_round"` to the end of BOTH tuples (update each list's leading comment to mention Arcade rounds). Then in `recent_activity`, after the existing `exam_result/remediation_started/capstone_result` block, add:

```python
        if r["event_type"] == "quiz_round":
            score, total = payload.get("score"), payload.get("total")
            if (isinstance(score, int) and not isinstance(score, bool)
                    and isinstance(total, int) and not isinstance(total, bool)
                    and total > 0):
                entry["score"] = score
                entry["total"] = total
```

(Do NOT reuse the exam block — exam scores are 0-1 fractions; these are raw counts. The isinstance guards mirror `quiz.py`'s `_quiz_round_events` posture: a forged row renders without a score, never crashes.)

- [ ] **Step 4: Run the backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (810 + 3 new).

- [ ] **Step 5: Write the failing frontend test** — append to `frontend/tests/activity.test.js` (uses the existing `at`/`NOW` helpers at the top of that file):

```javascript
test("activity renders an Arcade round with its score, and omits a malformed score", () => {
  const html = activityHTML([
    { occurredAt: at(0), type: "quiz_round", courseTitle: "ML", lessonTitle: null, quality: null, score: 7, total: 8 },
    { occurredAt: at(0), type: "quiz_round", courseTitle: "ML", lessonTitle: null, quality: null, score: "x", total: 0 },
  ], { now: NOW });
  assert.match(html, /Arcade round/);
  assert.match(html, /7\/8/);
  assert.ok(!html.includes("x/0"));
  assert.ok(!html.includes("undefined"));
});
```

- [ ] **Step 6: Run it to confirm it fails** — `cd frontend && node --test tests/activity.test.js` → FAIL.

- [ ] **Step 7: Implement the `quiz_round` branch in `frontend/src/views/activity.js`** — in `entryHTML`, after the `capstone_result` branch and before the generic verb-based return:

```javascript
  if (e.type === "quiz_round") {
    const hasScore = Number.isInteger(e.score) && Number.isInteger(e.total) && e.total > 0;
    return `<div class="act-entry"><span class="act-time">${when}</span>` +
      `<span class="act-text"><b>Arcade round</b> ` +
      `<span class="act-course">${esc(e.courseTitle || "")}</span>` +
      (hasScore ? `<span class="act-quality">${e.score}/${e.total}</span>` : "") +
      `</span></div>`;
  }
```

- [ ] **Step 8: Run the frontend suite** — `cd frontend && node --test` → all pass.

- [ ] **Step 9: Commit**

```bash
git add backend/stats.py frontend/src/views/activity.js tests/test_stats.py frontend/tests/activity.test.js
git commit -m "feat(arcade): count Arcade rounds toward the dashboard streak and Recent Activity"
```

---

### Task 2: Arcade result lists missed lessons as tappable review chips

**Files:**
- Modify: `frontend/src/views/arcade.js` (`arcadeResultHTML`, line 268)
- Modify: `frontend/src/app.js` (`finishRound` ~line 1163, `paintArcadePlay` result branch ~line 937-948; two new functions near `saveRoundResult`)
- Test: `frontend/tests/arcade.test.js`

**Interfaces:**
- Consumes: `playState.missed` = `{lessonId: missCount}` (built at app.js:1112/1152); `loadCourse({fetch, courseId})` from `./courses.js` (already imported in app.js:7; returns the manifest object or `null` on non-OK); `refreshSummary()`/`openLesson(lessonId)`/`showHome()` in app.js.
- Produces: `arcadeResultHTML(playState, lessonTitles = {})` — second param optional; existing caller/tests that pass one arg keep working.

- [ ] **Step 1: Write the failing view tests** — append to `frontend/tests/arcade.test.js`:

```javascript
test("arcadeResultHTML lists missed lessons sorted by miss count, titles escaped", () => {
  const html = arcadeResultHTML(
    { score: 6, total: 8, missed: { "c1-l2": 1, "c1-l5": 3 } },
    { "c1-l2": "Neurons <fast>", "c1-l5": "Synapses" });
  assert.match(html, /Review what you missed/);
  const iSyn = html.indexOf("Synapses");
  const iNeu = html.indexOf("Neurons &lt;fast&gt;");
  assert.ok(iSyn !== -1 && iNeu !== -1 && iSyn < iNeu);
  assert.ok(html.includes('data-lesson="c1-l5"'));
  assert.match(html, /missed 3/);
});

test("arcadeResultHTML falls back to the lesson id when no title is known", () => {
  const html = arcadeResultHTML({ score: 1, total: 2, missed: { "c1-l9": 1 } }, {});
  assert.ok(html.includes("c1-l9"));
});

test("arcadeResultHTML shows no missed section on a perfect round or missing map", () => {
  assert.ok(!arcadeResultHTML({ score: 8, total: 8, missed: {} }).includes("missed"));
  assert.ok(!arcadeResultHTML({ score: 6, total: 8 }).includes("missed"));
});
```

- [ ] **Step 2: Run to confirm they fail** — `cd frontend && node --test tests/arcade.test.js` → new tests FAIL.

- [ ] **Step 3: Implement `arcadeResultHTML`** — replace the existing function body:

```javascript
// End-of-round card. `lessonTitles` maps lesson id -> title for the missed-lesson
// chips (fetched after the round ends — the Arcade is a global tab with no course
// manifest loaded); an unknown id falls back to the raw id rather than hiding the chip.
export function arcadeResultHTML(playState, lessonTitles = {}) {
  const pct = playState.total ? Math.round((playState.score / playState.total) * 100) : 0;
  const chips = Object.entries(playState.missed || {})
    .filter(([, n]) => Number.isInteger(n) && n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([id, n]) =>
      `<div class="weak-spot"><button class="weak-lesson" data-lesson="${esc(id)}">` +
      `${esc(lessonTitles[id] || id)} — missed ${n}${n > 1 ? " times" : " time"}</button></div>`)
    .join("");
  return `
    <div class="arcade-result card">
      <div class="eyebrow">ROUND COMPLETE</div>
      <h1 class="session-topic">${pct}%</h1>
      <div class="arcade-score-note">${playState.score} / ${playState.total} correct</div>` +
    (chips ? `<h2 class="arcade-missed-head">Review what you missed</h2>${chips}` : "") + `
      <button class="btn-primary" data-action="arcade-play-again">Play again</button>
      <button class="btn-secondary" data-action="arcade-back">Back to Arcade</button>
    </div>`;
}
```

NOTE: the test in Step 1 matches `/missed 3/`; the copy "missed 3 times" satisfies it. Adjust nothing else — the `.weak-spot`/`.weak-lesson` classes are the exam screen's existing styled idiom.

- [ ] **Step 4: Run the frontend suite** — `cd frontend && node --test` → all pass (including the pre-existing `arcadeResultHTML shows the rounded percentage and score` test, which passes one argument — the default `= {}` keeps it green).

- [ ] **Step 5: Wire app.js.** Three edits:

(a) In `finishRound` (after `paintArcadePlay(); await saveRoundResult(st);` — add the title kick BEFORE `await saveRoundResult(st)` so the fetches overlap):

```javascript
    if (Object.keys(st.missed).length) loadMissedTitles(st);
    paintArcadePlay();
    await saveRoundResult(st);
```

(b) New functions next to `saveRoundResult`:

```javascript
  // Titles for the result screen's missed-lesson chips. Fail-open: the score renders
  // immediately with raw-id chips; titles repaint when (if) the manifest arrives.
  async function loadMissedTitles(st) {
    const course = await loadCourse({ fetch, courseId: ui.arcadeCourseId });
    if (ui.quizPlay !== st || ui.screen !== "arcade-play") return; // navigated away mid-fetch
    if (!course || course.error) return;
    const titles = {};
    (course.modules || []).forEach((m) => (m.lessons || []).forEach((l) => { titles[l.id] = l.title; }));
    st.lessonTitles = titles;
    if (st.phase === "result") paintArcadePlay();
  }

  // Chip tap: enter the course's context first (the Arcade is course-less), then open
  // the lesson so Prev/Next/curriculum all work. Mirrors openCourse's manifest guard.
  async function openMissedLesson(lessonId) {
    ui.courseId = ui.arcadeCourseId;
    await refreshSummary();
    if (!ui.manifest) { showHome(); return; }
    openLesson(lessonId);
  }
```

(c) In `paintArcadePlay`'s result branch: change the innerHTML line to
`view.innerHTML = arcadeResultHTML(st, st.lessonTitles || {}) + saveNotice;`
and add, next to the existing play-again/back listeners:

```javascript
      view.querySelectorAll("[data-lesson]").forEach((b) => {
        b.addEventListener("click", () => openMissedLesson(b.getAttribute("data-lesson")));
      });
```

- [ ] **Step 6: Import check + full suite** — `cd frontend && node -e "import('./src/app.js').then(() => console.log('imports ok'))" && node --test` → imports ok, all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/arcade.js frontend/src/app.js frontend/tests/arcade.test.js
git commit -m "feat(arcade): tappable missed-lesson review chips on the round result"
```

---

### Task 3: Cache-first lesson open — delay the skeleton behind the existing guards

**Files:**
- Modify: `frontend/src/app.js` (`openLesson`, lines 1215-1225 only)

**Interfaces:**
- Consumes: the existing `ui.loadSeq`/`ui.screen === "lesson-loading"` guard pair — every mid-flight navigation guard in `openLesson`/`paintActivate`/`finishOpenLesson` keys off them and MUST remain untouched.
- Produces: no interface change. `continueToLesson`'s immediate skeleton (always precedes a 30-90s generation) is deliberately NOT changed.

- [ ] **Step 1: Make the change.** In `openLesson`, replace:

```javascript
    ui.screen = "lesson-loading";
    const view = root.querySelector("#view");
    if (view) startLoading(view, "lesson", LESSON_STAGES);
```

with:

```javascript
    ui.screen = "lesson-loading";
    // Cache-first: nearly every open is an already-generated lesson that resolves in a
    // few hundred ms, and painting the skeleton immediately made every open flash it.
    // Delay the paint; the re-check makes a fast open (or navigating away) skip it, and
    // the slow paths (generation, slow Pi) still get the skeleton after 200ms.
    window.setTimeout(() => {
      if (ui.screen !== "lesson-loading" || ui.loadSeq !== seq) return;
      const v = root.querySelector("#view");
      if (v) startLoading(v, "lesson", LESSON_STAGES);
    }, 200);
```

(The `seq` const is declared just above — this callback closes over it exactly like the existing guards. `paintActivate` sets `ui.screen = "activate"` before painting, so a pending timer self-noops on the activation path too. No timer handle is kept: a stale callback is a guarded no-op, same idiom as `pollArcadeRound`'s seq checks.)

- [ ] **Step 2: Import check + full frontend suite**

Run: `cd frontend && node -e "import('./src/app.js').then(() => console.log('imports ok'))" && node --test`
Expected: imports ok; 325+ tests pass (no test touches this code — DOM constraint).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app.js
git commit -m "feat(lesson): cache-first open — skeleton only paints if the load takes over 200ms"
```

---

## Live Pi verification checklist (post-merge, by the orchestrator)

1. Open a cached lesson from the curriculum: no skeleton flash (previous screen holds ~100-300ms, then the lesson paints).
2. Open an ungenerated lesson: activation card, then skeleton during generation — unchanged.
3. Play an Arcade round, miss at least one question on purpose: result screen shows "Review what you missed" chips with real lesson titles, sorted; tap one → lands in that lesson with working Prev/Next; the dashboard streak and Activity screen show the round (e.g. "Arcade round 5/8 · Course").
4. Perfect round: no missed section.
5. Clean up any synthetic events/rounds created while testing.
