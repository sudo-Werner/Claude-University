# Claude University — Styled Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **For Werner (plain-language review):** Each task starts with a **What this is / Why / What you can verify** block in plain English — review *those* and the "Decisions for you" section. The code beneath is for whoever builds it.

**Goal:** Replace Plan 2's bare placeholder page with the real, styled Dashboard and Lesson screens from your Claude design — built as plain ES-module views wired to the live event pipeline, running on the Pi.

**Architecture:** Each screen is a pure function that takes a plain data object and returns an HTML string (so its content is unit-testable in Node). `app.js` drops that HTML into the page and attaches the click/typing handlers, which log events through the Plan 2 pipeline. Interaction rules with real logic (the 90-minute timer's phases, the "answer-before-solution" gate) live in their own pure, tested modules. The Pi serves it all.

**Tech Stack:** Plain HTML + ES modules (no framework, no build step), the design's `styles.css`, Node's built-in test runner (`node --test`), Playwright for the real-browser check, Flask static serving (Plan 1).

## Global Constraints

- No frontend framework, no build step, no bundler — plain ES modules and one stylesheet.
- The look is fixed by the design: copy `content/design/reference/styles.css` verbatim as the stylesheet; reuse its class names exactly (`.card`, `.opt`, `.btn-primary`, `.hint`, `.reveal`, `.solution`, etc.). Do not invent new visual styles where a design class exists.
- Every meaningful interaction logs an event through the existing `buildEvent`/`appendEvent` pipeline (Plan 2) — the event log stays the single source of truth.
- View modules are pure `…HTML(state) -> string` functions (Node-testable); `app.js` owns all DOM mutation and event wiring (browser-verified).
- Content shown here is **seed/sample data** (one hard-coded lesson + dashboard numbers). Real content, FSRS scheduling, mastery, and adaptive routing are later plans — out of scope here.
- Served over plain HTTP via Tailscale (insecure context): no secure-context-only browser APIs. `backdrop-filter` blur is fine over HTTP.
- Single user (Werner). API + page are same-origin (served by the Pi).
- Commit messages end with the trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## Plan sequence

This is **Plan 3 of 4** (sliced: this plan is *styled screens only*). It depends on Plan 1's API and Plan 2's pipeline (`buildEvent`, `appendEvent`, `flush`, `getSessionId`, `loadProfile`, `saveProfile`, `DIAGNOSTIC`, `buildProfile`). It deliberately leaves FSRS, mastery, real content authoring, and adaptive routing to later plans — those become Plans 5+. What this delivers: a real, clickable, good-looking app on the Pi whose every interaction is logged.

## Decisions for you (review these, not the code)

- **What's real vs. seeded:** the *look* and the *interactions* are real (tabs switch, the timer runs and advances through its phases, the hint and solution gates work, typing is captured, clicks are logged). The *content* is a single hard-coded sample (the backprop exercise from your screenshot) and the dashboard numbers are placeholders. Real lessons come in a later plan.
- **The diagnostic gets styled too.** Your design didn't include a diagnostic screen, so I render your six questions using the design's own option-row component (`.opt`). It's the first thing you see on a fresh browser; after you complete it once, you land on the Dashboard.
- **The 90-minute timer actually runs.** Pressing "Start session" begins a real countdown that fills the warm-up → peak → cool-down bar and updates the clock. It's a visual focus aid; it doesn't yet gate or schedule anything.
- **"Reviews due", "course progress", "streak" are seeded numbers** matching the screenshot — they'll be driven by real event data once mechanics land.

## File Structure

```
frontend/
  platform.html          # modify: link the stylesheet, keep the module bootstrap
  styles.css             # NEW: copied verbatim from content/design/reference/styles.css (+ a few diagnostic rules)
  src/
    timer.js             # NEW: pure 90-min phase maths (which phase, fill %, clock text)
    reveal.js            # NEW: pure answer-before-solution gate + hint toggle logic
    seed.js              # NEW: the sample dashboard data + sample lesson content
    views/
      shell.js           # NEW: shellHTML — topbar + segmented tabs + empty view slot
      dashboard.js       # NEW: dashboardHTML — the Dashboard screen as a string
      lesson.js          # NEW: lessonHTML — the Lesson (exercise) screen as a string
      diagnostic.js      # NEW: diagnosticHTML — the six questions as styled option rows
    app.js               # modify: orchestrate views, wire handlers, log events
  tests/
    timer.test.js        # NEW
    reveal.test.js       # NEW
    views.test.js        # NEW (string-output tests for the four view functions)
backend/
  app.py                 # modify: also serve /styles.css
tests/
  test_static.py         # modify: assert /styles.css is served
```

Each view file owns one screen's markup. `timer.js`/`reveal.js` own the only real logic. `app.js` is the one place DOM and events meet.

---

### Task 1: Stylesheet + styled shell (topbar, tabs, view switching)

**What this is:** The frame every screen sits in — the brand bar, the streak chip, and the Dashboard/Lesson segmented control — plus the design's stylesheet, served by the Pi.
**Why:** Everything else renders *inside* this frame. Getting the shell and the real CSS in first means every later screen looks right immediately.
**What you can verify:** Opening the page shows the warm frosted-glass frame with two working tabs; clicking a tab switches which one is highlighted.

**Files:**
- Create: `frontend/styles.css` (copied from `content/design/reference/styles.css`)
- Create: `frontend/src/views/shell.js`
- Create: `frontend/tests/views.test.js`
- Modify: `frontend/platform.html`
- Modify: `backend/app.py`
- Modify: `tests/test_static.py`

**Interfaces:**
- Produces:
  - `frontend/src/views/shell.js`: `shellHTML({ activeTab, streakDays }) -> string`. `activeTab` is `"dashboard"` or `"lesson"`. Renders the topbar (brand + streak chip showing `streakDays`), the two-button segmented control (the active tab carries `aria-selected="true"`), and an empty `<div id="view"></div>` slot where screens render. Tab buttons carry `data-tab="dashboard"` / `data-tab="lesson"`.
- Backend: `GET /styles.css` serves `frontend/styles.css`.

- [ ] **Step 1: Bring in the stylesheet verbatim**

Copy the design stylesheet into the served frontend folder (it already exists in the repo from the design export):
```bash
cp content/design/reference/styles.css frontend/styles.css
```

- [ ] **Step 2: Write the failing shell test**

`frontend/tests/views.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML } from "../src/views/shell.js";

test("shell shows both tabs with the active one selected", () => {
  const html = shellHTML({ activeTab: "lesson", streakDays: 12 });
  assert.match(html, /data-tab="dashboard"/);
  assert.match(html, /data-tab="lesson"[^>]*aria-selected="true"/);
  assert.match(html, /id="view"/);
  assert.match(html, /12/);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/views/shell.js`.

- [ ] **Step 4: Write the shell view**

`frontend/src/views/shell.js`:
```javascript
const FLAME = `<svg class="flame" width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 2c1 3-1 4-1 6a3 3 0 006 0c0-1.5-1-2.5-1-4 2 1.5 4 4 4 8a8 8 0 11-16 0c0-4 3-6 4-8 .5 1 1 1.5 2 2 1-1 1.5-2 1-4z" fill="#e0892f"/></svg>`;

export function shellHTML({ activeTab, streakDays }) {
  const sel = (t) => (t === activeTab ? 'aria-selected="true"' : 'aria-selected="false"');
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <div class="streak">${FLAME}${streakDays}</div>
    </header>
    <div class="tabs" role="tablist">
      <button class="tab" role="tab" data-tab="dashboard" ${sel("dashboard")}>Dashboard</button>
      <button class="tab" role="tab" data-tab="lesson" ${sel("lesson")}>Lesson</button>
    </div>
    <div id="view"></div>
  `;
}
```

- [ ] **Step 5: Point the page at the stylesheet**

Replace `frontend/platform.html` with:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Claude University</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <div class="page"><main class="app" id="app">Loading…</main></div>
    <script type="module">
      import { init } from "/src/app.js";
      init({ window, fetch: window.fetch.bind(window) });
    </script>
  </body>
</html>
```

- [ ] **Step 6: Serve the stylesheet from the backend**

In `backend/app.py`, add a route alongside the existing `index`/`src_files` routes (inside `create_app`, before `return app`):
```python
    @app.get("/styles.css")
    def styles():
        return send_from_directory(frontend_dir, "styles.css")
```

- [ ] **Step 7: Add the backend static test**

Add to `tests/test_static.py`:
```python
def test_styles_served(client):
    resp = client.get("/styles.css")
    assert resp.status_code == 200
    assert b".card" in resp.data
```

- [ ] **Step 8: Run the tests**

Run: `cd frontend && node --test` → PASS (shell test + Plan 2's tests).
Run: `pytest tests/test_static.py -v` (from project root) → PASS (3 passed).

- [ ] **Step 9: Commit**

```bash
git add frontend/styles.css frontend/src/views/shell.js frontend/tests/views.test.js frontend/platform.html backend/app.py tests/test_static.py
git commit -m "feat(frontend): styled shell, stylesheet, served from Pi

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The Dashboard screen

**What this is:** The home screen — today's session card, the phase bar, the two stat cards (course progress, reviews due), and the streak strip — rendered from a plain data object.
**Why:** It's the screen you open to. Building it from a data object (not hard-coded markup) means the same screen will later be driven by real numbers without touching its look.
**What you can verify:** The Dashboard matches `content/design/dashboard.png` — topic, progress %, reviews count, streak line all present and styled.

**Files:**
- Create: `frontend/src/seed.js`
- Create: `frontend/src/views/dashboard.js`
- Test: `frontend/tests/views.test.js` (add Dashboard tests)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `frontend/src/seed.js`: `DASHBOARD_SEED` object with fields `{ topic, sub, durationMin, progressPct, lessonsDone, lessonsTotal, reviewsDue, streakDays }`.
  - `frontend/src/views/dashboard.js`: `dashboardHTML(data, timerView) -> string`. `data` is shaped like `DASHBOARD_SEED`. `timerView` is `{ fills: [number, number, number] (0–1), activePhaseIndex: 0|1|2, statusLabel: string, clock: string }` — supplied by the timer in Task 3; Task 2 may pass a static default. Renders the session card, phase bar/labels, both stats, and the streak strip using the design's classes.

- [ ] **Step 1: Write the seed data**

`frontend/src/seed.js`:
```javascript
export const DASHBOARD_SEED = {
  topic: "Backpropagation, intuitively",
  sub: "Module 3 · Neural Networks · Lesson 2",
  durationMin: 90,
  progressPct: 30,
  lessonsDone: 12,
  lessonsTotal: 40,
  reviewsDue: 8,
  streakDays: 12,
};
```

- [ ] **Step 2: Write the failing Dashboard test**

Add to `frontend/tests/views.test.js`:
```javascript
import { dashboardHTML } from "../src/views/dashboard.js";
import { DASHBOARD_SEED } from "../src/seed.js";

const idleTimer = {
  fills: [0, 0, 0],
  activePhaseIndex: 0,
  statusLabel: "<b>Warm-up</b> in progress",
  clock: "0:00 / 90:00",
};

test("dashboard renders the seeded session and stats", () => {
  const html = dashboardHTML(DASHBOARD_SEED, idleTimer);
  assert.match(html, /Backpropagation, intuitively/);
  assert.match(html, /TODAY'S SESSION/);
  assert.match(html, /Warm-up/);
  assert.match(html, /Peak focus/);
  assert.match(html, /Cool-down/);
  assert.match(html, /30<\/span>/); // progress number
  assert.match(html, /12 of 40 lessons/);
  assert.match(html, />8<\/span>/); // reviews due
  assert.match(html, /12-day streak/);
  assert.match(html, /data-action="start-session"/);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/views/dashboard.js`.

- [ ] **Step 4: Write the Dashboard view**

`frontend/src/views/dashboard.js`:
```javascript
const CLOCK_ICON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#a59b89" stroke-width="2"/><path d="M12 7v5l3 2" stroke="#a59b89" stroke-width="2" stroke-linecap="round"/></svg>`;
const PLAY_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="#fff"><path d="M7 5l12 7-12 7V5z"/></svg>`;
const FLAME = `<svg class="flame" viewBox="0 0 24 24" fill="none"><path d="M12 2c1 3-1 4-1 6a3 3 0 006 0c0-1.5-1-2.5-1-4 2 1.5 4 4 4 8a8 8 0 11-16 0c0-4 3-6 4-8 .5 1 1 1.5 2 2 1-1 1.5-2 1-4z" fill="#e0892f"/></svg>`;

const PHASE_COLORS = ["#3aa0e0", "#7c6aff", "#25b478"];
const PHASE_NAMES = ["Warm-up", "Peak focus", "Cool-down"];
const PHASE_DUR = ["15m", "60m", "15m"];
const PHASE_FLEX = [15, 60, 15];

export function dashboardHTML(data, timerView) {
  const tracks = PHASE_FLEX.map(
    (flex, i) =>
      `<div class="phase-track" style="flex:${flex} 1 0"><i style="background:${PHASE_COLORS[i]}; width:${Math.round(
        timerView.fills[i] * 100,
      )}%"></i></div>`,
  ).join("");
  const labels = PHASE_FLEX.map(
    (flex, i) =>
      `<div class="${i === timerView.activePhaseIndex ? "active-warm" : ""}" style="flex:${flex} 1 0"><div class="name">${PHASE_NAMES[i]}</div><div class="dur">${PHASE_DUR[i]}</div></div>`,
  ).join("");

  return `
    <div class="greeting"><h1>Good morning, Werner</h1><span>Today</span></div>
    <section class="card">
      <div class="session-head">
        <span class="eyebrow">TODAY'S SESSION</span>
        <span class="meta">${CLOCK_ICON} ${data.durationMin} min</span>
      </div>
      <h2 class="session-topic">${data.topic}</h2>
      <div class="session-sub">${data.sub}</div>
      <div class="phase-bar" aria-label="Session plan">${tracks}</div>
      <div class="phase-labels">${labels}</div>
      <div class="timer-status"><span>${timerView.statusLabel}</span><span class="clock">${timerView.clock}</span></div>
      <button class="btn-primary" data-action="start-session">${PLAY_ICON} Start session</button>
    </section>
    <div class="stat-row">
      <section class="stat">
        <span class="eyebrow mut">COURSE PROGRESS</span>
        <div style="display:flex; align-items:baseline; gap:6px; margin-top:12px"><span class="big">${data.progressPct}</span><span class="unit">%</span></div>
        <div class="bar"><i style="width:${data.progressPct}%"></i></div>
        <div class="stat-note">${data.lessonsDone} of ${data.lessonsTotal} lessons</div>
      </section>
      <section class="stat">
        <span class="eyebrow mut">REVIEWS DUE</span>
        <div style="display:flex; align-items:baseline; gap:6px; margin-top:12px"><span class="big" style="color:var(--blue)">${data.reviewsDue}</span><span class="unit">cards</span></div>
        <div class="stat-note" style="margin:10px 0 14px">Spaced repetition</div>
        <button class="btn-secondary" data-action="review">Review</button>
      </section>
    </div>
    <div class="streak-strip">${FLAME}<div><b>${data.streakDays}-day streak.</b> One session today keeps it alive.</div></div>
  `;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (shell + dashboard tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/seed.js frontend/src/views/dashboard.js frontend/tests/views.test.js
git commit -m "feat(frontend): styled Dashboard screen from seed data

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The 90-minute session timer

**What this is:** The maths behind the phase bar — given how many seconds have elapsed, which phase you're in (warm-up/peak/cool-down), how full each phase segment should be, and the clock text.
**Why:** This is the one genuinely fiddly bit of Dashboard logic, so it gets isolated and tested on its own rather than tangled into rendering.
**What you can verify:** At 0s you're in warm-up with everything empty; at 30 min you're in peak with warm-up full; at 89 min you're in cool-down; the clock reads `MM:SS / 90:00`.

**Files:**
- Create: `frontend/src/timer.js`
- Test: `frontend/tests/timer.test.js`

**Interfaces:**
- Produces (in `frontend/src/timer.js`):
  - `TOTAL_SECONDS = 5400`
  - `PHASE_SECONDS = [900, 3600, 900]` (warm-up 15m, peak 60m, cool-down 15m)
  - `timerView(elapsedSeconds) -> { fills: [number, number, number], activePhaseIndex: 0|1|2, statusLabel: string, clock: string }`. `fills[i]` is that phase's completion 0–1 (clamped). `activePhaseIndex` is the phase the elapsed time falls in (stays `2` once complete). `statusLabel` is `"<b>NAME</b> in progress"` while running, `"<b>Session complete</b>"` at/after `TOTAL_SECONDS`. `clock` is `"M:SS / 90:00"`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/timer.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { timerView, TOTAL_SECONDS } from "../src/timer.js";

test("at start: warm-up active, nothing filled", () => {
  const v = timerView(0);
  assert.deepEqual(v.fills, [0, 0, 0]);
  assert.equal(v.activePhaseIndex, 0);
  assert.equal(v.clock, "0:00 / 90:00");
  assert.match(v.statusLabel, /Warm-up/);
});

test("at 30 min: peak active, warm-up full, peak part-filled", () => {
  const v = timerView(30 * 60);
  assert.equal(v.activePhaseIndex, 1);
  assert.equal(v.fills[0], 1);
  assert.ok(v.fills[1] > 0 && v.fills[1] < 1);
  assert.equal(v.fills[2], 0);
  assert.equal(v.clock, "30:00 / 90:00");
});

test("at 89 min: cool-down active", () => {
  const v = timerView(89 * 60);
  assert.equal(v.activePhaseIndex, 2);
  assert.equal(v.fills[0], 1);
  assert.equal(v.fills[1], 1);
});

test("at/after total: complete", () => {
  const v = timerView(TOTAL_SECONDS);
  assert.deepEqual(v.fills, [1, 1, 1]);
  assert.match(v.statusLabel, /complete/i);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/timer.js`.

- [ ] **Step 3: Write the implementation**

`frontend/src/timer.js`:
```javascript
export const PHASE_SECONDS = [900, 3600, 900];
export const TOTAL_SECONDS = PHASE_SECONDS.reduce((a, b) => a + b, 0);
const PHASE_NAMES = ["Warm-up", "Peak focus", "Cool-down"];

function mmss(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function timerView(elapsedSeconds) {
  const e = Math.max(0, Math.min(elapsedSeconds, TOTAL_SECONDS));
  const fills = [];
  let remaining = e;
  for (const len of PHASE_SECONDS) {
    const inThis = Math.max(0, Math.min(remaining, len));
    fills.push(len === 0 ? 0 : inThis / len);
    remaining -= inThis;
  }

  let activePhaseIndex = 0;
  let acc = 0;
  for (let i = 0; i < PHASE_SECONDS.length; i++) {
    acc += PHASE_SECONDS[i];
    if (e < acc) {
      activePhaseIndex = i;
      break;
    }
    activePhaseIndex = i;
  }

  const complete = e >= TOTAL_SECONDS;
  const statusLabel = complete
    ? "<b>Session complete</b>"
    : `<b>${PHASE_NAMES[activePhaseIndex]}</b> in progress`;

  return { fills, activePhaseIndex, statusLabel, clock: `${mmss(e)} / 90:00` };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/timer.js frontend/tests/timer.test.js
git commit -m "feat(frontend): 90-minute session timer phase logic

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The Lesson screen + answer-before-solution gate

**What this is:** The Lesson (exercise) screen — the step bar, the prompt, the answer box, the gated hint, and the gated solution — plus the rule that the solution can't be revealed until you've written something.
**Why:** The "answer first, then reveal" gate is the core learning-science behavior on this screen, so its logic is isolated and tested; the screen itself is rendered from state like the others.
**What you can verify:** With an empty answer the solution button is locked; type something and it becomes revealable; reveal it and the solution panel appears; matches `content/design/lesson.png`.

**Files:**
- Create: `frontend/src/reveal.js`
- Create: `frontend/src/views/lesson.js`
- Modify: `frontend/src/seed.js` (add the sample lesson)
- Test: `frontend/tests/reveal.test.js`, `frontend/tests/views.test.js` (add Lesson tests)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `frontend/src/reveal.js`: `canReveal(answer) -> boolean` (true when `answer` trimmed is non-empty); `solutionState({ answer, revealed }) -> "locked" | "ready" | "shown"` (`"shown"` if `revealed`; else `"ready"` if `canReveal`; else `"locked"`).
  - `frontend/src/seed.js`: add `SAMPLE_LESSON = { step, totalSteps, topic, eyebrow, promptHtml, hintHtml, solutionAns, solutionNote }`.
  - `frontend/src/views/lesson.js`: `lessonHTML(lesson, state) -> string` where `state = { answer, hintVisible, solutionRevealed }`. Renders the 5-segment step bar (segments before `lesson.step` get `done`, the `step`-th gets `now`), the exercise card, a `<textarea data-field="answer">` holding `state.answer`, a hint toggle (`data-action="toggle-hint"`) plus the hint panel only when `hintVisible`, a solution button (`data-action="reveal-solution"`) whose class is the `solutionState`, the solution panel only when `solutionRevealed`, and Back/Continue nav (`data-action="back"`, `data-action="continue"`).

- [ ] **Step 1: Write the failing gate test**

`frontend/tests/reveal.test.js`:
```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { canReveal, solutionState } from "../src/reveal.js";

test("empty answer cannot reveal", () => {
  assert.equal(canReveal(""), false);
  assert.equal(canReveal("   "), false);
  assert.equal(solutionState({ answer: "", revealed: false }), "locked");
});

test("non-empty answer is ready", () => {
  assert.equal(canReveal("w - 0.04"), true);
  assert.equal(solutionState({ answer: "w - 0.04", revealed: false }), "ready");
});

test("revealed is shown", () => {
  assert.equal(solutionState({ answer: "w - 0.04", revealed: true }), "shown");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/reveal.js`.

- [ ] **Step 3: Write the gate logic**

`frontend/src/reveal.js`:
```javascript
export function canReveal(answer) {
  return typeof answer === "string" && answer.trim().length > 0;
}

export function solutionState({ answer, revealed }) {
  if (revealed) return "shown";
  return canReveal(answer) ? "ready" : "locked";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS.

- [ ] **Step 5: Add the sample lesson to seed**

Append to `frontend/src/seed.js`:
```javascript
export const SAMPLE_LESSON = {
  step: 4,
  totalSteps: 5,
  topic: "Backpropagation",
  eyebrow: "EXERCISE",
  promptHtml:
    'A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>. ' +
    'With learning rate <code>η = 0.1</code>, write the gradient-descent update for <code>w</code>.',
  hintHtml:
    'Gradient descent moves <em>against</em> the gradient: <span class="mono">w ← w − η · ∂L/∂w</span>',
  solutionAns: "w ← w − (0.1 × 0.4) = w − 0.04",
  solutionNote:
    "Each step subtracts the learning rate times the gradient — a small move downhill on the loss.",
};
```

- [ ] **Step 6: Write the failing Lesson view test**

Add to `frontend/tests/views.test.js`:
```javascript
import { lessonHTML } from "../src/views/lesson.js";
import { SAMPLE_LESSON } from "../src/seed.js";

test("lesson locks the solution with an empty answer", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /class="reveal locked"/);
  assert.doesNotMatch(html, /class="solution"/); // panel hidden
  assert.doesNotMatch(html, /class="hint"[^-]/); // hint panel hidden (not the toggle)
  assert.match(html, /data-field="answer"/);
});

test("lesson makes the solution revealable once answered", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: false, solutionRevealed: false });
  assert.match(html, /class="reveal ready"/);
});

