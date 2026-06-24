function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

const norm = (s) => String(s).trim().toLowerCase();

export function gradeCheck(check, answer) {
  const correct =
    check.type === "mcq"
      ? Number(answer) === check.answer
      : norm(answer) === norm(check.answer);
  return { correct, explanation: check.explanation };
}

function item(check, i, state) {
  const result = state.checkResults && state.checkResults[i];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state.checkAnswers[i])) cls = "choice wrong";
        }
        return `<button class="${cls}" data-check="${i}" data-choice="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state.checkAnswers && state.checkAnswers[i] != null ? state.checkAnswers[i] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input data-check-input="${i}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="check-fill" data-check="${i}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}

export function checksHTML(checks, state) {
  if (!checks || !checks.length) return "";
  const items = checks.map((c, i) => item(c, i, state)).join("");
  return `<section class="checks"><div class="checks-title">Check your understanding</div>${items}</section>`;
}
