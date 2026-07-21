import { esc } from "../escape.js";

// The live-generation screen: everything in it is a REAL event from the model's
// stream (searches, pages read, thinking, narration) or a pipeline stage marker.
// Never invent activity here — the whole point is replacing the fake cycled
// status with the truth.

export function formatElapsed(seconds) {
  const s = Math.floor(seconds || 0);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function genFeedHTML(title) {
  return (
    `<div class="card lesson gen-card">` +
    `<div class="gen-head"><span class="load-dot"></span>` +
    `<span class="gen-title">Generating: ${esc(title)}</span>` +
    `<span class="gen-elapsed" data-gen-elapsed></span></div>` +
    `<div class="gen-feed" data-gen-feed></div>` +
    `<p class="gen-note">This takes a few minutes. You can do reviews meanwhile or ` +
    `close the app entirely — generation continues on the server and the lesson ` +
    `will be waiting.</p>` +
    `</div>`
  );
}

export function genLineHTML(ev) {
  return `<div class="gen-line gen-${esc(ev.kind)}">${esc(ev.text)}</div>`;
}

export function genErrorHTML(message) {
  return (
    `<div class="card lesson gen-card">` +
    `<p class="gen-error">${esc(message)}</p>` +
    `<button class="gen-retry" data-action="gen-retry">Try again</button>` +
    `</div>`
  );
}

export function genChipHTML(job) {
  if (!job) return "";
  if (job.status === "done") {
    return `<button class="gen-chip gen-chip-ready" data-action="gen-open">Lesson ready — open</button>`;
  }
  if (job.status === "error") {
    return `<button class="gen-chip gen-chip-err" data-action="gen-open">Generation failed — retry</button>`;
  }
  return `<span class="gen-chip">Generating lesson… ${esc(formatElapsed(job.elapsed))}</span>`;
}
