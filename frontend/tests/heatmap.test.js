import { test } from "node:test";
import assert from "node:assert/strict";
import { heatmapHTML } from "../src/views/heatmap.js";

const TODAY = "2026-07-15";

// The legend swatches intentionally reuse hm-p2/hm-f2 classes, so bucket
// assertions must scope to the grid cells, not the whole rendered card.
function gridOnly(html) {
  return html.slice(html.indexOf('class="hm-grid"'), html.indexOf('class="hm-legend"'));
}

test("heatmap renders the card shell and legend even with no data", () => {
  const html = heatmapHTML({ past: {}, forecast: {} }, { today: TODAY });
  assert.match(html, /STUDY HEATMAP/);
  assert.match(html, /Studied/);
  assert.match(html, /Forecast due/);
  assert.match(html, /hm-scroll/); // horizontally-scrollable container for phone width
});

test("heatmap buckets a past study day by its event count", () => {
  const html = heatmapHTML({ past: { [TODAY]: 3 }, forecast: {} }, { today: TODAY });
  // 3 study events falls in the 3rd past bucket (thresholds 1,2,4)
  assert.match(html, /hm-p3/);
});

test("heatmap buckets a forecast day by its due count", () => {
  const tomorrow = "2026-07-16";
  const html = heatmapHTML({ past: {}, forecast: { [tomorrow]: 5 } }, { today: TODAY });
  // 5 due falls in the 3rd forecast bucket (thresholds 1,3,6)
  assert.match(html, /hm-f3/);
});

test("heatmap marks today's cell distinctly", () => {
  const html = heatmapHTML({ past: {}, forecast: {} }, { today: TODAY });
  assert.match(html, /hm-today/);
});

test("heatmap treats today's own date as past (study-so-far), not forecast", () => {
  const html = heatmapHTML({ past: { [TODAY]: 2 }, forecast: { [TODAY]: 2 } }, { today: TODAY });
  const grid = gridOnly(html);
  assert.match(grid, /hm-p2/);
  assert.doesNotMatch(grid, /hm-f2/);
});

test("heatmap days beyond the collected window render as empty (bucket 0), never crash", () => {
  const html = heatmapHTML({ past: {}, forecast: {} }, { today: TODAY });
  assert.doesNotMatch(gridOnly(html), /hm-p[1-4]|hm-f[1-4]/);
});

test("heatmap accepts a Date object for today (production default shape)", () => {
  const html = heatmapHTML({ past: {}, forecast: {} }, { today: new Date(Date.UTC(2026, 6, 15)) });
  assert.match(html, /hm-today/);
});
