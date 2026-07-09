import { esc } from "../escape.js";
import { syllabusHTML } from "./syllabus.js";

export function revisionHTML({ course, changeSummary, progressAtRisk }) {
  const changeItems = (changeSummary || []);
  const atRisk = (progressAtRisk || []);

  const changeSection = changeItems.length
    ? `<div class="revision-changes"><h2>What's changing</h2><ul>${changeItems.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
    : "";

  const riskSection = atRisk.length
    ? `<div class="progress-at-risk">Progress on ${atRisk.length} lesson(s) will no longer count: ${atRisk.map((l) => esc(l.title || "")).join(", ")}</div>`
    : "";

  const actions = `<div class="syl-actions">` +
    `<button class="btn-primary" data-action="apply-revision">Apply changes</button>` +
    `<button class="btn-secondary" data-action="keep-discussing" style="margin-top:8px">Keep discussing</button>` +
    `</div>`;

  // Render the proposal WITHOUT syllabusHTML's own intake CTAs — the revision screen supplies
  // its own Apply / Keep discussing actions below, so the intake buttons would be dead + confusing.
  const syllabus = syllabusHTML(course, { actions: false });

  return `<div class="revision">${syllabus}${changeSection}${riskSection}${actions}</div>`;
}
