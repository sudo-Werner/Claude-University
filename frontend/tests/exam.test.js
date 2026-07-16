import test from "node:test";
import assert from "node:assert/strict";
import { examHTML, examResultHTML, examReady } from "../src/views/exam.js";

const EXAM = {
  examKey: "m1",
  questions: [
    { type: "mcq", prompt: "<p>Pick <em>one</em></p>", choices: ["<code>a</code>", "b", "c", "d"], objectiveText: "obj1", bloom: "remember", lessonId: "c1-l1" },
    { type: "free", prompt: "<p>Explain</p>", objectiveText: "obj2 <tag>", bloom: "apply", lessonId: "c1-l2" },
  ],
};

test("examHTML renders server-sanitized prompts raw and answers state", () => {
  const html = examHTML({ ...EXAM, title: "Module exam" }, { answers: { 0: 2 }, submitting: false, error: "" });
  assert.ok(html.includes("<p>Pick <em>one</em></p>"));        // raw, not escaped
  assert.ok(html.includes("<code>a</code>"));                   // choice raw
  assert.ok(html.includes('data-q="0"') && html.includes('data-choice="2"'));
  assert.ok(html.includes("selected"));
  assert.ok(html.includes("<textarea"));
  assert.ok(html.includes("disabled"));                          // free unanswered → submit disabled
});

test("examHTML escapes title and error, enables submit when ready", () => {
  const html = examHTML({ ...EXAM, title: "<b>x</b>" }, { answers: { 0: 1, 1: "done" }, submitting: false, error: "<script>e</script>" });
  assert.ok(!html.includes("<b>x</b>") && html.includes("&lt;b&gt;x&lt;/b&gt;"));
  assert.ok(!html.includes("<script>e</script>"));
  assert.ok(!/data-action="submit-exam"[^>]*disabled/.test(html));
});

test("examReady requires every mcq picked and every free non-blank", () => {
  assert.equal(examReady(EXAM, {}), false);
  assert.equal(examReady(EXAM, { 0: 1 }), false);
  assert.equal(examReady(EXAM, { 0: 1, 1: "  " }), false);
  assert.equal(examReady(EXAM, { 0: 1, 1: "ans" }), true);
});

test("examResultHTML shows pass banner, weak spots, and per-question feedback", () => {
  const result = {
    score: 0.85, passed: true, attempt: 2,
    perQuestion: [
      { type: "mcq", prompt: "<p>Q1</p>", choices: ["a", "b"], answer: 0, correct: false, correctIndex: 1, points: 0, objectiveText: "obj1", lessonId: "c1-l1" },
      { type: "free", prompt: "<p>Q2</p>", answer: "mine", verdict: "close", note: "<em>Nearly</em>", points: 0.5, objectiveText: "obj2", lessonId: "c1-l2" },
    ],
    weakSpots: [{ lessonId: "c1-l1", lessonTitle: "Lesson <One>", objectives: ["obj1 & more"] }],
  };
  const html = examResultHTML(result);
  assert.ok(html.includes("85%"));
  assert.ok(/passed/i.test(html));
  assert.ok(html.includes('data-lesson="c1-l1"'));
  assert.ok(html.includes("Lesson &lt;One&gt;"));                // lesson title escaped
  assert.ok(html.includes("obj1 &amp; more"));                   // objective escaped
  assert.ok(html.includes("<em>Nearly</em>"));                   // grader note raw (server-sanitized)
  assert.ok(html.includes('data-action="retake-exam"'));
  assert.ok(html.includes('data-action="back-curriculum"'));
});

test("examResultHTML fail banner names the bar", () => {
  const html = examResultHTML({ score: 0.5, passed: false, attempt: 1, perQuestion: [], weakSpots: [] });
  assert.ok(html.includes("50%") && html.includes("80%"));
});

test("failed result with weak spots offers Fix the gaps; passed result does not", () => {
  const failed = { score: 0.5, passed: false, weakSpots: [{ lessonId: "l1", lessonTitle: "L", objectives: [] }], perQuestion: [] };
  assert.ok(examResultHTML(failed).includes('data-action="fix-gaps"'));
  const passed = { score: 0.9, passed: true, weakSpots: [], perQuestion: [] };
  assert.ok(!examResultHTML(passed).includes('data-action="fix-gaps"'));
});

test("failed result with weak spots replaces retake with the unlock note", () => {
  const failed = { score: 0.5, passed: false, perQuestion: [],
    weakSpots: [{ lessonId: "l1", lessonTitle: "L", objectives: [] }] };
  const html = examResultHTML(failed);
  assert.ok(html.includes('data-action="fix-gaps"'));
  assert.ok(!html.includes('data-action="retake-exam"'));
  assert.ok(html.includes("Retake unlocks after the gap review."));
});

test("passed results and fails without weak spots keep the retake button", () => {
  const passed = examResultHTML({ score: 0.9, passed: true, perQuestion: [], weakSpots: [] });
  assert.ok(passed.includes('data-action="retake-exam"'));
  assert.ok(!passed.includes("Retake unlocks after the gap review."));
  const noSpots = examResultHTML({ score: 0.5, passed: false, perQuestion: [], weakSpots: [] });
  assert.ok(noSpots.includes('data-action="retake-exam"'));   // nothing to remediate: not gated
});
