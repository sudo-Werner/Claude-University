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

test("transcriptHTML empty state", () => {
  const html = transcriptHTML({ courses: [] });
  assert.ok(html.includes("No courses yet"));
  assert.ok(html.includes("not an accredited credential"));
});
