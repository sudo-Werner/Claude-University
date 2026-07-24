import { test } from "node:test";
import assert from "node:assert/strict";
import { SVG_ANIM_SANITIZE_CONFIG } from "../src/figureconfig.js";

// Plain object-shape assertions -- no DOMPurify, no browser. This is the
// client half of the two-layer SVG security (server half: backend/figures.py);
// it previously had zero automated coverage.
test("SVG_ANIM_SANITIZE_CONFIG forbids the dangerous tags: script/style/foreignObject/use/a", () => {
  const { FORBID_TAGS } = SVG_ANIM_SANITIZE_CONFIG;
  assert.ok(FORBID_TAGS.includes("script"));
  assert.ok(FORBID_TAGS.includes("style"));
  assert.ok(FORBID_TAGS.includes("foreignObject"));
  assert.ok(FORBID_TAGS.includes("use"));
  assert.ok(FORBID_TAGS.includes("a"));
});

test("SVG_ANIM_SANITIZE_CONFIG keeps the animation-tag forbids", () => {
  const { FORBID_TAGS } = SVG_ANIM_SANITIZE_CONFIG;
  assert.ok(FORBID_TAGS.includes("animate"));
  assert.ok(FORBID_TAGS.includes("set"));
  assert.ok(FORBID_TAGS.includes("mpath"));
});

test("SVG_ANIM_SANITIZE_CONFIG forbids href/xlink:href/style attributes", () => {
  const { FORBID_ATTR } = SVG_ANIM_SANITIZE_CONFIG;
  assert.ok(FORBID_ATTR.includes("href"));
  assert.ok(FORBID_ATTR.includes("xlink:href"));
  assert.ok(FORBID_ATTR.includes("style"));
});

test("SVG_ANIM_SANITIZE_CONFIG opts into DOMPurify's svg profile", () => {
  assert.equal(SVG_ANIM_SANITIZE_CONFIG.USE_PROFILES.svg, true);
});
