import { test } from "node:test";
import assert from "node:assert/strict";
import { gradeCheck, checksHTML } from "../src/views/checks.js";

test("gradeCheck mcq compares the selected index", () => {
  const c = { type: "mcq", choices: ["a", "b"], answer: 1, explanation: "why" };
  assert.equal(gradeCheck(c, 1).correct, true);
  assert.equal(gradeCheck(c, 0).correct, false);
  assert.equal(gradeCheck(c, "1").correct, true); // string index from the DOM
});

test("gradeCheck fill matches case/space-insensitively", () => {
  const c = { type: "fill", answer: "Four", explanation: "why" };
  assert.equal(gradeCheck(c, "  four ").correct, true);
  assert.equal(gradeCheck(c, "five").correct, false);
});

test("gradeCheck fill ignores internal spacing and dash/minus variants", () => {
  const c = { type: "fill", answer: "-70 mV", explanation: "why" };
  assert.equal(gradeCheck(c, "-70mV").correct, true); // the reported bug: missing space
  assert.equal(gradeCheck(c, "−70 mV").correct, true); // typographic minus (U+2212)
  assert.equal(gradeCheck(c, "–70mV").correct, true); // en dash + no space
  assert.equal(gradeCheck(c, "-70 mv").correct, true); // case
});

test("gradeCheck fill stays strict about sign and token", () => {
  const c = { type: "fill", answer: "-70 mV", explanation: "why" };
  assert.equal(gradeCheck(c, "70 mV").correct, false); // wrong sign is still wrong
  assert.equal(gradeCheck(c, "-70 mA").correct, false); // wrong unit is still wrong
});

test("checksHTML renders mcq choices and a fill input", () => {
  const html = checksHTML(
    [{ type: "mcq", prompt: "pick", choices: ["a", "b"], answer: 0, explanation: "e" },
     { type: "fill", prompt: "type", answer: "x", explanation: "e" }],
    { checkAnswers: {}, checkResults: {} },
  );
  assert.match(html, /data-check="0"[^>]*data-choice="0"/);
  assert.match(html, /data-check-input="1"/);
  assert.match(html, /Check your understanding/);
});

test("checksHTML shows the explanation and marker once answered", () => {
  const html = checksHTML(
    [{ type: "fill", prompt: "type", answer: "x", explanation: "because x" }],
    { checkAnswers: { 0: "x" }, checkResults: { 0: { correct: true } } },
  );
  assert.match(html, /because x/);
  assert.match(html, /Correct/);
});

test("checksHTML renders nothing for no checks", () => {
  assert.equal(checksHTML([], {}), "");
  assert.equal(checksHTML(undefined, {}), "");
});

test("checksHTML shows the fresh-items heading when state.freshItems is set", () => {
  const html = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {}, freshItems: true },
  );
  assert.match(html, /Fresh review questions/);
  assert.doesNotMatch(html, /Check your understanding/);
});

test("checksHTML keeps the default heading when freshItems is absent or false", () => {
  const absent = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {} },
  );
  assert.match(absent, /Check your understanding/);
  const falsy = checksHTML(
    [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
    { checkAnswers: {}, checkResults: {}, freshItems: false },
  );
  assert.equal(absent, falsy);
});
