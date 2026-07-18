import { test } from "node:test";
import assert from "node:assert/strict";
import { autoGrowTextarea } from "../src/autogrow.js";

// A minimal element mock: real DOM scrollHeight depends on layout, which node
// doesn't have — so scrollHeight is a fixed stand-in a real browser would compute.
function fakeTextarea(scrollHeight) {
  return { style: { height: "" }, scrollHeight };
}

test("autoGrowTextarea sets height to the element's scrollHeight", () => {
  const el = fakeTextarea(120);
  autoGrowTextarea(el);
  assert.equal(el.style.height, "120px");
});

test("autoGrowTextarea resets height to auto BEFORE reading scrollHeight", () => {
  // In a real browser, scrollHeight only shrinks back down after a stale
  // taller inline height is cleared first — reading it too early (or skipping
  // the reset) would freeze the box at its tallest-ever size. Spy on every
  // assignment to prove the order: "auto" is set before the final value.
  const heights = [];
  const el = {
    style: {
      set height(v) { heights.push(v); },
      get height() { return heights[heights.length - 1]; },
    },
    scrollHeight: 60,
  };
  autoGrowTextarea(el);
  assert.deepEqual(heights, ["auto", "60px"]);
});
