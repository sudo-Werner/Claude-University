import test from "node:test";
import assert from "node:assert/strict";
import { remediationHTML, flatPractice } from "../src/views/remediation.js";

const SESSION = {
  examKey: "m1", attempt: 1,
  gaps: [
    { lessonId: "c1-l1", lessonTitle: "Lesson <1>", objectives: ["obj <a>"],
      explanationHtml: "<p>An <em>analogy</em></p>",
      practice: [
        { type: "mcq", prompt: "<p>Pick</p>", choices: ["<code>a</code>", "b"], answer: 0, explanation: "why" },
        { type: "fill", prompt: "Blank?", answer: "w", explanation: "because" },
      ] },
    { lessonId: "c1-l2", lessonTitle: "L2", objectives: [],
      explanationHtml: "<p>Contrast</p>",
      practice: [
        { type: "mcq", prompt: "<p>Q2</p>", choices: ["x", "y"], answer: 1, explanation: "e" },
        { type: "mcq", prompt: "<p>Q3</p>", choices: ["x", "y"], answer: 0, explanation: "e" },
      ] },
  ],
};

test("flatPractice assigns global indices with the right lessonIds", () => {
  const flat = flatPractice(SESSION);
  assert.equal(flat.length, 4);
  assert.equal(flat[0].lessonId, "c1-l1");
  assert.equal(flat[2].lessonId, "c1-l2");
  assert.equal(flat[3].check.prompt, "<p>Q3</p>");
});

test("remediationHTML renders raw explanations, escaped titles, namespaced attrs", () => {
  const html = remediationHTML(SESSION, { answers: {}, results: {} });
  assert.ok(html.includes("<p>An <em>analogy</em></p>"));            // raw
  assert.ok(html.includes("&lt;code&gt;") === false);                 // choices raw
  assert.ok(html.includes("<code>a</code>"));
  assert.ok(html.includes("Lesson &lt;1&gt;"));                       // title escaped
  assert.ok(html.includes("obj &lt;a&gt;"));                          // objective escaped
  assert.ok(html.includes('data-rq="0"') && html.includes('data-rq="3"'));
  assert.ok(html.includes('data-rq-input="1"'));                      // fill at flat index 1
  assert.ok(html.includes('data-action="retake-exam"'));
  assert.ok(html.includes('data-action="back-curriculum"'));
});

test("answered practice shows feedback and disables choices", () => {
  const html = remediationHTML(SESSION, { answers: { 0: 1 }, results: { 0: { correct: false } } });
  assert.ok(html.includes("Not quite"));
  assert.ok(html.includes("choice correct") && html.includes("choice wrong"));
});
