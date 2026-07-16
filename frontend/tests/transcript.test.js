import test from "node:test";
import assert from "node:assert/strict";
import { transcriptHTML } from "../src/views/transcript.js";

const DATA = { courses: [{
  courseId: "c1", title: "Algo <1>", coursePassed: true, passedOn: "2026-07-12",
  masteryCounts: { attempted: 1, familiar: 0, proficient: 2, mastered: 1 },
  lessonsTotal: 10, lessonsCompleted: 4,
  modules: [
    { key: "m1", title: "Sorting", attempts: 2, bestScore: 0.9, passed: true, passedOn: "2026-07-10" },
    { key: "m2", title: "Graphs", attempts: 1, bestScore: 0.6, passed: false, passedOn: null },
    { key: "m3", title: "DP", attempts: 0, bestScore: 0, passed: false, passedOn: null },
  ],
  final: { key: "final", title: "Final exam", attempts: 1, bestScore: 0.88, passed: true, passedOn: "2026-07-12" },
}] };

test("transcriptHTML renders rows, escapes titles, includes the non-credential note", () => {
  const html = transcriptHTML(DATA);
  assert.ok(html.includes("Algo &lt;1&gt;"));
  assert.ok(html.includes("90%") && html.includes("2026-07-10"));
  assert.ok(html.includes("best 60%") && html.includes("1 attempt"));
  assert.ok(html.includes("Not taken"));
  assert.ok(html.includes("Passed — 2026-07-12"));
  assert.ok(html.includes("4 of 10 lessons studied") && html.includes("3 at proficient or above"));
  assert.ok(html.includes("not an accredited credential"));
});

test("transcriptHTML declares the mastery standard", () => {
  const html = transcriptHTML(DATA);
  assert.ok(html.includes("Mastery standard: a course is passed when every module exam and the final are passed at 80% or above."));
});

test("transcriptHTML shows level and targetHours, esc()'d, when present", () => {
  const withLevel = { courses: [{ ...DATA.courses[0], level: "Master-equivalent <x>", targetHours: 130 }] };
  const html = transcriptHTML(withLevel);
  assert.ok(html.includes("Master-equivalent &lt;x&gt;"));
  assert.ok(html.includes("~130 h"));
  assert.ok(html.includes("Master-equivalent &lt;x&gt; · ~130 h · 4 of 10 lessons studied · 3 at proficient or above"));
});

test("transcriptHTML omits level and targetHours cleanly when absent (legacy course)", () => {
  const html = transcriptHTML(DATA);  // DATA has no level/targetHours field
  assert.ok(!html.includes("null"));
  assert.ok(!html.includes("undefined"));
  assert.ok(html.includes("4 of 10 lessons studied · 3 at proficient or above"));
});

test("transcriptHTML empty state", () => {
  const html = transcriptHTML({ courses: [] });
  assert.ok(html.includes("No courses yet"));
  assert.ok(html.includes("not an accredited credential"));
});

test("passed exam rows include the attempt count", () => {
  const html = transcriptHTML(DATA);
  assert.ok(html.includes("90% · 2026-07-10 · 2 attempts"));
  assert.ok(html.includes("88% · 2026-07-12 · 1 attempt"));   // singular on the final
});

test("capstone rows render after the final with the same status treatment", () => {
  const withCaps = { courses: [{ ...DATA.courses[0], capstones: [
    { scope: "m1", title: "Sorting", attempts: 2, bestScore: 0.75, passed: true, passedOn: "2026-07-13" },
    { scope: "course", title: "Course capstone", attempts: 1, bestScore: 0.4, passed: false, passedOn: null },
  ] }] };
  const html = transcriptHTML(withCaps);
  assert.ok(html.includes("Capstone: Sorting"));
  assert.ok(html.includes("Course capstone"));
  assert.ok(!html.includes("Capstone: Course capstone"));      // course scope is not double-labelled
  assert.ok(html.includes("75% · 2026-07-13 · 2 attempts"));
  assert.ok(html.includes("best 40% · 1 attempt"));
  assert.ok(html.indexOf("Capstone: Sorting") > html.indexOf("Final exam"));
});

test("courses without capstone submissions show nothing new", () => {
  const html = transcriptHTML(DATA);                            // DATA has no capstones field
  assert.ok(!html.includes("Capstone"));
});
