import { esc } from "../escape.js";

// Mirrors backend/stats.py HEATMAP_PAST_DAYS/HEATMAP_FORECAST_DAYS — the grid
// window and the API's data window must agree or the edges render empty.
const PAST_DAYS = 370;
const FORECAST_DAYS = 30;

// Hand-picked bucket boundaries for a personal-scale calendar (a handful of
// courses, not a public dashboard) — not derived from any statistical method.
const PAST_THRESHOLDS = [1, 2, 4];
const FORECAST_THRESHOLDS = [1, 3, 6];

function toISO(utcMs) {
  return new Date(utcMs).toISOString().slice(0, 10);
}

function addDaysISO(dateStr, days) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return toISO(Date.UTC(y, m - 1, d + days));
}

function weekdayISO(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat
}

function bucket(n, thresholds) {
  if (!n) return 0;
  for (let i = 0; i < thresholds.length; i++) if (n <= thresholds[i]) return i + 1;
  return thresholds.length + 1;
}

function cellHTML(dateISO, todayISO, past, forecast) {
  const isFuture = dateISO > todayISO;
  const count = isFuture ? (forecast[dateISO] || 0) : (past[dateISO] || 0);
  const b = bucket(count, isFuture ? FORECAST_THRESHOLDS : PAST_THRESHOLDS);
  const cls = `hm-cell ${isFuture ? "hm-f" : "hm-p"}${b}${dateISO === todayISO ? " hm-today" : ""}`;
  const label = isFuture
    ? (count ? `${count} review${count === 1 ? "" : "s"} forecast due ${dateISO}` : `Nothing forecast due ${dateISO}`)
    : (count ? `${count} study event${count === 1 ? "" : "s"} on ${dateISO}` : `No study activity on ${dateISO}`);
  return `<div class="${cls}" title="${esc(label)}" aria-label="${esc(label)}"></div>`;
}

export function heatmapHTML(data, { today = new Date() } = {}) {
  const past = (data && data.past) || {};
  const forecast = (data && data.forecast) || {};
  const todayISO = typeof today === "string" ? today : toISO(today.getTime());

  const rangeStart = addDaysISO(todayISO, -PAST_DAYS);
  const rangeEnd = addDaysISO(todayISO, FORECAST_DAYS);
  const gridStart = addDaysISO(rangeStart, -weekdayISO(rangeStart));
  const gridEnd = addDaysISO(rangeEnd, 6 - weekdayISO(rangeEnd));

  const cells = [];
  for (let d = gridStart; d <= gridEnd; d = addDaysISO(d, 1)) {
    cells.push(cellHTML(d, todayISO, past, forecast));
  }

  return `<section class="card heatmap-card">
    <span class="eyebrow mut">STUDY HEATMAP</span>
    <div class="hm-scroll"><div class="hm-grid">${cells.join("")}</div></div>
    <div class="hm-legend">
      <span class="hm-legend-item"><i class="hm-swatch hm-p2"></i>Studied</span>
      <span class="hm-legend-item"><i class="hm-swatch hm-f2"></i>Forecast due</span>
    </div>
  </section>`;
}
