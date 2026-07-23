import { test } from "node:test";
import assert from "node:assert/strict";
import { themedMermaid, MERMAID_INIT } from "../src/figuretheme.js";

test("themedMermaid prepends the brand init directive", () => {
  const out = themedMermaid("flowchart TD\n A-->B");
  assert.ok(out.startsWith(MERMAID_INIT));
  assert.ok(out.includes("flowchart TD"));
});

test("themedMermaid is idempotent when an init directive is already present", () => {
  const already = '%%{init: {"theme":"dark"}}%%\nflowchart TD';
  assert.equal(themedMermaid(already), already);
});

test("MERMAID_INIT carries the brand purple and transparent background", () => {
  assert.ok(MERMAID_INIT.includes("#7c6aff"));
  assert.ok(MERMAID_INIT.includes("transparent"));
});
