import { test } from "node:test";
import assert from "node:assert/strict";
import { timerView, TOTAL_SECONDS } from "../src/timer.js";

test("at start: warm-up active, nothing filled", () => {
  const v = timerView(0);
  assert.deepEqual(v.fills, [0, 0, 0]);
  assert.equal(v.activePhaseIndex, 0);
  assert.equal(v.clock, "0:00 / 90:00");
  assert.match(v.statusLabel, /Warm-up/);
});

test("at 30 min: peak active, warm-up full, peak part-filled", () => {
  const v = timerView(30 * 60);
  assert.equal(v.activePhaseIndex, 1);
  assert.equal(v.fills[0], 1);
  assert.ok(v.fills[1] > 0 && v.fills[1] < 1);
  assert.equal(v.fills[2], 0);
  assert.equal(v.clock, "30:00 / 90:00");
});

test("at 89 min: cool-down active", () => {
  const v = timerView(89 * 60);
  assert.equal(v.activePhaseIndex, 2);
  assert.equal(v.fills[0], 1);
  assert.equal(v.fills[1], 1);
});

test("at/after total: complete", () => {
  const v = timerView(TOTAL_SECONDS);
  assert.deepEqual(v.fills, [1, 1, 1]);
  assert.match(v.statusLabel, /complete/i);
});
