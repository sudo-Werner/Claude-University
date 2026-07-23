import { test } from "node:test";
import assert from "node:assert/strict";
import { themedMermaid, MERMAID_INIT } from "../src/figuretheme.js";
import { expandFigureTokens } from "../src/views/lesson.js";

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

test("expandFigureTokens renders an svg-animated placeholder with the anim data attr", () => {
  const lesson = {
    images: [{ n: 1, type: "svg-animated", code: "<svg viewBox='0 0 8 8'/>", caption: "flow" }],
    promptHtml: "<p>Body</p>[[figure:1]]",
  };
  const { html } = expandFigureTokens(lesson.promptHtml, lesson, "demo");
  assert.ok(html.includes('data-fig-svg-anim="1"'));
  assert.ok(html.includes("lesson-fig-svg-animated"));
  assert.ok(html.includes("flow"));
});

test("expandFigureTokens drops an svg-animated entry with empty code", () => {
  const lesson = {
    images: [{ n: 1, type: "svg-animated", code: "", caption: "x" }],
    promptHtml: "[[figure:1]]",
  };
  const { html } = expandFigureTokens(lesson.promptHtml, lesson, "demo");
  assert.ok(!html.includes("lesson-fig-svg-animated"));
});
