import { checkItemHTML } from "./checkItem.js";

// Fill answers are short canonical tokens, so trivial formatting differences —
// internal spacing ("-70mV" vs "-70 mV") and dash/minus variants (a typographic
// minus vs a keyboard hyphen) — must not fail an otherwise-correct answer. A sign
// or a different token still differs, so this stays strict about meaning.
const norm = (s) =>
  String(s)
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/\s+/g, "")
    .toLowerCase();

export function gradeCheck(check, answer) {
  const correct =
    check.type === "mcq"
      ? Number(answer) === check.answer
      : norm(answer) === norm(check.answer);
  return { correct, explanation: check.explanation };
}

function item(check, i, state) {
  return checkItemHTML(check, i, state, {
    resultsKey: "checkResults", answersKey: "checkAnswers",
    indexAttr: "data-check", choiceAttr: "data-choice", inputAttr: "data-check-input",
    action: "check-fill",
  });
}

export function checksHTML(checks, state) {
  if (!checks || !checks.length) return "";
  const items = checks.map((c, i) => item(c, i, state)).join("");
  const title = state && state.freshItems ? "Fresh review questions" : "Check your understanding";
  return `<section class="checks"><div class="checks-title">${title}</div>${items}</section>`;
}
