import { test } from "node:test";
import assert from "node:assert/strict";
import { homeHTML } from "../src/views/home.js";

const ML = {
  id: "machine-learning",
  title: "Machine Learning",
  subtitle: "From fundamentals to neural networks",
  progress: { done: 1, total: 4, pct: 25 },
  nextLesson: { id: "ml-m3-l2", title: "Backpropagation, intuitively", moduleTitle: "Neural Networks" },
  reviewsDue: 0,
};

test("home renders a card per course with progress and continue", () => {
  const html = homeHTML([ML]);
  assert.match(html, /data-course="machine-learning"/);
  assert.match(html, /Machine Learning/);
  assert.match(html, /1 of 4 lessons/);
  assert.match(html, /width:25%/);
  assert.match(html, /Continue/);
});

test("home always shows the add-course card", () => {
  assert.match(homeHTML([]), /data-action="add-course"/);
});
