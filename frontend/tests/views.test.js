import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML } from "../src/views/shell.js";
import { dashboardHTML } from "../src/views/dashboard.js";
import { lessonHTML } from "../src/views/lesson.js";
import { diagnosticHTML } from "../src/views/diagnostic.js";
import { DASHBOARD_SEED, SAMPLE_LESSON } from "../src/seed.js";

const idleTimer = {
  fills: [0, 0, 0],
  activePhaseIndex: 0,
  statusLabel: "<b>Warm-up</b> in progress",
  clock: "0:00 / 90:00",
};

test("shell shows both tabs with the active one selected", () => {
  const html = shellHTML({ activeTab: "lesson", streakDays: 12 });
  assert.match(html, /data-tab="dashboard"/);
  assert.match(html, /data-tab="lesson"[^>]*aria-selected="true"/);
  assert.match(html, /id="view"/);
  assert.match(html, /12/);
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
