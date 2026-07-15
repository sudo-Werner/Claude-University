const LABELS = { attempted: "Attempted", familiar: "Familiar", proficient: "Proficient", mastered: "Mastered" };

const CHECK = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L19 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

import { esc } from "../escape.js";

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

function examRow(examKey, exams, label) {
  const s = exams && exams[examKey];
  let badge = `<span class="exam-status">Not taken</span>`;
  if (s && s.passed) {
    badge = `<span class="exam-status passed">Passed — best ${Math.round(s.bestScore * 100)}%</span>`;
  } else if (s && s.attempts) {
    badge = `<span class="exam-status failed">Best ${Math.round(s.bestScore * 100)}% (${s.attempts} attempt${s.attempts === 1 ? "" : "s"})</span>`;
  }
  const cta = s && s.attempts ? "Retake" : "Take exam";
  return (
    `<button class="c-exam" data-exam="${esc(examKey)}">` +
    `<span class="c-etitle">${esc(label)}</span>${badge}` +
    `<span class="c-ecta">${cta} →</span></button>`
  );
}

function moduleBlock(module, mastery, currentId, exams) {
  const p = moduleProgress(module, mastery);
  const rows = (module.lessons || []).map((l) => lessonRow(l, mastery, currentId)).join("");
  // #1: once every lesson in the module is done, offer its real-world capstone.
  const complete = p.total > 0 && p.done === p.total;
  const capstone = complete
    ? `<button class="c-capstone" data-capstone="${esc(module.id)}">Real-world connections →</button>`
    : "";
  return (
    `<section class="c-module">` +
    `<div class="c-mhead"><span class="c-mtitle">${esc(module.title)}</span>` +
    `<span class="c-mprog">${p.done}/${p.total}</span></div>` +
    `<div class="c-lessons">${rows}</div>${capstone}${examRow(module.id, exams, "Module exam")}</section>`
  );
}

export function curriculumHTML(manifest, mastery, currentId, exams, coursePassed) {
  const m = mastery || {};
  const flat = flatten(manifest);
  const done = flat.filter((l) => m[l.id]).length;
  const modules = (manifest.modules || []).map((mod) => moduleBlock(mod, m, currentId, exams)).join("");
  // #1: when the whole course is done, offer a course-wide real-world capstone.
  const courseDone = flat.length > 0 && done === flat.length;
  const courseCapstone = courseDone
    ? `<button class="c-capstone course" data-capstone="course">Real-world connections for the whole course →</button>`
    : "";
  return (
    `<div class="curriculum">` +
    `<div class="greeting"><h1>${esc(manifest.title)}</h1>` +
    `<span>${coursePassed ? '<span class="course-passed">Course passed</span> ' : ""}${done} of ${flat.length} lessons</span></div>` +
    `${modules}${courseCapstone}${examRow("final", exams, "Final exam")}</div>`
  );
}
