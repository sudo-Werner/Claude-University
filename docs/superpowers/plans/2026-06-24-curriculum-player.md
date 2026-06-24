# Curriculum & Lesson-Player UX (Slice 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a curriculum accordion (modules→lessons with completion ✓, mastery badge, per-module
progress, jump-to-any-lesson) and a lesson-player nav bar (Curriculum · Prev · Next), adapted to the
app's narrow warm-glass column.

**Architecture:** Pure frontend. Reuses the existing `GET /api/courses/<id>` payload (manifest +
Slice-6 `mastery` map). A lesson is **done** iff its id is a key in `mastery`; its **badge** is the
level. No backend/API/schema change.

**Tech Stack:** Plain ES modules, no framework. Tests: `cd frontend && node --test`.

## Global Constraints

- **No backend change.** Completion is read from the `mastery` map keys; structure from
  `manifest.modules`; "X of Y" from the lesson JSON `step`/`totalSteps`.
- Mastery level keys (lowercase) and labels: `attempted→Attempted, familiar→Familiar,
  proficient→Proficient, mastered→Mastered` — identical to Slice 6.
- Warm-glass theme: reuse existing CSS variables (`--glass-*`, `--text-*`, `--purple`, radius vars)
  and existing patterns (`.eyebrow`, `.stat`, the Slice-6 `.mastery`/`.m-item` chips).
- App.js wiring is browser-verified (the project does not unit-test app.js). Only the pure view
  functions get unit tests.
- All learner-/LLM-derived strings rendered through an `esc()` helper (titles come from the
  manifest; escape them).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Curriculum view + lesson player-nav rendering (pure, TDD)

**Files:**
- Create: `frontend/src/views/curriculum.js`
- Modify: `frontend/src/views/lesson.js` (`lessonHTML` gains a player-nav row)
- Test: `frontend/tests/views.test.js` (add cases)

**Interfaces:**
- Produces: `curriculumHTML(manifest, mastery, currentId)->string`,
  `lessonStatus(lessonId, mastery, currentId)->"done"|"current"|"todo"`,
  `moduleProgress(module, mastery)->{done,total}` (all exported from curriculum.js).
- `lessonHTML(lesson, state, nav)` — `nav` is `{hasPrev, hasNext}` (default `{}`); renders a
  player-nav row with Curriculum / Prev / Next; Prev disabled unless `nav.hasPrev`, Next disabled
  unless `nav.hasNext`.

- [ ] **Step 1: Write the failing tests** (append to `frontend/tests/views.test.js`, matching its
  existing import + `node:test`/`assert` style; add imports for the new functions)

```javascript
import { curriculumHTML, lessonStatus, moduleProgress } from "../src/views/curriculum.js";

const SAMPLE_MANIFEST = {
  id: "demo", title: "Demo Course", subtitle: "s",
  modules: [
    { id: "m1", title: "Basics", lessons: [
      { id: "demo-l1", title: "Lesson One" }, { id: "demo-l2", title: "Lesson Two" } ] },
    { id: "m2", title: "Advanced", lessons: [ { id: "demo-l3", title: "Lesson Three" } ] },
  ],
};
const SAMPLE_MASTERY = { "demo-l1": "proficient" };  // l1 done, rest not

test("lessonStatus reflects done / current / todo", () => {
  assert.equal(lessonStatus("demo-l1", SAMPLE_MASTERY, "demo-l2"), "done");
  assert.equal(lessonStatus("demo-l2", SAMPLE_MASTERY, "demo-l2"), "current");
  assert.equal(lessonStatus("demo-l3", SAMPLE_MASTERY, "demo-l2"), "todo");
});

test("moduleProgress counts completed lessons in a module", () => {
  assert.deepEqual(moduleProgress(SAMPLE_MANIFEST.modules[0], SAMPLE_MASTERY), { done: 1, total: 2 });
  assert.deepEqual(moduleProgress(SAMPLE_MANIFEST.modules[1], SAMPLE_MASTERY), { done: 0, total: 1 });
});

test("curriculumHTML renders modules, lessons, progress, badge and hooks", () => {
  const html = curriculumHTML(SAMPLE_MANIFEST, SAMPLE_MASTERY, "demo-l2");
  assert.match(html, /Basics/);
  assert.match(html, /Advanced/);
  assert.match(html, /Lesson One/);
  assert.match(html, /data-lesson="demo-l1"/);
  assert.match(html, /data-lesson="demo-l3"/);
  assert.match(html, /1\/2/);            // module-one progress
  assert.match(html, /Proficient/);      // badge for the completed lesson
  assert.match(html, /1 of 3 lessons/);  // overall header
});

test("curriculumHTML tolerates missing mastery", () => {
  const html = curriculumHTML(SAMPLE_MANIFEST, undefined, null);
  assert.match(html, /0 of 3 lessons/);
  assert.match(html, /data-lesson="demo-l1"/);
});
```

