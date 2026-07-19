import { esc } from "../escape.js";

// #4 — Claude's verdict on a graded answer. Warm, specific microcopy
// (research: empathetic feedback beats "Wrong"). Shared by every grading
// surface (exercise answer, explain-it-back, teach-it-to-Claude, remediation
// apply-it) so a fourth or fifth one doesn't invent a fourth visual language.
export const GRADE_LABEL = { correct: "Correct", close: "Almost there", incorrect: "Not quite" };

// `grading`/`loadingText` are optional — omit both when the caller already
// paints its own loading state (e.g. a shared banner covering more than just
// this card) and just wants the error/verdict rendering.
export function gradeCardHTML(g, { grading = false, loadingText = "", labels = GRADE_LABEL } = {}) {
  if (grading) {
    return `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>${loadingText}</span></div>`;
  }
  if (!g) return "";
  if (g.error) return `<div class="grade grade-soft">${esc(g.error)}</div>`;
  const v = labels[g.verdict] ? g.verdict : "close";
  return `<div class="grade grade-${v}" aria-live="polite">
      <div class="grade-verdict">${labels[v]}</div>
      <div class="grade-note">${g.note || ""}</div>
    </div>`;
}

// Pass/fail banner for a graded exam or capstone attempt.
export function examBannerHTML(passed, pct, neededPct) {
  return passed
    ? `<div class="exam-banner pass">Passed — ${pct}%</div>`
    : `<div class="exam-banner fail">Not passed — ${pct}% (${neededPct}% needed)</div>`;
}
