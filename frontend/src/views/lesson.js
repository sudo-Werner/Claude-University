import { solutionState } from "../reveal.js";
import { checksHTML } from "./checks.js";
import { preQuizHTML } from "./prequiz.js";
import { esc } from "../escape.js";

const BULB = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.2 1 2.5h6c0-1.3.3-1.8 1-2.5A6 6 0 0012 3z" stroke="#e0892f" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const LOCK = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 11V8a4 4 0 018 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`;
const ARROW = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const LIST = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;

const REVEAL_TEXT = {
  locked: "Attempt first to unlock the solution",
  ready: "Reveal solution",
  shown: "Solution shown",
};
const HINT_TEXT = { true: "Hide hint", false: "Show hint" };

// #4 — Claude's verdict on the learner's typed answer. Warm, specific microcopy
// (research: empathetic feedback beats "Wrong").
const GRADE_LABEL = { correct: "Correct", close: "Almost there", incorrect: "Not quite" };

function gradeBlock(state) {
  if (state.grading) {
    return `<div class="grade grade-loading" aria-live="polite">
        <span class="grade-spin"></span><span>Checking your answer…</span>
      </div>`;
  }
  const g = state.grade;
  if (!g) return "";
  if (g.error) return `<div class="grade grade-soft">${esc(g.error)}</div>`;
  const v = GRADE_LABEL[g.verdict] ? g.verdict : "close";
  return `<div class="grade grade-${v}" aria-live="polite">
      <div class="grade-verdict">${GRADE_LABEL[v]}</div>
      <div class="grade-note">${g.note || ""}</div>
    </div>`;
}

// Explain-it-back (skippable): the learner restates the core idea in their own
// words after the solution; Claude grades understanding via the /explain route.
function explainHTML(state) {
  const ex = state.explain || {};
  const g = ex.grade;
  let result = "";
  if (ex.grading) {
    result = `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Reading your explanation…</span></div>`;
  } else if (g && g.error) {
    result = `<div class="grade grade-soft">${esc(g.error)}</div>`;
  } else if (g) {
    const v = GRADE_LABEL[g.verdict] ? g.verdict : "close";
    result = `<div class="grade grade-${v}" aria-live="polite"><div class="grade-verdict">${GRADE_LABEL[v]}</div><div class="grade-note">${g.note || ""}</div></div>`;
    if (g.followUp) {
      const seeded = !!ex.seeded;
      result +=
        `<div class="explain-followup"><div class="grade-note">${g.followUp}</div>` +
        `<button class="btn-secondary" data-action="explain-chat"${seeded ? " disabled" : ""}>` +
        `${seeded ? "Sent to side-chat" : "Explore in side-chat"}</button></div>`;
    }
  }
  const canSend = (ex.text || "").trim() && !ex.grading;
  return (
    `<section class="card explain"><div class="checks-title">Explain it back</div>` +
    `<div class="pq-lead">In your own words, what is the core idea of this lesson? Optional — but saying it yourself is the strongest test.</div>` +
    `<textarea data-field="explain" placeholder="The core idea is…">${esc(ex.text || "")}</textarea>` +
    `<button class="btn-secondary" data-action="explain-grade"${canSend ? "" : " disabled"}>${g && !g.error ? "Get feedback again" : "Get feedback"}</button>` +
    `${result}</section>`
  );
}

// Phase 2 — the accredited sources this lesson was grounded in (real, web-retrieved).
const SRC_TYPE_LABEL = {
  university: "University", preprint: "Preprint / scholarly", "peer-reviewed": "Peer-reviewed",
  textbook: "Textbook", "official-docs": "Official docs", reference: "Reference",
};

function lessonSourcesHTML(sources) {
  if (!Array.isArray(sources) || !sources.length) return "";
  const rows = sources.map((s) =>
    `<li class="lsrc"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.title}</a>` +
    `<span class="src-badge src-${esc(s.type || "reference")}">${SRC_TYPE_LABEL[s.type] || "Reference"}</span></li>`,
  ).join("");
  return (
    `<section class="card lesson-sources"><div class="ls-head">Sources</div>` +
    `<ul class="lsrc-list">${rows}</ul>` +
    `<div class="ls-foot">Grounded sources this lesson drew on — retrieved from the web, not invented.</div></section>`
  );
}

