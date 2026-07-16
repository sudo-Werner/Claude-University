import { esc } from "../escape.js";

// A corrective session after a failed exam: per gap, a new-angle explanation
// (server-sanitized, renders raw) plus fresh practice items graded client-side
// exactly like lesson checks, plus ONE free-response "Apply it" task graded by
// the backend (legacy sessions on the Pi lack it — rendered only when present).
// Practice state is keyed by FLAT index across gaps; apply state by gap index.

export function flatPractice(session) {
  const out = [];
  (session.gaps || []).forEach((g, gi) =>
    (g.practice || []).forEach((check) => out.push({ gapIndex: gi, lessonId: g.lessonId, check })));
  return out;
}

export function lessonIndexFrom(manifest) {
  const idx = {};
  ((manifest && manifest.modules) || []).forEach((m) =>
    (m.lessons || []).forEach((l) => { idx[l.id] = { title: l.title || "", prereqs: l.prereqs || [] }; }));
  return idx;
}

// A gap's apply task is usable only when it has a non-blank prompt AND a
// non-blank modelAnswer — the same rule the backend grade route (POST
// .../remediation/grade in backend/app.py) enforces before it will grade an
// answer, and the same rule backend/remediation.py's session_completed uses
// server-side. A gap with a present-but-blank/malformed apply dict must NOT
// be treated as "has an apply task" here, or the retake unlock (and this
// render gate) could depend on a task nothing can ever grade.
export function usableApply(gap) {
  const apply = gap && gap.apply;
  return !!(apply
    && typeof apply.prompt === "string" && apply.prompt.trim()
    && typeof apply.modelAnswer === "string" && apply.modelAnswer.trim());
}

// The retake unlock (Item B): every practice item answered and every present
// apply task graded. The backend detector is authoritative; this mirrors it.
export function remediationComplete(session, state) {
  const total = flatPractice(session).length;
  for (let k = 0; k < total; k++) {
    if (!(state.results && state.results[k])) return false;
  }
  return (session.gaps || []).every((g, gi) =>
    !usableApply(g) || !!(state.applyResults && state.applyResults[gi] && state.applyResults[gi].verdict));
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

const APPLY_LABEL = { correct: "Correct", close: "Almost there", incorrect: "Not quite" };

function applyBlock(gap, gi, state) {
  if (!usableApply(gap)) return "";
  const res = state.applyResults && state.applyResults[gi];
  const busy = !!(state.applyBusy && state.applyBusy[gi]);
  const done = !!(res && res.verdict);
  const val = state.applyAnswers && state.applyAnswers[gi] != null ? state.applyAnswers[gi] : "";
  let feedback = "";
  if (busy) {
    feedback = `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Checking your answer…</span></div>`;
  } else if (res && res.error) {
    feedback = `<div class="grade grade-soft">${esc(res.error)}</div>`;
  } else if (done) {
    const v = APPLY_LABEL[res.verdict] ? res.verdict : "close";
    feedback =
      `<div class="grade grade-${v}" aria-live="polite">` +
      `<div class="grade-verdict">${APPLY_LABEL[v]}</div>` +
      `<div class="grade-note">${res.note || ""}</div></div>` +
      `<div class="rem-model"><b>A correct answer covers:</b> ${res.modelAnswer || ""}</div>`;
  }
  const canSend = !!val.trim() && !busy && !done;
  return (
    `<div class="rem-apply"><div class="checks-title">Apply it</div>` +
    `<div class="rem-apply-prompt">${gap.apply.prompt}</div>` +
    `<textarea data-rem-apply="${gi}" placeholder="Work it through…"${done ? " disabled" : ""}>${esc(val)}</textarea>` +
    `<button class="btn-secondary" data-action="rem-apply" data-gap="${gi}"${canSend ? "" : " disabled"}>` +
    `${done ? "Answered" : busy ? "Checking…" : "Check my answer"}</button>${feedback}</div>`
  );
}

// Item D: trace the weakness to its root — chips open the upstream lesson.
function buildsOnChips(lessonId, lessonIndex) {
  const entry = lessonIndex[lessonId];
  const chips = ((entry && entry.prereqs) || [])
    .filter((id) => lessonIndex[id])          // revised-away lessons: skipped silently
    .map((id) => `<button class="rem-chip" data-lesson="${esc(id)}">${esc(lessonIndex[id].title)}</button>`)
    .join("");
  return chips ? `<div class="rem-builds">Builds on: ${chips}</div>` : "";
}

export function remediationHTML(session, state, manifest) {
  const lessonIndex = lessonIndexFrom(manifest);
  let k = 0;
  const gaps = (session.gaps || [])
    .map((g, gi) => {
      const items = (g.practice || []).map((c) => practiceItem(c, k++, state)).join("");
      const objectives = (g.objectives || []).map((o) => `<li>${esc(o)}</li>`).join("");
      return (
        `<section class="rem-gap"><h2>${esc(g.lessonTitle)}</h2>` +
        (objectives ? `<ul class="rem-objectives">${objectives}</ul>` : "") +
        buildsOnChips(g.lessonId, lessonIndex) +
        `<div class="rem-explain">${g.explanationHtml}</div>` +
        `<div class="rem-practice">${items}</div>` +
        applyBlock(g, gi, state) +
        `</section>`
      );
    })
    .join("");
  const complete = remediationComplete(session, state);
  return (
    `<div class="remediation">` +
    `<div class="eyebrow">GAP REVIEW</div>` +
    `<h1 class="session-topic">Fix the gaps</h1>` +
    `<div class="exam-note">Each gap is re-explained from a new angle, with fresh practice. ` +
    `When it clicks, retake the exam — new questions, same objectives.</div>` +
    gaps +
    `<div class="nav">` +
    `<button class="btn-primary" data-action="retake-exam"${complete ? "" : " disabled"}>` +
    `${complete ? "Retake with fresh questions" : "Answer everything above to unlock the retake"}</button>` +
    `<button class="btn-back" data-action="back-curriculum">Back to course</button>` +
    `</div></div>`
  );
}