test("lesson shows the solution panel once revealed", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: true, solutionRevealed: true });
  assert.match(html, /class="reveal shown"/);
  assert.match(html, /class="solution"/);
  assert.match(html, /w − 0.04/);
  assert.match(html, /class="hint"/); // hint panel visible
});
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/views/lesson.js`.

- [ ] **Step 8: Write the Lesson view**

`frontend/src/views/lesson.js`:
```javascript
import { solutionState } from "../reveal.js";

const BULB = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.2 1 2.5h6c0-1.3.3-1.8 1-2.5A6 6 0 0012 3z" stroke="#e0892f" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const LOCK = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 11V8a4 4 0 018 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`;
const ARROW = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const REVEAL_TEXT = { locked: "Attempt first to unlock the solution", ready: "Reveal solution", shown: "Solution shown" };
const HINT_TEXT = { true: "Hide hint", false: "Show hint" };

export function lessonHTML(lesson, state) {
  const segs = Array.from({ length: lesson.totalSteps }, (_, i) => {
    if (i + 1 < lesson.step) return '<i class="done"></i>';
    if (i + 1 === lesson.step) return '<i class="now"></i>';
    return "<i></i>";
  }).join("");

  const sol = solutionState(state);
  const hint = state.hintVisible
    ? `<div class="hint" style="margin-bottom:10px">${lesson.hintHtml}</div>`
    : "";
  const solutionPanel = state.solutionRevealed
    ? `<div class="solution"><div class="lbl">SOLUTION</div><div class="ans">${lesson.solutionAns}</div><div class="note">${lesson.solutionNote}</div></div>`
    : "";

  return `
    <div>
      <div class="steps">${segs}</div>
      <div class="steprow"><span>Step ${lesson.step} of ${lesson.totalSteps} · <b>Exercise</b></span><span class="right">${lesson.topic}</span></div>
    </div>
    <section class="card lesson">
      <span class="eyebrow">${lesson.eyebrow}</span>
      <p class="prompt">${lesson.promptHtml}</p>
      <textarea data-field="answer" placeholder="Write your update here…" style="min-height:64px; margin:12px 0">${state.answer}</textarea>
      <button class="hint-toggle" data-action="toggle-hint" style="margin-bottom:10px">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
      ${hint}
      <button class="reveal ${sol}" data-action="reveal-solution">${LOCK}<span style="flex:1">${REVEAL_TEXT[sol]}</span></button>
      ${solutionPanel}
    </section>
    <div class="nav">
      <button class="btn-back" data-action="back">Back</button>
      <button class="btn-primary" data-action="continue">Continue ${ARROW}</button>
    </div>
  `;
}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd frontend && node --test`
Expected: PASS (all view + reveal tests).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/reveal.js frontend/src/views/lesson.js frontend/src/seed.js frontend/tests/reveal.test.js frontend/tests/views.test.js
git commit -m "feat(frontend): styled Lesson screen with answer-before-solution gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Diagnostic screen, wiring, event logging, and the live Pi proof

**What this is:** The styled first-run diagnostic, plus the glue in `app.js` that picks which screen to show, runs the timer, handles every click/keystroke, logs each as an event, and saves the profile — then the real-browser proof on the Pi.
**Why:** This is where the screens become a usable app and where the whole point — capturing your learning behavior as events — actually happens.
**What you can verify:** A fresh browser shows the styled six-question diagnostic; finishing it lands you on the Dashboard; switching tabs, starting the timer, revealing a hint/solution each appear as events in the Pi's database.

**Files:**
- Create: `frontend/src/views/diagnostic.js`
- Modify: `frontend/src/app.js`
- Modify: `frontend/styles.css` (a few diagnostic-only rules)
- Test: `frontend/tests/views.test.js` (add diagnostic test); Playwright real-browser check

**Interfaces:**
- Consumes: `shellHTML` (T1), `dashboardHTML` (T2), `timerView` (T3), `lessonHTML` (T4), `DASHBOARD_SEED`/`SAMPLE_LESSON` (T2/T4); from Plan 2: `getSessionId`, `buildEvent`, `appendEvent`, `newId`, `flush`, `loadProfile`, `saveProfile`, `DIAGNOSTIC`, `buildProfile`.
- Produces:
  - `frontend/src/views/diagnostic.js`: `diagnosticHTML(answers) -> string`. `answers` maps question `key` → chosen `value` (or undefined). Renders each `DIAGNOSTIC` question in a `.card` with `.opt` option rows (`data-q="<key>"`, `data-value="<value>"`); a chosen row carries `selected`. A Continue button (`data-action="finish-diagnostic"`) is `disabled` until all six are answered.
  - `frontend/src/app.js`: `init({ window, fetch })` unchanged signature; now renders the diagnostic when no profile exists, else the shell + Dashboard, wiring all handlers and logging events.

- [ ] **Step 1: Write the failing diagnostic test**

Add to `frontend/tests/views.test.js`:
```javascript
import { diagnosticHTML } from "../src/views/diagnostic.js";

