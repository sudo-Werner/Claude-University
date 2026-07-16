import { esc } from "../escape.js";

// The global academic record. All fields are plain text -> esc() everything.

function pct(score) {
  return `${Math.round((score || 0) * 100)}%`;
}

function attemptsLabel(n) {
  return `${n} attempt${n === 1 ? "" : "s"}`;
}

function examRow(r) {
  let status = `<span class="tr-status">Not taken</span>`;
  if (r.passed) {
    status = `<span class="tr-status passed">${pct(r.bestScore)}` +
      `${r.passedOn ? ` · ${esc(r.passedOn)}` : ""}` +
      `${r.attempts ? ` · ${attemptsLabel(r.attempts)}` : ""}</span>`;
  } else if (r.attempts) {
    status = `<span class="tr-status failed">best ${pct(r.bestScore)} · ${attemptsLabel(r.attempts)}</span>`;
  }
  return `<div class="tr-row"><span class="tr-name">${esc(r.title)}</span>${status}</div>`;
}

// Capstone rows reuse the exam-row treatment; module scopes get a "Capstone:"
// prefix, the course scope's title is already "Course capstone".
function capstoneRow(r) {
  const title = r.scope === "course" ? r.title : `Capstone: ${r.title}`;
  return examRow({ ...r, title });
}

function courseBlock(c) {
  const rows = (c.modules || []).map(examRow).join("") + examRow(c.final || {}) +
    (c.capstones || []).map(capstoneRow).join("");
  const passed = c.coursePassed
    ? `<span class="course-passed">Passed${c.passedOn ? ` — ${esc(c.passedOn)}` : ""}</span>`
    : "";
  const counts = c.masteryCounts || {};
  const mastered = (counts.proficient || 0) + (counts.mastered || 0);
  // Level and targetHours are legacy-optional (older manifests predate these fields) —
  // omit each part cleanly when missing rather than rendering "null"/"undefined".
  const metaParts = [
    c.level ? esc(c.level) : "",
    c.targetHours ? `~${esc(String(c.targetHours))} h` : "",
    `${c.lessonsCompleted} of ${c.lessonsTotal} lessons studied`,
    `${mastered} at proficient or above`,
  ].filter(Boolean);
  return (
    `<section class="card tr-course"><div class="tr-chead">` +
    `<h2>${esc(c.title)}</h2>${passed}</div>` +
    `<div class="tr-meta">${metaParts.join(" · ")}</div>${rows}</section>`
  );
}

export function transcriptHTML(data) {
  const courses = (data && data.courses) || [];
  const head = `<div class="greeting"><h1>Transcript</h1><span>Your academic record</span></div>`;
  const note = `<div class="tr-note">This transcript records learning on a personal platform. It is not an accredited credential.</div>` +
    `<div class="tr-note">Mastery standard: a course is passed when every module exam and the final are passed at 80% or above.</div>`;
  if (!courses.length) {
    return `<div class="transcript">${head}` +
      `<div class="card"><div class="prompt">No courses yet — your record will build as you study and sit exams.</div></div>${note}</div>`;
  }
  return `<div class="transcript">${head}${courses.map(courseBlock).join("")}${note}</div>`;
}
