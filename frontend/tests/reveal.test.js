import { test } from "node:test";
import assert from "node:assert/strict";
import { solutionState } from "../src/reveal.js";

test("empty answer cannot reveal", () => {
  assert.equal(solutionState({ answer: "", revealed: false }), "locked");
  assert.equal(solutionState({ answer: "   ", revealed: false }), "locked");
});

test("non-empty answer is ready", () => {
  assert.equal(solutionState({ answer: "w - 0.04", revealed: false }), "ready");
});

test("revealed is shown", () => {
  assert.equal(solutionState({ answer: "w - 0.04", revealed: true }), "shown");
});
