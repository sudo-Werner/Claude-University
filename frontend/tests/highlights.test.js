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

test("findNthOccurrence is case-insensitive (CSS text-transform regression)", () => {
  // Confirmed live: a heading styled with CSS text-transform:uppercase makes
  // Selection.toString() return uppercase text while the underlying DOM nodeValue
  // stays mixed-case -- a highlight created inside such a heading must still match.
  const text = "Worked example: body temperature rises here";
  assert.deepEqual(findNthOccurrence(text, "TEMPERATURE", 0), [21, 32]);
  assert.deepEqual(findNthOccurrence(text, "temperature", 0), [21, 32]);
  assert.deepEqual(findNthOccurrence(text, "TeMpErAtUrE", 0), [21, 32]);
});

test("countOccurrencesBefore is case-insensitive and stays consistent with findNthOccurrence", () => {
  const text = "The Cat sat near the cat bowl and the CAT slept";
  // Three occurrences of "cat" regardless of case: "Cat"(4), "cat"(22), "CAT"(39).
  const [firstStart] = findNthOccurrence(text, "cat", 0);
  const [secondStart] = findNthOccurrence(text, "CAT", 1);
  assert.equal(countOccurrencesBefore(text, "cat", firstStart), 0);
  assert.equal(countOccurrencesBefore(text, "CAT", secondStart), 1);
});

test("findNthOccurrence never corrupts offsets on the one length-changing lowercase case", () => {
  // U+0130 (Turkish capital dotted I) is the sole Unicode code point where
  // toLowerCase() changes a string's length ("İ" -> "i" + combining dot, 1->2 chars).
  // Falls back to an exact-case match rather than risk offsets computed against a
  // longer lowercased string being applied to the original (shorter) text.
  const text = "before İstanbul after";
  assert.deepEqual(findNthOccurrence(text, "İstanbul", 0), [7, 15]);
  // The exact-case fallback means a differently-cased search for this one substring
  // legitimately won't match -- an accepted, documented trade-off, not a silent bug.
  assert.equal(findNthOccurrence(text, "istanbul", 0), null);
});
