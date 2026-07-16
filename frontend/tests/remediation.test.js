import test from "node:test";
import assert from "node:assert/strict";
import { remediationHTML, flatPractice } from "../src/views/remediation.js";
import { remediationComplete, lessonIndexFrom } from "../src/views/remediation.js";

const SESSION = {
  examKey: "m1", attempt: 1,
  gaps: [
    { lessonId: "c1-l1", lessonTitle: "Lesson <1>", objectives: ["obj <a>"],
      explanationHtml: "<p>An <em>analogy</em></p>",
      practice: [
        { type: "mcq", prompt: "<p>Pick</p>", choices: ["<code>a</code>", "b"], answer: 0, explanation: "why" },
        { type: "fill", prompt: "Blank?", answer: "w", explanation: "because" },
      ],
      apply: { prompt: "<p>A <em>novel</em> scenario</p>", modelAnswer: "Covers <strong>X</strong>" } },
    { lessonId: "c1-l2", lessonTitle: "L2", objectives: [],
      explanationHtml: "<p>Contrast</p>",
      practice: [
        { type: "mcq", prompt: "<p>Q2</p>", choices: ["x", "y"], answer: 1, explanation: "e" },
        { type: "mcq", prompt: "<p>Q3</p>", choices: ["x", "y"], answer: 0, explanation: "e" },
      ] },
  ],
};

const EMPTY = { answers: {}, results: {}, applyAnswers: {}, applyResults: {}, applyBusy: {} };

test("flatPractice assigns global indices with the right lessonIds", () => {
  const flat = flatPractice(SESSION);
  assert.equal(flat.length, 4);
  assert.equal(flat[0].lessonId, "c1-l1");
  assert.equal(flat[2].lessonId, "c1-l2");
  assert.equal(flat[3].check.prompt, "<p>Q3</p>");
});

test("remediationHTML renders raw explanations, escaped titles, namespaced attrs", () => {
  const html = remediationHTML(SESSION, { ...EMPTY });
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
  const html = remediationHTML(SESSION, { ...EMPTY, answers: { 0: 1 }, results: { 0: { correct: false } } });
  assert.ok(html.includes("Not quite"));
  assert.ok(html.includes("choice correct") && html.includes("choice wrong"));
});

const MANIFEST = { modules: [
  { id: "m1", title: "Mod", lessons: [
    { id: "c1-l0", title: "Roots <b>", prereqs: [] },
    { id: "c1-l1", title: "Lesson One", prereqs: ["c1-l0", "ghost"] },
    { id: "c1-l2", title: "Lesson Two", prereqs: [] },
  ] },
] };

test("apply block renders for gaps that have one, with server HTML raw", () => {
  const html = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(html.includes("<p>A <em>novel</em> scenario</p>"));       // raw
  assert.ok(html.includes('data-rem-apply="0"'));                      // textarea for gap 0
  assert.ok(html.includes('data-action="rem-apply"') && html.includes('data-gap="0"'));
  assert.ok(!html.includes('data-gap="1"'));                           // legacy gap: no block
  assert.ok(!html.includes("Covers <strong>X</strong>"));              // model answer hidden pre-grade
});

test("graded apply shows verdict, note and model answer, and locks the input", () => {
  const state = { ...EMPTY,
    applyAnswers: { 0: "my answer" },
    applyResults: { 0: { verdict: "close", note: "Nearly <em>there</em>", modelAnswer: "Covers <strong>X</strong>" } } };
  const html = remediationHTML(SESSION, state, MANIFEST);
  assert.ok(html.includes("Almost there"));
  assert.ok(html.includes("Nearly <em>there</em>"));                   // note raw (server-sanitized)
  assert.ok(html.includes("Covers <strong>X</strong>"));               // model answer revealed
  assert.ok(/data-rem-apply="0"[^>]*disabled/.test(html) || /disabled[^>]*data-rem-apply="0"/.test(html));
});

test("remediationComplete needs all practice plus every present apply", () => {
  const allPractice = { 0: { correct: true }, 1: { correct: true }, 2: { correct: true }, 3: { correct: true } };
  assert.equal(remediationComplete(SESSION, { ...EMPTY }), false);
  assert.equal(remediationComplete(SESSION, { ...EMPTY, results: allPractice }), false);   // apply missing
  assert.equal(remediationComplete(SESSION, { ...EMPTY, results: allPractice,
    applyResults: { 0: { verdict: "correct" } } }), true);
  const legacy = { ...SESSION, gaps: SESSION.gaps.map((g) => { const { apply, ...rest } = g; return rest; }) };
  assert.equal(remediationComplete(legacy, { ...EMPTY, results: allPractice }), true);      // no apply anywhere
});

test("retake button is disabled with unlock copy until the session is complete", () => {
  const locked = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(/data-action="retake-exam"[^>]*disabled/.test(locked));
  assert.ok(locked.includes("Answer everything above to unlock the retake"));
  const done = { ...EMPTY,
    results: { 0: { correct: true }, 1: { correct: true }, 2: { correct: true }, 3: { correct: true } },
    applyResults: { 0: { verdict: "correct" } } };
  const open = remediationHTML(SESSION, done, MANIFEST);
  assert.ok(!/data-action="retake-exam"[^>]*disabled/.test(open));
  assert.ok(open.includes("Retake with fresh questions"));
});

test("builds-on chips resolve prereq titles, escape them, and skip unknown ids", () => {
  const html = remediationHTML(SESSION, { ...EMPTY }, MANIFEST);
  assert.ok(html.includes("Builds on:"));
  assert.ok(html.includes('data-lesson="c1-l0"'));
  assert.ok(html.includes("Roots &lt;b&gt;"));                         // title escaped
  assert.ok(!html.includes("ghost"));                                  // unknown id skipped
  const bare = remediationHTML(SESSION, { ...EMPTY });                 // no manifest: no crash, no chips
  assert.ok(!bare.includes("Builds on:"));
});

test("lessonIndexFrom maps ids to titles and prereqs, tolerating null", () => {
  const idx = lessonIndexFrom(MANIFEST);
  assert.deepEqual(idx["c1-l1"], { title: "Lesson One", prereqs: ["c1-l0", "ghost"] });
  assert.deepEqual(lessonIndexFrom(null), {});
});
