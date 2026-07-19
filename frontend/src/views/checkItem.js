import { esc } from "../escape.js";

// Shared render for one check-shaped item (mcq/fill + its answered/feedback
// state) — used by lesson checks (checks.js), remediation practice
// (remediation.js), and originally duplicated byte-for-byte between them.
// Parameterized on the caller's own state field names and DOM data-attribute
// names (which differ between callers and are load-bearing — app.js's click
// handlers read them directly) so every existing caller's markup and
// event-wiring stay byte-identical.
export function checkItemHTML(check, i, state, { resultsKey, answersKey, indexAttr, choiceAttr, inputAttr, action }) {
  const result = state[resultsKey] && state[resultsKey][i];
  const answered = !!result;
  let body;
  if (check.type === "mcq") {
    body = check.choices
      .map((c, j) => {
        let cls = "choice";
        if (answered) {
          if (j === check.answer) cls = "choice correct";
          else if (j === Number(state[answersKey][i])) cls = "choice wrong";
        }
        return `<button class="${cls}" ${indexAttr}="${i}" ${choiceAttr}="${j}" ${answered ? "disabled" : ""}>${c}</button>`;
      })
      .join("");
  } else {
    const val = state[answersKey] && state[answersKey][i] != null ? state[answersKey][i] : "";
    body = answered
      ? `<div class="fill-answer">Your answer: <b>${esc(val)}</b></div>`
      : `<div class="fill-row"><input ${inputAttr}="${i}" placeholder="Type your answer…" value="${esc(val)}"><button class="btn-secondary" data-action="${action}" ${indexAttr}="${i}">Check</button></div>`;
  }
  const feedback = answered
    ? `<div class="check-feedback ${result.correct ? "ok" : "no"}">${result.correct ? "Correct" : "Not quite"} — ${check.explanation}</div>`
    : "";
  return `<div class="check"><div class="check-q">${check.prompt}</div>${body}${feedback}</div>`;
}
