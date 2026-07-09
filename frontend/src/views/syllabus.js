import { esc } from "../escape.js";

function objList(objectives) {
  const items = (objectives || [])
    .filter((o) => o && o.text)
    .map((o) => `<li>${esc(o.text)} <span class="obj-tag">${esc(o.bloom || "")}</span></li>`)
    .join("");
  return items ? `<ul class="obj-list">${items}</ul>` : "";
}

function moduleBlock(module) {
  const lessons = (module.lessons || [])
    .map((l) => `<div class="syl-lesson"><div class="syl-lesson-title">${esc(l.title || "")}</div>${objList(l.objectives)}</div>`)
    .join("");
  return `<section class="syl-module"><h3>${esc(module.title || "")}</h3>${lessons}</section>`;
}

function sourceList(sources) {
  const items = (sources || [])
    .filter((s) => s && s.url)
    .map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a> <span class="src-type">${esc(s.type || "")}</span></li>`)
    .join("");
  return items ? `<ul class="src-list">${items}</ul>` : "<div class='muted'>No sources retrieved.</div>";
}

export function syllabusHTML(course, { actions = true } = {}) {
  const skills = (course.skills || []).map((s) => `<li>${esc(s)}</li>`).join("");
  const outcomes = objList(course.outcomes);
  const level = course.level || {};
  const modules = (course.modules || []).map(moduleBlock).join("");
  return (
    `<div class="syllabus">` +
    `<div class="eyebrow">PROPOSED PROGRAM</div>` +
    `<h1 class="session-topic">${esc(course.title || "")}</h1>` +
    `<div class="session-sub">${esc(course.subtitle || "")}</div>` +
    `<div class="syl-badges">` +
      `<span class="level-badge">${esc(level.label || level.code || "")}</span>` +
      `<span class="hours-badge">~${esc(String(course.targetHours || ""))} h estimated total effort</span>` +
    `</div>` +
    (skills ? `<h2>Skills you'll gain</h2><ul class="skill-list">${skills}</ul>` : "") +
    (outcomes ? `<h2>Course outcomes</h2>${outcomes}` : "") +
    `<h2>Syllabus</h2>${modules}` +
    `<h2>Grounding sources</h2>${sourceList(course.groundingSources)}` +
    (actions
      ? `<div class="syl-actions">` +
          `<button class="btn-primary" data-action="accept-syllabus">Create this course</button>` +
          `<button class="btn-secondary" data-action="revise-syllabus" style="margin-top:8px">Request changes</button>` +
        `</div>`
      : "") +
    `</div>`
  );
}