test("diagnostic renders all six questions and gates Continue", () => {
  const none = diagnosticHTML({});
  assert.equal((none.match(/data-q="/g) || []).length >= 6, true);
  assert.match(none, /data-action="finish-diagnostic"[^>]*disabled/);
});

test("diagnostic enables Continue once all answered and marks selections", () => {
  const all = diagnosticHTML({
    contentOrder: "theory_first",
    stuckStrategy: "push",
    wrongAnswerFeedback: "hint",
    sessionStyle: "deep_block",
    lessonStructure: "top_down",
    analogies: true,
  });
  assert.doesNotMatch(all, /data-action="finish-diagnostic"[^>]*disabled/);
  assert.match(all, /class="opt selected"/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test`
Expected: FAIL — cannot find `../src/views/diagnostic.js`.

- [ ] **Step 3: Write the diagnostic view**

`frontend/src/views/diagnostic.js`:
```javascript
import { DIAGNOSTIC } from "../profile.js";

const DOT = `<span class="dot"><i></i></span>`;

export function diagnosticHTML(answers) {
  const cards = DIAGNOSTIC.map((q) => {
    const opts = q.options
      .map((o) => {
        const selected = answers[q.key] === o.value ? " selected" : "";
        return `<button class="opt${selected}" data-q="${q.key}" data-value="${o.value}">${DOT}<span style="flex:1">${o.label}</span></button>`;
      })
      .join("");
    return `<section class="card" style="margin-bottom:14px"><div class="diag-q">${q.question}</div>${opts}</section>`;
  }).join("");

  const answered = DIAGNOSTIC.every((q) => answers[q.key] !== undefined);
  const disabled = answered ? "" : "disabled";

  return `
    <div class="greeting"><h1>Let's tune how this teaches you</h1></div>
    ${cards}
    <button class="btn-primary" data-action="finish-diagnostic" ${disabled}>Start learning</button>
  `;
}
```

- [ ] **Step 4: Add the diagnostic CSS rules**

Append to `frontend/styles.css`:
```css
/* diagnostic question heading (reuses .card + .opt option rows) */
.diag-q{font-size:16px; font-weight:600; color:var(--text); line-height:1.35; margin-bottom:13px}
```

- [ ] **Step 5: Run the diagnostic test**

Run: `cd frontend && node --test`
Expected: PASS (all frontend tests).

- [ ] **Step 6: Rewrite `app.js` to orchestrate, wire, and log**

Replace `frontend/src/app.js` with:
```javascript
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { DASHBOARD_SEED, SAMPLE_LESSON } from "./seed.js";
import { shellHTML } from "./views/shell.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML } from "./views/lesson.js";
import { diagnosticHTML } from "./views/diagnostic.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const FLUSH_INTERVAL_MS = 15000;

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const doc = window.document;
  const sessionId = getSessionId(storage);

  const log = (type, payload = null) =>
    appendEvent(storage, buildEvent({ type, sessionId, payload, now: () => new Date(), newId }));
  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });

  log("session_start");
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const root = doc.getElementById("app");

  // ---- mutable UI state ----
  const ui = {
    tab: "dashboard",
    timer: { running: false, elapsed: 0, intervalId: null },
    lesson: { answer: SAMPLE_LESSON ? "" : "", hintVisible: false, solutionRevealed: false },
    diagnostic: {},
  };

  // ---- diagnostic flow ----
  async function showDiagnostic() {
    root.innerHTML = diagnosticHTML(ui.diagnostic);
    root.querySelectorAll('[data-q]').forEach((btn) => {
      btn.addEventListener("click", () => {
        let v = btn.getAttribute("data-value");
        if (v === "true") v = true;
        else if (v === "false") v = false;
        ui.diagnostic[btn.getAttribute("data-q")] = v;
        showDiagnostic();
      });
    });
    const finish = root.querySelector('[data-action="finish-diagnostic"]');
    finish.addEventListener("click", async () => {
      const profile = buildProfile(ui.diagnostic);
      log("diagnostic_completed", profile);
      await saveProfile({ fetch, endpoint: PROFILE_ENDPOINT, profile });
      await doFlush();
      showApp();
    });
  }

  // ---- main app (shell + tabbed views) ----
  function renderView() {
    const view = root.querySelector("#view");
    if (ui.tab === "dashboard") {
      view.innerHTML = dashboardHTML(DASHBOARD_SEED, timerView(ui.timer.elapsed));
      view.querySelector('[data-action="start-session"]').addEventListener("click", startSession);
      view.querySelector('[data-action="review"]').addEventListener("click", () => log("review_opened"));
    } else {
      view.innerHTML = lessonHTML(SAMPLE_LESSON, ui.lesson);
      const ta = view.querySelector('[data-field="answer"]');
      ta.addEventListener("input", () => {
        ui.lesson.answer = ta.value;
        // re-render only the reveal button state without losing focus: cheap full re-render is fine here
        const sel = ta.selectionStart;
        renderView();
        const ta2 = root.querySelector('[data-field="answer"]');
        ta2.focus();
        ta2.setSelectionRange(sel, sel);
      });
      view.querySelector('[data-action="toggle-hint"]').addEventListener("click", () => {
        ui.lesson.hintVisible = !ui.lesson.hintVisible;
        if (ui.lesson.hintVisible) log("hint_revealed", { topic: SAMPLE_LESSON.topic });
        renderView();
      });
      view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
        if (!ui.lesson.answer.trim()) return; // gate: must attempt first
        if (!ui.lesson.solutionRevealed) log("solution_revealed", { topic: SAMPLE_LESSON.topic });
        ui.lesson.solutionRevealed = true;
        renderView();
      });
      view.querySelector('[data-action="back"]').addEventListener("click", () => switchTab("dashboard"));
      view.querySelector('[data-action="continue"]').addEventListener("click", () => log("lesson_continue", { step: SAMPLE_LESSON.step }));
    }
  }

  function bindTabs() {
    root.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
    });
  }

  function switchTab(tab) {
    if (tab === ui.tab) return;
    ui.tab = tab;
    log("view_switch", { to: tab });
    showApp();
  }

  function startSession() {
    if (ui.timer.running) return;
    ui.timer.running = true;
    log("session_timer_start", { topic: DASHBOARD_SEED.topic });
    ui.timer.intervalId = window.setInterval(() => {
      ui.timer.elapsed += 1;
      if (ui.timer.elapsed >= TOTAL_SECONDS) {
        window.clearInterval(ui.timer.intervalId);
        ui.timer.running = false;
        log("session_timer_complete");
      }
      if (ui.tab === "dashboard") {
        const view = root.querySelector("#view");
        view.innerHTML = dashboardHTML(DASHBOARD_SEED, timerView(ui.timer.elapsed));
        view.querySelector('[data-action="start-session"]').addEventListener("click", startSession);
        view.querySelector('[data-action="review"]').addEventListener("click", () => log("review_opened"));
      }
    }, 1000);
  }

  function showApp() {
    root.innerHTML = shellHTML({ activeTab: ui.tab, streakDays: DASHBOARD_SEED.streakDays });
    bindTabs();
    renderView();
  }

  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  if (profile) showApp();
  else showDiagnostic();
}
```

- [ ] **Step 7: Run every test (frontend + backend)**

Run: `cd frontend && node --test` → PASS (all frontend tests).
Run: `pytest -v` (from project root) → PASS (all backend tests).

- [ ] **Step 8: Deploy to the Pi**

```bash
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='backend/data' \
  --exclude='.pytest_cache' --exclude='.remember' --exclude='.git' --exclude='node_modules' \
  /Users/wernervanellewee/Projects/Claude_Education/ \
  werner@192.168.2.69:~/claude_university/
