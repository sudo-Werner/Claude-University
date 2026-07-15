import { esc } from "../escape.js";

// Question prompts, choices, and grader notes arrive SERVER-sanitized and render
// raw (client esc() would double-escape). Objective texts, lesson titles, the exam
// title, and error strings are plain text and MUST be escaped here.

export function examReady(exam, answers) {
  return exam.questions.every((q, i) =>
    q.type === "mcq" ? Number.isInteger(answers[i]) : !!(answers[i] || "").trim());
}

function questionBlock(q, i, answers) {
  let body;
  if (q.type === "mcq") {
    body = q.choices
      .map((c, j) => `<button class="exam-choice${answers[i] === j ? " selected" : ""}" data-q="${i}" data-choice="${j}">${c}</button>`)
      .join("");
  } else {
    body = `<textarea class="exam-free" data-q="${i}" rows="4" maxlength="5000" placeholder="Answer in a few sentences…">${esc(answers[i] || "")}</textarea>`;
  }
  return (
    `<div class="exam-q"><div class="exam-qhead">Question ${i + 1}` +
    `<span class="obj-tag">${esc(q.bloom || "")}</span></div>` +
    `<div class="exam-prompt">${q.prompt}</div>${body}</div>`
  );
}

export function examHTML(exam, state) {
  const qs = exam.questions.map((q, i) => questionBlock(q, i, state.answers)).join("");
  const ready = examReady(exam, state.answers) && !state.submitting;
  return (
    `<div class="exam">` +
    `<div class="eyebrow">EXAM</div>` +
    `<h1 class="session-topic">${esc(exam.title || "")}</h1>` +
    `<div class="exam-note">Pass mark: 80%. You can retake with fresh questions anytime.</div>` +
    qs +
    (state.error ? `<div class="exam-error">${esc(state.error)}</div>` : "") +
    `<div class="nav"><button class="btn-primary" data-action="submit-exam"${ready ? "" : " disabled"}>` +
    `${state.submitting ? "Grading…" : "Submit exam"}</button></div>` +
    `</div>`
  );
}

function resultQuestion(q, i) {
  let feedback;
  if (q.type === "mcq") {
    const yours = q.choices[q.answer];
    feedback = q.correct
      ? `<div class="exam-fb good">Correct</div>`
      : `<div class="exam-fb bad">Your answer: ${yours}. Correct answer: ${q.choices[q.correctIndex]}</div>`;
  } else {
    feedback = `<div class="exam-fb ${q.verdict === "correct" ? "good" : q.verdict === "close" ? "mid" : "bad"}">` +
      `<b>${esc(q.verdict)}</b> — ${q.note}</div>`;
  }
  return (
    `<div class="exam-q result"><div class="exam-qhead">Question ${i + 1}` +
    `<span class="exam-pts">${q.points} pt</span></div>` +
    `<div class="exam-prompt">${q.prompt}</div>${feedback}</div>`
  );
}

export function examResultHTML(result) {
  const pct = Math.round(result.score * 100);
  const banner = result.passed
    ? `<div class="exam-banner pass">Passed — ${pct}%</div>`
    : `<div class="exam-banner fail">Not passed — ${pct}% (80% needed)</div>`;
  const weak = (result.weakSpots || [])
    .map((w) =>
      `<div class="weak-spot"><button class="weak-lesson" data-lesson="${esc(w.lessonId)}">${esc(w.lessonTitle)} →</button>` +
      `<ul>${(w.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul></div>`)
    .join("");
  const qs = (result.perQuestion || []).map(resultQuestion).join("");
  return (
    `<div class="exam-result">${banner}` +
    (weak ? `<h2>Focus next on</h2>${weak}` : "") +
    (qs ? `<h2>Question by question</h2>${qs}` : "") +
    `<div class="nav">` +
    `<button class="btn-secondary" data-action="retake-exam">Retake with fresh questions</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
