import { test } from "node:test";
import assert from "node:assert/strict";
import { findNthOccurrence, countOccurrencesBefore } from "../src/highlights.js";

test("findNthOccurrence finds the first occurrence", () => {
  assert.deepEqual(findNthOccurrence("the cat sat on the mat near the door", "the", 0), [0, 3]);
});

test("findNthOccurrence finds a later occurrence by index", () => {
  assert.deepEqual(findNthOccurrence("the cat sat on the mat near the door", "the", 1), [15, 18]);
});

test("findNthOccurrence returns null when there is no such occurrence", () => {
  assert.equal(findNthOccurrence("the cat sat on the mat near the door", "the", 3), null);
  assert.equal(findNthOccurrence("no match here", "xyz", 0), null);
});

test("findNthOccurrence returns null for an empty needle", () => {
  assert.equal(findNthOccurrence("some text", "", 0), null);
});

test("countOccurrencesBefore counts non-overlapping matches before a position", () => {
  const text = "the cat sat on the mat near the door";
  assert.equal(countOccurrencesBefore(text, "the", 0), 0);
  assert.equal(countOccurrencesBefore(text, "the", 15), 1);
  assert.equal(countOccurrencesBefore(text, "the", 28), 2);
  assert.equal(countOccurrencesBefore(text, "the", 37), 3);
});

test("findNthOccurrence and countOccurrencesBefore agree with each other", () => {
  const text = "aa aa aa aa";
  const [start] = findNthOccurrence(text, "aa", 2);
  assert.equal(countOccurrencesBefore(text, "aa", start), 2);
});
