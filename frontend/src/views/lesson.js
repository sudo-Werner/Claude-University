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
  textbook: "Textbook", "official-docs": "Official docs", reference: "Reference", video: "Video",
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

const FIGURE_TOKEN_RE = /\[\[figure:(\d+)\]\]/g;
const FIGURE_FILENAME_RE = /^[a-z0-9-]+-\d\.(jpg|png|webp)$/;
const SAFE_HREF_RE = /^https?:\/\//i;

function webImageFigureHTML(entry, courseId) {
  const src = `/api/courses/${esc(courseId)}/images/${esc(entry.file)}`;
  const licenseHref = entry.licenseUrl || entry.sourceUrl || "";
  // Only render an <a> if the href is a valid http(s) URL; otherwise show text
  const licenseLink = SAFE_HREF_RE.test(licenseHref)
    ? `<a href="${esc(licenseHref)}" target="_blank" rel="noopener noreferrer">${esc(entry.license)}</a>`
    : esc(entry.license);
  return (
    `<figure class="lesson-fig"><img src="${src}" alt="${esc(entry.caption)}" loading="lazy">` +
    `<figcaption>${esc(entry.caption)} <span class="fig-credit">${esc(entry.credit)} ` +
    `${licenseLink}` +
    `</span></figcaption></figure>`
  );
}

// svg/mermaid figures are Claude-drawn diagrams (slice 2). The template NEVER
// string-interpolates entry.code — it has no DOMPurify here, so raw code (which could
// carry a <script> if a cached lesson were hand-edited) must never reach this string.
// A placeholder is emitted instead; app.js's hydrateFigures() sanitizes/renders the
// code and injects it into the placeholder (before the figcaption) after paint.
function drawnFigurePlaceholderHTML(entry, dataAttr) {
  return (
    `<figure class="lesson-fig lesson-fig-${esc(entry.type)}" data-${dataAttr}="${entry.n}">` +
    `<figcaption>${esc(entry.caption)} <span class="fig-credit">Drawn by Claude</span></figcaption>` +
    `</figure>`
  );
}

function figureHTML(entry, courseId) {
  if (entry.type === "svg") return drawnFigurePlaceholderHTML(entry, "fig-svg");
  if (entry.type === "mermaid") return drawnFigurePlaceholderHTML(entry, "fig-mermaid");
  return webImageFigureHTML(entry, courseId);
}

function isValidFigureEntry(entry) {
  if (!entry || typeof entry.n !== "number") return false;
  if (entry.type === "web-image") {
    return typeof entry.file === "string" && FIGURE_FILENAME_RE.test(entry.file);
  }
  if (entry.type === "svg" || entry.type === "mermaid") {
    return typeof entry.code === "string" && entry.code.length > 0;
  }
  return false;
}

// Pure pre-render transform: expands [[figure:n]] tokens ONLY against this lesson's
// OWN backend-written images array, and ONLY for entries of a KNOWN type (web-image,
// svg, mermaid — an unrecognized type renders nothing here, so a future new type stays
// inert until its own slice ships). Returns the expanded promptHtml plus a separate
// trailing block for entries whose token never appeared in the prose (the
// retrofit/backfill case).
export function expandFigureTokens(promptHtml, lesson, courseId) {
  const entries = Array.isArray(lesson.images) ? lesson.images : [];
  const byN = new Map();
  for (const entry of entries) {
    if (isValidFigureEntry(entry) && !byN.has(entry.n)) {
      byN.set(entry.n, entry);
    }
  }
  const used = new Set();
  const html = promptHtml.replace(FIGURE_TOKEN_RE, (match, nStr) => {
    const n = Number(nStr);
    if (used.has(n) || !byN.has(n)) return "";
    used.add(n);
    return figureHTML(byN.get(n), courseId);
  });
  const trailing = Array.from(byN.entries())
    .filter(([n]) => !used.has(n))
    .map(([, entry]) => figureHTML(entry, courseId))
    .join("");
  const figuresBlock = trailing
    ? `<section class="card lesson-figures"><div class="ls-head">Figures</div>${trailing}</section>`
    : "";
  return { html, figuresBlock };
}

