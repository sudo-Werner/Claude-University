import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML } from "../src/views/shell.js";
import { dashboardHTML } from "../src/views/dashboard.js";
import { lessonHTML } from "../src/views/lesson.js";
import { diagnosticHTML } from "../src/views/diagnostic.js";
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

test("shell shows the streak; back control only when given", () => {
  const home = shellHTML({ streakDays: 12 });
  assert.match(home, /12/);
  assert.match(home, /id="view"/);
  assert.doesNotMatch(home, /data-action="nav-back"/);

  const inCourse = shellHTML({ streakDays: 12, back: "Courses" });
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
  assert.match(html, /12-day streak/);
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
