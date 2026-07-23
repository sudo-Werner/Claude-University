import { test } from "node:test";
import assert from "node:assert/strict";
import { clampSpeed, nextTime, SPEED_MIN, SPEED_MAX } from "../src/figureplayer.js";

test("clampSpeed clamps to [0.25, 2.5] and defaults non-finite to 1", () => {
  assert.equal(clampSpeed(0.1), SPEED_MIN);
  assert.equal(clampSpeed(9), SPEED_MAX);
  assert.equal(clampSpeed(1.5), 1.5);
  assert.equal(clampSpeed("x"), 1);
});

test("nextTime advances by dt*speed and never goes negative", () => {
  assert.equal(nextTime(0, 1, 1), 1);
  assert.equal(nextTime(2, 0.5, 2.5), 2 + 0.5 * 2.5);
  assert.equal(nextTime(0, -1, 1), 0); // negative dt clamped
});