And for the lesson nav (same file; `lessonHTML` is already imported there — confirm the existing
import and the sample lesson object the file uses; reuse that sample):

```javascript
test("lessonHTML renders player nav with Prev/Next enabled per nav flags", () => {
  // reuse the file's existing SAMPLE_LESSON + a minimal state with solutionRevealed:false
  const state = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
  const mid = lessonHTML(SAMPLE_LESSON, state, { hasPrev: true, hasNext: true });
  assert.match(mid, /data-action="curriculum"/);
  assert.match(mid, /data-action="prev-lesson"/);
  assert.match(mid, /data-action="next-lesson"/);
  assert.doesNotMatch(mid, /data-action="prev-lesson"[^>]*disabled/);

  const first = lessonHTML(SAMPLE_LESSON, state, { hasPrev: false, hasNext: true });
  assert.match(first, /data-action="prev-lesson"[^>]*disabled/);
});
```

If the existing `views.test.js` lesson tests call `lessonHTML(lesson, state)` with two args, they
must keep working — `nav` defaults to `{}` so Prev/Next render disabled and nothing else changes.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd frontend && node --test tests/views.test.js`
Expected: FAIL (curriculum.js missing; nav hooks absent).

- [ ] **Step 3: Create `frontend/src/views/curriculum.js`**

```javascript
const LABELS = { attempted: "Attempted", familiar: "Familiar", proficient: "Proficient", mastered: "Mastered" };

const CHECK = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L19 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function flatten(manifest) {
  const out = [];
  (manifest.modules || []).forEach((m) => (m.lessons || []).forEach((l) => out.push(l)));
  return out;
}

export function lessonStatus(lessonId, mastery, currentId) {
  if (mastery && mastery[lessonId]) return "done";
  if (lessonId === currentId) return "current";
  return "todo";
}

export function moduleProgress(module, mastery) {
  const lessons = module.lessons || [];
  const done = lessons.filter((l) => mastery && mastery[l.id]).length;
  return { done, total: lessons.length };
}

function lessonRow(lesson, mastery, currentId) {
  const status = lessonStatus(lesson.id, mastery, currentId);
  const level = mastery && mastery[lesson.id];
  const badge = level ? `<span class="c-badge ${level}">${LABELS[level]}</span>` : "";
  const inner = status === "done" ? CHECK : "";
  return (
    `<button class="c-lesson ${status}" data-lesson="${esc(lesson.id)}">` +
    `<span class="c-mark ${status}">${inner}</span>` +
    `<span class="c-ltitle">${esc(lesson.title)}</span>${badge}</button>`
  );
}

function moduleBlock(module, mastery, currentId) {
  const p = moduleProgress(module, mastery);
  const rows = (module.lessons || []).map((l) => lessonRow(l, mastery, currentId)).join("");
  return (
    `<section class="c-module">` +
    `<div class="c-mhead"><span class="c-mtitle">${esc(module.title)}</span>` +
    `<span class="c-mprog">${p.done}/${p.total}</span></div>` +
    `<div class="c-lessons">${rows}</div></section>`
  );
}

export function curriculumHTML(manifest, mastery, currentId) {
  const m = mastery || {};
  const flat = flatten(manifest);
  const done = flat.filter((l) => m[l.id]).length;
  const modules = (manifest.modules || []).map((mod) => moduleBlock(mod, m, currentId)).join("");
  return (
    `<div class="curriculum">` +
    `<div class="greeting"><h1>${esc(manifest.title)}</h1>` +
    `<span>${done} of ${flat.length} lessons</span></div>${modules}</div>`
  );
}
```

- [ ] **Step 4: Add the player-nav row to `frontend/src/views/lesson.js`**

Change the signature to `export function lessonHTML(lesson, state, nav = {})` and insert a player-nav
row immediately AFTER the steps/steprow `</div>` (the block that closes at the line before
`<section class="card lesson">`). Add a `LIST` icon constant near the other icon constants:

```javascript
const LIST = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
```

Insert this between the `</div>` that closes the steps wrapper and `<section class="card lesson">`:

```javascript
      <div class="player-nav">
        <button class="pn-btn pn-curric" data-action="curriculum">${LIST}<span>Curriculum</span></button>
        <div class="pn-move">
          <button class="pn-btn" data-action="prev-lesson" aria-label="Previous lesson"${nav.hasPrev ? "" : " disabled"}>‹</button>
          <button class="pn-btn" data-action="next-lesson" aria-label="Next lesson"${nav.hasNext ? "" : " disabled"}>›</button>
        </div>
      </div>
