const LABELS = { attempted: "Attempted", familiar: "Familiar", proficient: "Proficient", mastered: "Mastered" };

const CHECK = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L19 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function flatten(manifest) {
  const out = [];
  (manifest.modules || []).forEach((m) => (m.lessons || []).forEach((l) => out.push(l)));
  return out;
}

export function lessonStatus(lessonId, mastery, currentId) {
  if (mastery && mastery[lessonId]) return "done";
  if (lessonId === currentId) return "current";
  return "todo";
}

export function moduleProgress(module, mastery) {
  const lessons = module.lessons || [];
  const done = lessons.filter((l) => mastery && mastery[l.id]).length;
  return { done, total: lessons.length };
}

function lessonRow(lesson, mastery, currentId) {
  const status = lessonStatus(lesson.id, mastery, currentId);
  const level = mastery && mastery[lesson.id];
  const badge = level ? `<span class="c-badge ${level}">${LABELS[level]}</span>` : "";
  const inner = status === "done" ? CHECK : "";
  return (
    `<button class="c-lesson ${status}" data-lesson="${esc(lesson.id)}">` +
    `<span class="c-mark ${status}">${inner}</span>` +
    `<span class="c-ltitle">${esc(lesson.title)}</span>${badge}</button>`
  );
}

function moduleBlock(module, mastery, currentId) {
  const p = moduleProgress(module, mastery);
  const rows = (module.lessons || []).map((l) => lessonRow(l, mastery, currentId)).join("");
  return (
    `<section class="c-module">` +
    `<div class="c-mhead"><span class="c-mtitle">${esc(module.title)}</span>` +
    `<span class="c-mprog">${p.done}/${p.total}</span></div>` +
    `<div class="c-lessons">${rows}</div></section>`
  );
}

export function curriculumHTML(manifest, mastery, currentId) {
  const m = mastery || {};
  const flat = flatten(manifest);
  const done = flat.filter((l) => m[l.id]).length;
  const modules = (manifest.modules || []).map((mod) => moduleBlock(mod, m, currentId)).join("");
  return (
    `<div class="curriculum">` +
    `<div class="greeting"><h1>${esc(manifest.title)}</h1>` +
    `<span>${done} of ${flat.length} lessons</span></div>${modules}</div>`
  );
}
