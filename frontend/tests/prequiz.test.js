import { test } from "node:test";
import assert from "node:assert/strict";
import { preQuizHTML } from "../src/views/prequiz.js";

const MCQ = { type: "mcq", prompt: "Best guess?", choices: ["A", "B"], answer: 1, explanation: "B because." };
const FILL = { type: "fill", prompt: "Name it", answer: "x", explanation: "It is x." };

test("prequiz mcq renders choices and no feedback before the attempt", () => {
  const html = preQuizHTML(MCQ, {});
  assert.match(html, /BEFORE YOU START/);
  assert.match(html, /Best guess\?/);
  assert.match(html, /data-pq-choice="0"/);
  assert.match(html, /data-pq-choice="1"/);
  assert.doesNotMatch(html, /pq-continue/);
});

test("prequiz mcq after attempt marks correct/wrong, shows explanation and continue", () => {
  const html = preQuizHTML(MCQ, { preQuiz: { answer: 0, result: { correct: false } } });
  assert.match(html, /choice correct/);
  assert.match(html, /choice wrong/);
  assert.match(html, /B because\./);
  assert.match(html, /data-action="pq-continue"/);
  assert.match(html, /disabled/);
});

test("prequiz fill renders input then echoes the escaped answer", () => {
  const before = preQuizHTML(FILL, {});
  assert.match(before, /data-pq-input/);
  assert.match(before, /data-action="pq-submit"/);
  const after = preQuizHTML(FILL, { preQuiz: { answer: "<b>me</b>", result: { correct: true } } });
  assert.doesNotMatch(after, /<b>me<\/b>/);
  assert.match(after, /&lt;b&gt;me&lt;\/b&gt;/);
  assert.match(after, /It is x\./);
});
