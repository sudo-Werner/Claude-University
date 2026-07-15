import { esc } from "../escape.js";

// The warm-up attempt before a first-time lesson. preQuiz prompt/choices/explanation
// are server-sanitized (same boundary as checks) — rendered raw, like views/checks.js.
export function preQuizHTML(preQuiz, state) {
  const pq = state.preQuiz || null;
  const answered = !!(pq && pq.result);
  let body;
  if (preQuiz.type === "mcq") {
    body = preQuiz.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === preQuiz.answer) cls = "choice correct";
          else if (j === Number(pq.answer)) cls = "choice wrong";
        }
        return `<button class="${cls}" data-pq-choice="${j}"${answered ? " disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(pq.answer != null ? pq.answer : "")}</b></div>`
      : `<div class="fill-row"><input data-pq-input placeholder="Your best guess…"><button class="btn-secondary" data-action="pq-submit">Submit</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${pq.result.correct ? "ok" : "no"}">${pq.result.correct ? "Correct" : "Not quite"} — ${preQuiz.explanation}</div>` +
      `<button class="btn-primary" data-action="pq-continue" style="margin-top:12px">Start the lesson</button>`
    : "";
  return (
    `<section class="card prequiz"><span class="eyebrow">BEFORE YOU START</span>` +
    `<div class="pq-lead">Take your best guess — attempting first makes the lesson stick, even if you get it wrong.</div>` +
    `<div class="check-q">${preQuiz.prompt}</div>${body}${feedback}</section>`
  );
}
