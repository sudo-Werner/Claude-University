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
  // This proves only the CALL ORDER: "auto" is written before the final value.
  // It does NOT prove the real-browser shrink behavior that order exists for —
  // this mock's scrollHeight is a fixed constant, not reactive to style writes
  // the way a real layout engine's is, so that part needs live verification.
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
