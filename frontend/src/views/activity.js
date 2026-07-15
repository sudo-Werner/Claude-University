import { esc } from "../escape.js";

const VERBS = {
  lesson_view: "Studied",
  lesson_reviewed: "Completed",
  course_created: "Created course",
  course_revised: "Revised course",
};

function dayKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayLabel(d, now) {
  const key = dayKey(d);
  if (key === dayKey(now)) return "Today";
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (key === dayKey(yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function entryHTML(e) {
  const when = new Date(e.occurredAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const verb = VERBS[e.type] || e.type;
  const what = e.lessonTitle ? esc(e.lessonTitle) : (e.courseTitle ? esc(e.courseTitle) : "");
  const context = e.lessonTitle && e.courseTitle ? `<span class="act-course">${esc(e.courseTitle)}</span>` : "";
  const quality = e.quality ? `<span class="act-quality">rated ${esc(e.quality)}</span>` : "";
  return `<div class="act-entry"><span class="act-time">${when}</span>` +
    `<span class="act-text"><b>${verb}</b> ${what} ${context}${quality}</span></div>`;
}

export function activityHTML(entries, { now = new Date() } = {}) {
  const head = `<div class="greeting"><h1>Recent activity</h1><span>Your study log</span></div>`;
  if (!entries.length) {
    return `<div class="activity">${head}` +
      `<div class="card"><div class="prompt">Nothing here yet — study a lesson and it will show up.</div></div></div>`;
  }
  const groups = [];
  for (const e of entries) {
    const d = new Date(e.occurredAt);
    const label = dayLabel(d, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(e);
    else groups.push({ label, items: [e] });
  }
  const body = groups.map((g) =>
    `<section class="card act-day"><span class="eyebrow mut">${esc(g.label)}</span>` +
    `${g.items.map(entryHTML).join("")}</section>`,
  ).join("");
  return `<div class="activity">${head}${body}</div>`;
}
