import { test } from "node:test";
import assert from "node:assert/strict";
import { genFeedHTML, genLineHTML, genErrorHTML, genChipHTML, formatElapsed } from "../src/views/genfeed.js";

test("genFeedHTML includes escaped title, feed slot, elapsed slot", () => {
  const html = genFeedHTML("<b>Cells</b>");
  assert.ok(html.includes("&lt;b&gt;Cells&lt;/b&gt;"));
  assert.ok(html.includes("data-gen-feed"));
  assert.ok(html.includes("data-gen-elapsed"));
  assert.ok(!html.includes("<b>Cells</b>"));
});

test("genLineHTML sets the kind class and escapes text", () => {
  const html = genLineHTML({ kind: "search", text: "Searching: <x>" });
  assert.ok(html.includes("gen-search"));
  assert.ok(html.includes("Searching: &lt;x&gt;"));
});

test("genErrorHTML shows the message and a retry action", () => {
  const html = genErrorHTML("It broke");
  assert.ok(html.includes("It broke"));
  assert.ok(html.includes('data-action="gen-retry"'));
});

test("genChipHTML covers empty, running, done, error", () => {
  assert.equal(genChipHTML(null), "");
  assert.ok(genChipHTML({ status: "running", elapsed: 125 }).includes("2:05"));
  assert.ok(genChipHTML({ status: "done" }).includes('data-action="gen-open"'));
  assert.ok(genChipHTML({ status: "error" }).includes('data-action="gen-open"'));
});

test("formatElapsed renders m:ss", () => {
  assert.equal(formatElapsed(0), "0:00");
  assert.equal(formatElapsed(65), "1:05");
  assert.equal(formatElapsed(600.7), "10:00");
});