// ---- lesson workspace: collapsible Notes | Chat panel below the lesson ----
function wsNotesHTML(w) {
  const status = { saving: "saving…", saved: "saved", offline: "offline" }[w.saveStatus] || "";
  return (
    `<div class="ws-notes">` +
    `<textarea data-field="ws-notes" placeholder="Jot your notes…">${esc(w.notes || "")}</textarea>` +
    `<div class="ws-status">${status}</div></div>`
  );
}

function wsChatHTML(w) {
  const thread = (w.chat || [])
    .map((m) => `<div class="ws-msg ws-${m.role === "user" ? "you" : "ai"}">${esc(m.content)}</div>`)
    .join("");
  const pending = w.pending ? `<div class="ws-msg ws-ai ws-typing">…</div>` : "";
  return (
    `<div class="ws-chat"><div class="ws-thread">${thread}${pending}</div>` +
    `<div class="ws-compose"><textarea data-field="ws-chat" placeholder="Ask a side question…"${w.pending ? " disabled" : ""}></textarea>` +
    `<button class="ws-send" data-action="ws-send"${w.pending ? " disabled" : ""}>Send</button></div></div>`
  );
}

function workspaceHTML(ws) {
  const w = ws || {};
  const caret = w.open ? "▾" : "▸";
  const head = `<button class="ws-toggle" data-action="ws-toggle"><span class="ws-caret">${caret}</span> Notes &amp; side-chat</button>`;
  if (!w.open) return `<section class="card workspace">${head}</section>`;
  const tabs =
    `<div class="ws-tabs">` +
    `<button class="ws-tab ${w.tab === "chat" ? "" : "on"}" data-action="ws-tab" data-tab="notes">Notes</button>` +
    `<button class="ws-tab ${w.tab === "chat" ? "on" : ""}" data-action="ws-tab" data-tab="chat">Chat</button>` +
    `</div>`;
  const body = w.tab === "chat" ? wsChatHTML(w) : wsNotesHTML(w);
  return `<section class="card workspace">${head}${tabs}${body}</section>`;
}

// Review mode gates the recall rating behind an actual retrieval attempt: the
// lesson's checks must be re-answered first (testing effect — re-reading alone
// systematically inflates self-rated recall).
export function ratingLocked(lesson, state) {
  if (!state.isReview) return false;
  const checks = (lesson.checks || []).length;
  if (!checks) return false;
  const answered = Object.keys(state.checkResults || {}).length;
  return answered < checks;
}

export function suggestedQuality(lesson, state) {
  if (!state.isReview) return null;
  const results = state.checkResults || {};
  const keys = Object.keys(results);
  if (!keys.length) return null;
  return keys.some((k) => results[k] && !results[k].correct) ? "again" : "good";
}

