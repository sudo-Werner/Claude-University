import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML } from "../src/views/shell.js";
import { dashboardHTML } from "../src/views/dashboard.js";
import { lessonHTML } from "../src/views/lesson.js";
import { diagnosticHTML } from "../src/views/diagnostic.js";
import { curriculumHTML, lessonStatus, moduleProgress } from "../src/views/curriculum.js";
const DASHBOARD_SEED = {
  topic: "Backpropagation, intuitively",
  sub: "Module 3 · Neural Networks · Lesson 2",
  durationMin: 90, progressPct: 30, lessonsDone: 12, lessonsTotal: 40,
  reviewsDue: 8, streakDays: 12,
};
const SAMPLE_LESSON = {
  step: 4, totalSteps: 5, topic: "Backpropagation", eyebrow: "EXERCISE",
  promptHtml: "A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>.",
  hintHtml: "Gradient descent moves <em>against</em> the gradient.",
  solutionAns: "w ← w − 0.04",
  solutionNote: "A small move downhill on the loss.",
};

const idleTimer = {
  fills: [0, 0, 0],
  activePhaseIndex: 0,
  statusLabel: "<b>Warm-up</b> in progress",
  clock: "0:00 / 90:00",
};

test("shell shows back control only when given", () => {
  const home = shellHTML({});
  assert.match(home, /id="view"/);
  assert.doesNotMatch(home, /data-action="nav-back"/);
  assert.doesNotMatch(home, /streak/i);

  const inCourse = shellHTML({ back: "Courses" });
  assert.match(inCourse, /data-action="nav-back"/);
  assert.match(inCourse, /Courses/);
});

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
  assert.match(html, /data-action="start-session"/);
});

test("lesson locks the solution with an empty answer", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /class="reveal locked"/);
  assert.doesNotMatch(html, /class="solution"/); // panel hidden
  assert.doesNotMatch(html, /<div class="hint"/); // hint panel hidden (not the toggle)
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
  assert.match(html, /<div class="hint"/); // hint panel visible
});

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

test("lesson shows the recall rating once the solution is revealed", () => {
  const revealed = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.match(revealed, /data-quality="again"/);
  assert.match(revealed, /data-quality="hard"/);
  assert.match(revealed, /data-quality="good"/);
  assert.match(revealed, /data-quality="easy"/);
  assert.match(revealed, /recall/i);

  const notYet = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(notYet, /data-quality=/);
});

test("lesson renders the checks section once the solution is revealed", () => {
  const withChecks = {
    ...SAMPLE_LESSON,
    checks: [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
  };
  const revealed = lessonHTML(withChecks, { answer: "x", hintVisible: false, solutionRevealed: true, checkAnswers: {}, checkResults: {} });
  assert.match(revealed, /Check your understanding/);
  assert.match(revealed, /data-check-input="0"/);

  const notYet = lessonHTML(withChecks, { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} });
  assert.doesNotMatch(notYet, /Check your understanding/);
});

test("dashboard shows a mastery breakdown when there is mastery data", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 50, lessonsDone: 2,
      lessonsTotal: 4, reviewsDue: 0, streakDays: 0,
      masteryCounts: { attempted: 1, familiar: 0, proficient: 1, mastered: 0 } },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" },
  );
  assert.match(html, /Mastery/);
  assert.match(html, /Proficient/i);
});

test("dashboard omits the mastery breakdown when all counts are zero", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 4, reviewsDue: 0, streakDays: 0,
      masteryCounts: { attempted: 0, familiar: 0, proficient: 0, mastered: 0 } },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" },
  );
  assert.doesNotMatch(html, /class="mastery"/);
});

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

test("shell no longer renders a streak pill", () => {
  const html = shellHTML({ back: "Courses" });
  assert.doesNotMatch(html, /streak/i);
});

test("dashboard no longer renders a streak strip", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 2, reviewsDue: 0, masteryCounts: {} },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" });
  assert.doesNotMatch(html, /streak/i);
});

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
