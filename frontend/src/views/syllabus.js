import { esc } from "../escape.js";

function objList(objectives) {
  const items = (objectives || [])
    .filter((o) => o && o.text)
    .map((o) => `<li>${esc(o.text)} <span class="obj-tag">${esc(o.bloom || "")}</span></li>`)
    .join("");
  return items ? `<ul class="obj-list">${items}</ul>` : "";
}

// Item D: the compiled prereq graph's first consumer. Plain text only — the
// syllabus renders pre-enrolment (and in the revision review), so no links.
function buildsOnLine(lesson, titles) {
  const names = (lesson.prereqs || []).map((id) => titles[id]).filter(Boolean);
  return names.length ? `<div class="syl-builds">Builds on: ${names.map(esc).join(", ")}</div>` : "";
}

function moduleBlock(module, titles) {
  const lessons = (module.lessons || [])
    .map((l) => `<div class="syl-lesson"><div class="syl-lesson-title">${esc(l.title || "")}</div>${objList(l.objectives)}${buildsOnLine(l, titles)}</div>`)
    .join("");
  return `<section class="syl-module"><h3>${esc(module.title || "")}</h3>${lessons}</section>`;
}

function sourceList(sources) {
  const items = (sources || [])
    .filter((s) => s && typeof s.url === "string" && /^https?:\/\//.test(s.url))
    .map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a> <span class="src-type">${esc(s.type || "")}</span></li>`)
    .join("");
  return items ? `<ul class="src-list">${items}</ul>` : "<div class='muted'>No sources retrieved.</div>";
}

export function syllabusHTML(course, { actions = true } = {}) {
  const skills = (course.skills || []).map((s) => `<li>${esc(s)}</li>`).join("");
  const outcomes = objList(course.outcomes);
  const level = course.level || {};
  const titles = {};
  (course.modules || []).forEach((m) => (m.lessons || []).forEach((l) => { titles[l.id] = l.title || ""; }));
  const modules = (course.modules || []).map((m) => moduleBlock(m, titles)).join("");
  return (
    `<div class="syllabus">` +
    `<div class="eyebrow">PROPOSED COURSE</div>` +
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