ssh werner@192.168.2.69 'sudo systemctl restart claude-university && sleep 2 && systemctl is-active claude-university'
```
Expected: `active`.

- [ ] **Step 9: Real-browser end-to-end check (Playwright) against the Pi over Tailscale**

> Verify on `http://100.99.33.106:8200/` — the real insecure-context URL, not localhost (Plan 2 lesson).

1. Reset to a clean first-run: clear the Pi profile + events so the diagnostic shows.
   ```bash
   ssh werner@192.168.2.69 "cd ~/claude_university && .venv/bin/python -c \"import sqlite3; c=sqlite3.connect('backend/data/learning.db'); c.execute('DELETE FROM events'); c.execute('DELETE FROM profile'); c.execute(\\\"DELETE FROM sqlite_sequence\\\"); c.commit()\""
   ```
2. `browser_navigate` to `http://100.99.33.106:8200/`, snapshot → the styled **diagnostic** (six questions) shows, no console errors.
3. Click one option per question (`data-q` buttons), then "Start learning" → snapshot shows the **Dashboard** (matches `content/design/dashboard.png`).
4. Click "Start session" → wait ~3s → snapshot: the clock has advanced past `0:00` and the warm-up segment shows fill.
5. Click the "Lesson" tab → snapshot shows the **Lesson** screen (matches `content/design/lesson.png`); the solution button reads "Attempt first to unlock the solution" (locked).
6. Type into the answer box, click "Reveal solution" → snapshot: the solution panel appears.
7. Read the events back:
   ```bash
   curl -s 'http://100.99.33.106:8200/api/events?limit=50' | python3 -m json.tool
   ```
   Expected: `session_start`, `diagnostic_completed`, `session_timer_start`, `view_switch`, `solution_revealed` events present — proving every interaction is logged to the Pi.