```

Do not change any other lesson markup or the existing `.nav`/rate block.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && node --test tests/views.test.js` then `cd frontend && node --test`
Expected: PASS (all suites, including the new cases and the unchanged lesson tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/curriculum.js frontend/src/views/lesson.js frontend/tests/views.test.js
git commit -m "feat(frontend): curriculum accordion view + lesson player-nav rendering"
```

---

### Task 2: App wiring + styles (curriculum screen, jump-to-lesson, player nav)

**Files:**
- Modify: `frontend/src/app.js`, `frontend/src/views/dashboard.js`, `frontend/styles.css`
- (No new tests — browser-verified per the project's app.js convention.)

**Interfaces:**
- Consumes: `curriculumHTML` (Task 1); `lessonHTML(lesson, state, nav)` (Task 1).
- Produces: a `curriculum` screen; `openLesson(lessonId)`; Prev/Next/Curriculum behavior.

- [ ] **Step 1: Read** `frontend/src/app.js` (esp. `startLesson` ~140, `showLesson`/`paintLesson`
  ~154-212, `showCourse`/`paintCourse` ~125-137, `refreshSummary` ~93) and `dashboard.js`.

- [ ] **Step 2: Import the curriculum view** in app.js:

```javascript
import { curriculumHTML } from "./views/curriculum.js";
```

- [ ] **Step 3: Generalize `startLesson` into `openLesson(lessonId)`** — refactor the existing
  `startLesson` body so it takes an explicit `lessonId`, and keep `startLesson` as a thin wrapper:

```javascript
  async function openLesson(lessonId) {
    if (!lessonId) return;
    ui.reviewQueue = [];
    const view = root.querySelector("#view");
    if (view) view.innerHTML = `<div class="card lesson loading">Preparing your lesson…</div>`;
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId });
    if (!ui.lesson) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: lessonId });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  function startLesson() {
    const next = ui.summary && ui.summary.nextLesson;
    if (next) openLesson(next.id);
  }
```

- [ ] **Step 4: Add `flattenManifest` + `currentLessonId` + Prev/Next helpers** (near
  `sessionData`):

```javascript
  function flatLessons() {
    const out = [];
    const mods = (ui.manifest && ui.manifest.modules) || [];
    mods.forEach((m) => (m.lessons || []).forEach((l) => out.push(l)));
    return out;
  }

  function currentLessonId() {
    if (ui.lesson) return ui.lesson.id;
    return ui.summary && ui.summary.nextLesson ? ui.summary.nextLesson.id : null;
  }

  function adjacentLesson(offset) {
    const flat = flatLessons();
    const i = flat.findIndex((l) => ui.lesson && l.id === ui.lesson.id);
    if (i < 0) return null;
    const j = i + offset;
    return j >= 0 && j < flat.length ? flat[j] : null;
  }
```

- [ ] **Step 5: Add the curriculum screen**:

```javascript
  function showCurriculum() {
    ui.screen = "curriculum";
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintCurriculum();
  }

  function paintCurriculum() {
    const view = root.querySelector("#view");
    view.innerHTML = curriculumHTML(ui.manifest, (ui.manifest && ui.manifest.mastery) || {}, currentLessonId());
    view.querySelectorAll("[data-lesson]").forEach((row) => {
      row.addEventListener("click", () => openLesson(row.getAttribute("data-lesson")));
    });
  }
```

- [ ] **Step 6: Wire the dashboard "View all lessons" button.** In `dashboard.js`, add a button
  with `data-action="curriculum"` in the session card (e.g. directly under the Start session button
  or beneath the stat row — a full-width secondary button labelled "View all lessons"). Then in
  app.js `paintCourse`, after binding start-session/review, add:

```javascript
    const cur = view.querySelector('[data-action="curriculum"]');
    if (cur) cur.addEventListener("click", showCurriculum);
