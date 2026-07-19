import { esc } from "../escape.js";

// "My notes" (charter Tier 3 #20): a read-only per-course aggregate of every
// lesson's notes + highlights, grouped by lesson. Display only — no AI
// processing (that's items 7/9 territory, explicitly out of scope here).

function highlightsHTML(highlights) {
  if (!highlights.length) return "";
  const items = highlights.map((h) => `<li>${esc(h)}</li>`).join("");
  return `<ul class="mn-highlights">${items}</ul>`;
}

function lessonEntryHTML(entry) {
  const notesBlock = entry.notes ? `<div class="mn-notes">${esc(entry.notes)}</div>` : "";
  return (
    `<div class="mn-lesson">` +
    `<div class="mn-head"><span class="mn-ltitle">${esc(entry.lessonTitle)}</span>` +
    `<span class="mn-mtitle">${esc(entry.moduleTitle)}</span></div>` +
    notesBlock + highlightsHTML(entry.highlights) +
    `</div>`
  );
}

export function myNotesHTML(data) {
  const lessons = (data && data.lessons) || [];
  const head = `<div class="greeting"><h1>My notes</h1><span>Everything you've written or highlighted</span></div>`;
  if (!lessons.length) {
    return (
      `<div class="mynotes">${head}` +
      `<div class="card"><div class="prompt">Nothing here yet — jot a note or highlight a passage ` +
      `in any lesson and it will show up here.</div></div>` +
      `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`
    );
  }
  const rows = lessons.map(lessonEntryHTML).join("");
  return (
    `<div class="mynotes">${head}<section class="card">${rows}</section>` +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`
  );
}