8. Take screenshots of the Dashboard and Lesson for the record (`browser_take_screenshot`).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/views/diagnostic.js frontend/src/app.js frontend/styles.css frontend/tests/views.test.js
git commit -m "feat(frontend): diagnostic screen, view orchestration, event logging

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec/design coverage:**
- Dashboard screen (session card, 90-min phase timer, course progress, reviews due, streak) → Tasks 2–3, matches `dashboard.png`. ✓
- Lesson screen (step bar, exercise, gated hint, hidden solution, answer box) → Task 4, matches `lesson.png`. ✓
- Progressive reveal (answer before solution; hint gated) → Task 4 (`reveal.js`) + Task 5 wiring (reveal click no-ops on empty answer). ✓
- One primary action per screen, design classes reused verbatim → enforced via copied `styles.css` + Global Constraints. ✓
- Diagnostic as first-run, profile saved/versioned on the Pi → Task 5 (reuses Plan 1 profile store + Plan 2 `buildProfile`/`saveProfile`). ✓
- Every interaction logged as an event → Task 5 (`session_start`, `diagnostic_completed`, `view_switch`, `session_timer_start/complete`, `hint_revealed`, `solution_revealed`, `lesson_continue`, `review_opened`). ✓
- Served by the Pi, plain HTTP / insecure-context safe → Tasks 1, 5; no secure-context APIs used. ✓
- *Correctly deferred to later plans:* FSRS scheduling, mastery (BKT), real content packs, adaptive routing, the full 5-step lesson sequence (only the designed Exercise step is built), concept-check/pre-quiz/explain-it-back steps, the in-app tutor (Plan 4).

**2. Placeholder scan:** Seed content is explicitly labelled sample data (Decisions + Global Constraints), not a stealth TODO. No "handle edge cases"/"TBD"; every code step is complete. ✓

**3. Type/name consistency:** `shellHTML`/`dashboardHTML`/`lessonHTML`/`diagnosticHTML` signatures match between their defining task and `app.js` (Task 5). `timerView` return shape (`fills`, `activePhaseIndex`, `statusLabel`, `clock`) consistent between Task 3 and its consumers (Task 2 test + `app.js`). `solutionState`/`canReveal` (Task 4) consumed by `lesson.js` and `app.js`. `data-action`/`data-tab`/`data-q`/`data-field`/`data-value` attribute names consistent between the view strings and `app.js` query selectors. Plan 2 imports (`getSessionId`, `buildEvent`, `appendEvent`, `newId`, `flush`, `loadProfile`, `saveProfile`, `buildProfile`, `DIAGNOSTIC`) match their Plan 2 definitions. ✓
```