```

- [ ] **Step 7: Pass nav flags into the lesson and bind the player nav.** In `paintLesson`, change
  the render call to compute nav and pass it:

```javascript
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
```

  and after the existing bindings in `paintLesson`, add:

```javascript
    const curBtn = view.querySelector('[data-action="curriculum"]');
    if (curBtn) curBtn.addEventListener("click", showCurriculum);
    const prevBtn = view.querySelector('[data-action="prev-lesson"]');
    if (prevBtn) prevBtn.addEventListener("click", () => { const a = adjacentLesson(-1); if (a) openLesson(a.id); });
    const nextBtn = view.querySelector('[data-action="next-lesson"]');
    if (nextBtn) nextBtn.addEventListener("click", () => { const a = adjacentLesson(1); if (a) openLesson(a.id); });
```

- [ ] **Step 8: Add CSS** to `frontend/styles.css` (warm-glass theme) for:
  - `.curriculum`, `.c-module`, `.c-mhead`, `.c-mtitle`, `.c-mprog`, `.c-lessons`,
    `.c-lesson` (a full-width row button: marker + title + optional badge; hover; `.done`/`.current`
    states), `.c-mark` (small circle; `.done` filled w/ check in green-ish, `.current` purple ring),
    `.c-badge` (reuse the Slice-6 `.m-item`/mastery chip look; small).
  - `.player-nav` (a flex row: Curriculum left, `.pn-move` Prev/Next right), `.pn-btn` (small glass
    button; `:disabled` muted), reusing `.btn-back`/glass patterns.
  Keep it minimal and consistent; reuse existing variables. Do not restructure existing rules.

- [ ] **Step 9: Sanity-run frontend tests** (Task 1's view tests still pass; app.js untested):

Run: `cd frontend && node --test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/app.js frontend/src/views/dashboard.js frontend/styles.css
git commit -m "feat(frontend): curriculum screen, jump-to-lesson, and lesson player nav"
```

---

### Task 3: End-to-end verification + deploy

**What / Why / Verify:** Prove the curriculum + player navigation works in a real browser, then ship.

**Files:** none (verification + deploy).

- [ ] **Step 1: Full local sweep** — `.venv/bin/pytest -q` PASS; `cd frontend && node --test` PASS.

- [ ] **Step 2: Confirm Pi Claude login + load** (generation needed to make lessons/mastery):
```
mcp__pi-ssh__exec: env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN HOME=/home/werner PATH=/home/werner/.local/bin:$PATH timeout 60 claude -p 'Reply with ONLY {"ok": true}' --output-format json --model claude-sonnet-4-6
```
Expected `is_error:false`; also `uptime`.

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
  1. Create a 2-module course (e.g. "tiny 2-module Python course: module 1 variables (1 lesson),
     module 2 loops (1 lesson)").
  2. From the course dashboard, click **View all lessons** → confirm the curriculum accordion shows
     both modules, their lessons, per-module progress (0/1 each), and "0 of 2 lessons".
  3. Tap the **second module's** lesson directly (a non-next lesson) → confirm it opens and generates.
  4. In the player, use **Curriculum** to return, and **Prev/Next** to move between lessons; confirm
     Prev is disabled on the first lesson and Next on the last.
  5. Complete a lesson (answer → reveal → checks → rate). Reopen the curriculum → confirm that
     lesson now shows a ✓ and a mastery badge, and its module progress incremented.
  6. Remove the throwaway course on the Pi; confirm the university is empty.

- [ ] **Step 5: Confirm service active + enabled.**

---

## Self-Review

**1. Spec coverage:** curriculum accordion + badges + per-module progress (T1 view, T2 screen);
jump-to-any-lesson (T2 `openLesson`); player nav Curriculum/Prev/Next + X-of-Y (T1 lesson nav, T2
wiring); no backend change (completion from mastery keys). e2e (T3). All spec sections map to tasks.

**2. Placeholder scan:** No TBD. View code is complete; wiring steps give exact functions/snippets;
CSS step lists the exact classes to style with the theme variables to reuse.

**3. Type consistency:** mastery level keys/labels match Slice 6 (curriculum.js `LABELS`). `nav`
object `{hasPrev,hasNext}` is produced in app.js `paintLesson` and consumed by `lessonHTML` (T1).
`data-lesson` / `data-action="curriculum|prev-lesson|next-lesson"` hooks emitted by the views (T1)
are exactly what app.js binds (T2). `openLesson(lessonId)` is the single entry both Start-session and
curriculum taps use.