// #6 analogy on tap: a chip row per spine concept term (response-only field from
// the lesson GET, read live from spine.json — never cached in the lesson file).
// A tap streams a fresh alternative-angle explanation into the workspace chat.
function conceptChipsHTML(lesson, ws) {
  const concepts = Array.isArray(lesson.concepts) ? lesson.concepts : [];
  if (!concepts.length) return "";
  const pending = !!(ws && ws.pending);
  const chips = concepts.map((term, i) =>
    `<button class="chip" data-action="analogy-chip" data-index="${i}"${pending ? " disabled" : ""}>${esc(term)}</button>`,
  ).join("");
  return `<div class="concept-row"><span class="concept-label">Stuck on a concept? Tap it for a different angle.</span>${chips}</div>`;
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

// Teach it to Claude (protégé effect): a session-mode banner mirroring Socratic's, plus
// the graded verdict once the episode ends. teachGradeHTML mirrors gradeBlock's own
// verdict-painting idiom (GRADE_LABEL + .grade-<verdict>, .grade-soft for an error) so a
// fourth grading surface doesn't invent a fourth visual language.
function teachGradeHTML(g) {
  if (!g) return "";
  if (g.error) return `<div class="grade grade-soft">${esc(g.error)}</div>`;
  const v = GRADE_LABEL[g.verdict] ? g.verdict : "close";
  return `<div class="grade grade-${v}" aria-live="polite">
      <div class="grade-verdict">${GRADE_LABEL[v]}</div>
      <div class="grade-note">${g.note || ""}</div>
    </div>`;
}

function wsChatHTML(w) {
  let banner = "";
  if (w.teaching) {
    const hasTeacherTurn = (w.chat || []).slice(w.teachStart || 0)
      .some((m) => m.role === "user" && (m.content || "").trim());
    const gradeDisabled = !!w.pending || !!w.grading || !hasTeacherTurn;
    const gradeSurface = w.grading
      ? `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Checking your teaching…</span></div>`
      : teachGradeHTML(w.teachGrade);
    banner =
      `<div class="ws-socratic"><span>You're the teacher — Claude is your student.</span>` +
      `<button class="ws-socratic-exit" data-action="teach-exit">Exit</button>` +
      `<button class="ws-socratic-exit" data-action="teach-grade"${gradeDisabled ? " disabled" : ""}>Grade my teaching</button></div>` +
      gradeSurface;
  } else if (w.socratic) {
    banner =
      `<div class="ws-socratic"><span>Working through the exercise — Claude will guide with questions, not answers.</span>` +
      `<button class="ws-socratic-exit" data-action="socratic-exit">Exit</button></div>`;
  } else if (w.teachGrade) {
    banner = teachGradeHTML(w.teachGrade);
  }
  const thread = (w.chat || [])
    .map((m) => `<div class="ws-msg ws-${m.role === "user" ? "you" : "ai"}">${esc(m.content)}</div>`)
    .join("");
  const composeDisabled = w.pending || w.grading;
  const pending = w.pending ? `<div class="ws-msg ws-ai ws-typing">…</div>` : "";
  return (
    `<div class="ws-chat">${banner}<div class="ws-thread">${thread}${pending}</div>` +
    `<div class="ws-compose"><textarea data-field="ws-chat" placeholder="Ask a side question…"${composeDisabled ? " disabled" : ""}></textarea>` +
    `<button class="ws-send" data-action="ws-send"${composeDisabled ? " disabled" : ""}>Send</button></div></div>`
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

// ---- sticky lesson workspace layout ----
// >=1100px the .lesson-side wrapper below becomes a sticky right column via CSS alone.
// Below that, the SAME wrapper (same node, same workspaceHTML() call — never duplicated)
// can be re-styled as a fixed bottom drawer by adding one class; the floating toggle
// button flips that class. Pure/testable in node — no DOM, no app.js state read here.
export function lessonSideClass(drawerOpen) {
  return `lesson-side${drawerOpen ? " ws-drawer-open" : ""}`;
}

function wsDrawerToggleHTML(drawerOpen) {
  return (
    `<button class="ws-drawer-toggle" data-action="ws-drawer-toggle" aria-expanded="${drawerOpen ? "true" : "false"}">` +
    `Notes &amp; Chat</button>`
  );
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

  const { html: expandedPrompt, figuresBlock } = expandFigureTokens(lesson.promptHtml, lesson, lesson.courseId);

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
      <div class="prompt">${expandedPrompt}</div>
      ${conceptChipsHTML(lesson, state.ws)}
      <button class="deepen" data-action="deepen-lesson">Rusty on this? Explain it more deeply</button>
      ${state.deepenError ? `<div class="grade grade-soft">${esc(state.deepenError)}</div>` : ""}
      <textarea data-field="answer" placeholder="Write your update here…" style="min-height:64px; margin:12px 0">${state.answer}</textarea>
      <button class="check-answer" data-action="check-answer"${state.answer.trim() && !state.grading ? "" : " disabled"}>${state.grade && !state.grade.error ? "Check again" : "Check my answer"}</button>
      ${gradeBlock(state)}
      ${state.solutionRevealed ? "" : `<button class="btn-secondary" data-action="socratic-start" style="margin:10px 0 0">Work through it with Claude</button>`}
      <button class="hint-toggle" data-action="toggle-hint" style="margin:10px 0">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
      ${hint}
      <button class="reveal ${sol}" data-action="reveal-solution">${LOCK}<span style="flex:1">${REVEAL_TEXT[sol]}</span></button>
      ${solutionPanel}
    </section>
    ${figuresBlock}
    ${state.solutionRevealed
      ? (state.isReview && state.freshPending
          ? '<p class="checks-pending">Preparing fresh review questions…</p>'
          : checksHTML(lesson.checks || [], state))
      : ""}
    ${state.solutionRevealed ? explainHTML(state) : ""}
    ${state.solutionRevealed ? `<button class="btn-secondary" data-action="teach-start">Teach it to Claude</button>` : ""}
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
    <div class="${lessonSideClass(!!state.drawerOpen)}">${workspaceHTML(state.ws)}</div>
    </div>
    ${wsDrawerToggleHTML(!!state.drawerOpen)}
    </div>
  `;
}
