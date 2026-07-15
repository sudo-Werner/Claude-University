import { esc } from "../escape.js";

// A corrective session after a failed exam: per gap, a new-angle explanation
// (server-sanitized, renders raw) plus fresh practice items graded client-side
// exactly like lesson checks. Practice state is keyed by FLAT index across gaps.

export function flatPractice(session) {
  const out = [];
  (session.gaps || []).forEach((g, gi) =>
    (g.practice || []).forEach((check) => out.push({ gapIndex: gi, lessonId: g.lessonId, check })));
  return out;
}

function practiceItem(check, k, state) {
  const result = state.results && state.results[k];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state.answers[k])) cls = "choice wrong";
        }
        return `<button class="${cls}" data-rq="${k}" data-rq-choice="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state.answers && state.answers[k] != null ? state.answers[k] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input data-rq-input="${k}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="rq-fill" data-rq="${k}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}

export function remediationHTML(session, state) {
  let k = 0;
  const gaps = (session.gaps || [])
    .map((g) => {
      const items = (g.practice || []).map((c) => practiceItem(c, k++, state)).join("");
      const objectives = (g.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("");
      return (
        `<section class="rem-gap"><h2>${esc(g.lessonTitle)}</h2>` +
        (objectives ? `<ul class="rem-objectives">${objectives}</ul>` : "") +
        `<div class="rem-explain">${g.explanationHtml}</div>` +
        `<div class="rem-practice">${items}</div></section>`
      );
    })
    .join("");
  return (
    `<div class="remediation">` +
    `<div class="eyebrow">GAP REVIEW</div>` +
    `<h1 class="session-topic">Fix the gaps</h1>` +
    `<div class="exam-note">Each gap is re-explained from a new angle, with fresh practice. ` +
    `When it clicks, retake the exam — new questions, same objectives.</div>` +
    gaps +
    `<div class="nav">` +
    `<button class="btn-primary" data-action="retake-exam">Retake with fresh questions</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
