import { esc } from "../escape.js";

// Misconception profile (charter Tier 2 item 7): a read-only, delete-only-
// editable per-course list of misconceptions the teach-it-to-Claude and
// explain-it-back graders have named, grouped by lesson (most recent lesson
// first). The excerpt is the learner's OWN words that triggered the entry —
// shown distinctly from the claim itself so it can be judged against it
// (DeepTutor's "nothing in your profile is unaccountable" trust model).

function groupByLesson(entries) {
  const order = [];
  const byLesson = new Map();
  for (const e of entries) {
    if (!byLesson.has(e.lessonId)) {
      byLesson.set(e.lessonId, { lessonTitle: e.lessonTitle, items: [] });
      order.push(e.lessonId);
    }
    byLesson.get(e.lessonId).items.push(e);
  }
  return order.map((lessonId) => ({ lessonId, ...byLesson.get(lessonId) }));
}

function entryHTML(e) {
  return (
    `<div class="mc-entry">` +
    `<div class="mc-text">${esc(e.text)}</div>` +
    `<div class="mc-excerpt">"${esc(e.excerpt)}"</div>` +
    `<button class="mc-delete" data-action="delete-misconception" data-entry="${esc(e.id)}">Remove</button>` +
    `</div>`
  );
}

function lessonGroupHTML(group) {
  const items = group.items.map(entryHTML).join("");
  return (
    `<div class="mc-lesson">` +
    `<div class="mc-ltitle">${esc(group.lessonTitle)}</div>${items}</div>`
  );
}

export function misconceptionsHTML(data) {
  const entries = (data && data.entries) || [];
  const head = `<div class="greeting"><h1>Misconceptions</h1><span>What your teaching and explanations have shown</span></div>`;
  if (!entries.length) {
    return (
      `<div class="misconceptions">${head}` +
      `<div class="card"><div class="prompt">Nothing here yet — teach a concept to Claude or explain ` +
      `one back, and anything it flags will show up here.</div></div>` +
      `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`
    );
  }
  const groups = groupByLesson(entries).map(lessonGroupHTML).join("");
  return (
    `<div class="misconceptions">${head}<section class="card">${groups}</section>` +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`
  );
}