export function lessonHTML(lesson, state, nav = {}) {
  const segs = Array.from({ length: lesson.totalSteps }, (_, i) => {
    if (i + 1 < lesson.step) return '<i class="done"></i>';
    if (i + 1 === lesson.step) return '<i class="now"></i>';
    return "<i></i>";
  }).join("");

  if (state.stage === "prequiz" && lesson.preQuiz) {
    return `
    <div class="lesson-col">
    <div class="lesson-head">
    <div>
      <div class="steps">${segs}</div>
      <div class="steprow"><span>Step ${lesson.step} of ${lesson.totalSteps} · <b>Warm-up</b></span><span class="right">${lesson.topic}</span></div>
    </div>
      <div class="player-nav">
        <button class="pn-btn pn-curric" data-action="curriculum">${LIST}<span>Curriculum</span></button>
        <div class="pn-move">
          <button class="pn-btn" data-action="prev-lesson" aria-label="Previous lesson"${nav.hasPrev ? "" : " disabled"}>‹</button>
          <button class="pn-btn" data-action="next-lesson" aria-label="Next lesson"${nav.hasNext ? "" : " disabled"}>›</button>
        </div>
      </div>
    </div>
    ${preQuizHTML(lesson.preQuiz, state)}
    </div>
  `;
  }

  const sol = solutionState({ answer: state.answer, revealed: state.solutionRevealed });
  const hint = state.hintVisible
    ? `<div class="hint" style="margin-bottom:10px">${lesson.hintHtml}</div>`
    : "";
  const solutionPanel = state.solutionRevealed
    ? `<div class="solution"><div class="lbl">SOLUTION</div><div class="ans">${lesson.solutionAns}</div><div class="note">${lesson.solutionNote}</div></div>`
    : "";

  const locked = state.solutionRevealed && ratingLocked(lesson, state);
  const suggested = state.solutionRevealed && !locked ? suggestedQuality(lesson, state) : null;
  const rateQ = locked ? "Answer the checks above to rate your recall" : "How well did you recall this?";
  const rateBtn = (quality, label) =>
    `<button class="rate-btn${suggested === quality ? " suggested" : ""}" data-quality="${quality}"${locked ? " disabled" : ""}>${label}</button>`;

  return `
    <div class="lesson-col">
    <div class="lesson-head">
    <div>
      <div class="steps">${segs}</div>
      <div class="steprow"><span>Step ${lesson.step} of ${lesson.totalSteps} · <b>Exercise</b></span><span class="right">${lesson.topic}</span></div>
    </div>
      <div class="player-nav">
        <button class="pn-btn pn-curric" data-action="curriculum">${LIST}<span>Curriculum</span></button>
        <div class="pn-move">
          <button class="pn-btn" data-action="prev-lesson" aria-label="Previous lesson"${nav.hasPrev ? "" : " disabled"}>‹</button>
          <button class="pn-btn" data-action="next-lesson" aria-label="Next lesson"${nav.hasNext ? "" : " disabled"}>›</button>
        </div>
      </div>
    </div>
    <div class="lesson-body">
    <div class="lesson-main">
    <section class="card lesson">
      <span class="eyebrow">${lesson.eyebrow}</span>
      <div class="prompt">${lesson.promptHtml}</div>
      <button class="deepen" data-action="deepen-lesson">Rusty on this? Explain it more deeply</button>
      ${state.deepenError ? `<div class="grade grade-soft">${esc(state.deepenError)}</div>` : ""}
      <textarea data-field="answer" placeholder="Write your update here…" style="min-height:64px; margin:12px 0">${state.answer}</textarea>
      <button class="check-answer" data-action="check-answer"${state.answer.trim() && !state.grading ? "" : " disabled"}>${state.grade && !state.grade.error ? "Check again" : "Check my answer"}</button>
      ${gradeBlock(state)}
      <button class="hint-toggle" data-action="toggle-hint" style="margin:10px 0">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
      ${hint}
      <button class="reveal ${sol}" data-action="reveal-solution">${LOCK}<span style="flex:1">${REVEAL_TEXT[sol]}</span></button>
      ${solutionPanel}
    </section>
    ${state.solutionRevealed ? checksHTML(lesson.checks || [], state) : ""}
    ${state.solutionRevealed ? explainHTML(state) : ""}
    ${lessonSourcesHTML(lesson.sources)}
    <div class="nav">
      <button class="btn-back" data-action="back">Back</button>
      ${
        state.solutionRevealed
          ? `<div class="rate" role="group" aria-label="Rate recall">
               <span class="rate-q">${rateQ}</span>
               ${rateBtn("again", "Again")}
               ${rateBtn("hard", "Hard")}
               ${rateBtn("good", "Good")}
               ${rateBtn("easy", "Easy")}
             </div>`
          : `<span class="nav-hint">Reveal the solution to finish</span>`
      }
    </div>
    </div>
    <div class="lesson-side">${workspaceHTML(state.ws)}</div>
    </div>
    </div>
  `;
}
