import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSSELines } from "../src/chat.js";

test("parseSSELines extracts complete events and keeps the partial tail", () => {
  const buffer =
    "event: delta\ndata: Hi\n\n" +
    "event: proposal\ndata: {\"title\":\"X\"}\n\n" +
    "event: done\ndata: {}";  // no trailing blank line yet
  const { events, rest } = parseSSELines(buffer);
  assert.deepEqual(events[0], { event: "delta", data: "Hi" });
  assert.deepEqual(events[1], { event: "proposal", data: '{"title":"X"}' });
  assert.equal(events.length, 2);          // "done" is incomplete
  assert.match(rest, /event: done/);       // retained for the next chunk
});

test("parseSSELines returns no events for an empty buffer", () => {
  assert.deepEqual(parseSSELines(""), { events: [], rest: "" });
});

test("parseSSELines joins multiple data lines in one frame (multi-line delta)", () => {
  const { events } = parseSSELines("event: delta\ndata: Line one.\ndata: Line two.\n\n");
  assert.deepEqual(events[0], { event: "delta", data: "Line one.\nLine two." });
});
