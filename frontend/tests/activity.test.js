import { test } from "node:test";
import assert from "node:assert/strict";
import { activityHTML } from "../src/views/activity.js";

// Build ISO strings on LOCAL days relative to `now`, so grouping labels are
// deterministic regardless of the machine's timezone.
const NOW = new Date(2026, 6, 15, 14, 0, 0); // local 2026-07-15 14:00
const at = (daysAgo, hour = 10) =>
  new Date(2026, 6, 15 - daysAgo, hour, 0, 0).toISOString();

const STUDY = { occurredAt: at(0), type: "lesson_view", courseTitle: "ML", lessonTitle: "Intro", quality: null };

test("activity groups entries under Today and Yesterday", () => {
  const html = activityHTML([
    STUDY,
    { ...STUDY, occurredAt: at(1), type: "lesson_reviewed", quality: "good" },
  ], { now: NOW });
  assert.match(html, /Today/);
  assert.match(html, /Yesterday/);
});

test("activity renders verbs, titles, and review quality", () => {
  const html = activityHTML([
    STUDY,
    { ...STUDY, type: "lesson_reviewed", quality: "easy" },
    { occurredAt: at(0), type: "course_created", courseTitle: "Stats", lessonTitle: null, quality: null },
    { occurredAt: at(0), type: "course_revised", courseTitle: "Stats", lessonTitle: null, quality: null },
  ], { now: NOW });
  assert.match(html, /Studied/);
  assert.match(html, /Completed/);
  assert.match(html, /rated easy/);
  assert.match(html, /Created course/);
  assert.match(html, /Revised course/);
  assert.match(html, /Intro/);
  assert.match(html, /Stats/);
});

test("activity escapes titles", () => {
  const html = activityHTML([{ ...STUDY, lessonTitle: "<img src=x>", courseTitle: "<b>x</b>" }], { now: NOW });
  assert.doesNotMatch(html, /<img src=x>/);
  assert.doesNotMatch(html, /<b>x<\/b>/);
});

test("activity shows an empty state", () => {
  assert.match(activityHTML([], { now: NOW }), /Nothing here yet/);
});

test("activity renders exam and gap-review entries", () => {
  const html = activityHTML([
    { occurredAt: "2026-07-15T09:00:00+00:00", type: "exam_result",
      courseTitle: "Algo", examLabel: "Sorting exam", score: 0.85, passed: true },
    { occurredAt: "2026-07-15T10:00:00+00:00", type: "remediation_started",
      courseTitle: "Algo", examLabel: "Final exam" },
  ], { now: new Date("2026-07-15T12:00:00+00:00") });
  assert.ok(html.includes("Sorting exam") && html.includes("85% — passed"));
  assert.ok(html.includes("Reviewed gaps") && html.includes("Final exam"));
});
