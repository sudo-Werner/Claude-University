import { esc } from "../escape.js";

// Prior-knowledge activation (design doc, 2026-07-16): asked once, right before a
// lesson is generated for the first time. openLesson (app.js) paints this in place
// of the loading skeleton when the status check reports generated: false.
export function activateHTML(title) {
  return (
    `<section class="card"><span class="eyebrow">BEFORE YOU START</span>` +
    `<h2 class="session-topic">${esc(title)}</h2>` +
    `<div class="check-q">What do you already know — or suspect — about this topic?</div>` +
    `<div class="pq-lead">A sentence or two is plenty. The lesson will build on your answer.</div>` +
    `<textarea data-field="pk-text" maxlength="2000" placeholder="Type what you know or suspect…"></textarea>` +
    `<button class="btn-primary" data-action="pk-start" style="margin-top:12px">Start lesson</button>` +
    `<button class="btn-secondary" data-action="pk-skip" style="margin-top:8px">Skip</button>` +
    `</section>`
  );
}
