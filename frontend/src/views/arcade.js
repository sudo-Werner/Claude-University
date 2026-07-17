import { esc } from "../escape.js";

const FORMAT_LABELS = {
  rapid_fire: "Rapid fire",
  true_false: "True or false",
  odd_one_out: "Odd one out",
  spot_the_lie: "Spot the lie",
  match_up: "Match-up",
};

// ---- Arcade home: course cards ----

function arcadeStatsHTML(s) {
  const perFormat = Object.keys(s.perFormat || {})
    .map((f) => `<span class="af-item">${esc(FORMAT_LABELS[f] || f)}: <b>${s.perFormat[f].bestPct}%</b> (${s.perFormat[f].plays})</span>`)
    .join("");
  const history = (s.history || [])
    .map((h) => `<li>${esc(h.date)} — ${esc(FORMAT_LABELS[h.format] || h.format)}: ${h.score}/${h.total}</li>`)
    .join("");
  return `
    <div class="arcade-stats">
      <div class="as-row">
        <span class="as-item"><b>${s.roundsPlayed}</b> rounds</span>
        <span class="as-item"><b>${s.bestPct}%</b> best</span>
        <span class="as-item"><b>${s.streakDays}</b> day streak</span>
      </div>
      ${perFormat ? `<div class="af-row">${perFormat}</div>` : ""}
      ${history ? `<ul class="ah-list">${history}</ul>` : ""}
    </div>`;
}

function arcadeCardHTML(course, stats) {
  const locked = !course.progress || course.progress.done === 0;
  if (locked) {
    return `
      <div class="card arcade-card locked">
        <div class="arcade-title">${esc(course.title)}</div>
        <div class="arcade-locked-note">Finish your first lesson to unlock</div>
      </div>`;
  }
  const s = stats || { roundsPlayed: 0, bestPct: 0, streakDays: 0, perFormat: {}, history: [] };
  return `
    <div class="card arcade-card">
      <div class="arcade-title">${esc(course.title)}</div>
      ${arcadeStatsHTML(s)}
      <button class="btn-primary" data-arcade-play="${esc(course.id)}">Play</button>
    </div>`;
}

export function arcadeHTML(courses, statsByCourseId) {
  const cards = courses.map((c) => arcadeCardHTML(c, (statsByCourseId || {})[c.id])).join("");
  return `
    <div class="arcade">
      <div class="greeting"><h1>Arcade</h1><span>Surprise-format quizzes from what you've completed</span></div>
      <div class="arcade-grid">${cards}</div>
    </div>`;
}

// ---- loading / locked / timeout states ----

export function arcadeGeneratingHTML() {
  return `
    <div class="card lesson loading-card arcade-loading">
      <div class="load-status"><span class="load-dot"></span><span class="load-msg">Shuffling a fresh round…</span></div>
      <div class="skeleton"><div class="sk sk-eyebrow"></div><div class="sk sk-line"></div><div class="sk sk-line w70"></div></div>
    </div>`;
}

export function arcadeLockedHTML() {
  return `<div class="card"><div class="prompt">Finish your first lesson to unlock the Arcade for this course.</div></div>`;
}

export function arcadeTimeoutHTML() {
  return `
    <div class="card"><div class="prompt">Still shuffling a round — this is taking longer than usual.</div>
    <div class="nav"><button class="btn-primary" data-action="arcade-retry">Try again</button></div></div>`;
}

// ---- host intro ----

export function hostIntroHTML(round) {
  return `
    <div class="arcade-intro card">
      <div class="eyebrow">ARCADE — ${esc(FORMAT_LABELS[round.format] || round.format)}</div>
      <h1 class="session-topic">${esc(round.title)}</h1>
      <div class="arcade-host">${esc(round.host_intro)}</div>
      <button class="btn-primary" data-action="arcade-begin">Start</button>
    </div>`;
}

// ---- grading (pure; app.js wires DOM taps to this) ----

// Every format grades against a 0-based CHOICE INDEX; true_false's boolean
// answer is mapped to index 0 ("True") / 1 ("False") so the same comparison
// works everywhere. A null/undefined selection (a rapid_fire countdown
// timeout) always grades as a miss — never coerced to index 0.
export function gradeChoice(round, index, selected) {
  if (selected === null || selected === undefined) return false;
  const q = round.questions[index];
  if (round.format === "true_false") return Number(selected) === (q.answer ? 0 : 1);
  return Number(selected) === q.answer;
}

// ---- single-question formats: rapid_fire, true_false, odd_one_out, spot_the_lie ----

function choiceQuestionHTML(index, total, state, choices, promptLabel, correctIndex, reveal) {
  const answered = state.answered;
  const choiceButtons = choices
    .map((c, j) => {
      let cls = "choice";
      if (answered) {
        if (j === correctIndex) cls += " correct";
        else if (j === state.selected) cls += " wrong";
      }
      return `<button class="${cls}" data-arcade-choice="${j}" ${answered ? "disabled" : ""}>${esc(c)}</button>`;
    })
    .join("");
  const countdown = state.countdown != null
    ? `<div class="arcade-countdown">${state.countdown}s</div>` : "";
  const revealBlock = answered ? `<div class="arcade-reveal">${esc(reveal)}</div>` : "";
  const next = answered ? `<button class="btn-primary" data-action="arcade-next">Next</button>` : "";
  return `
    <div class="arcade-question card">
      <div class="arcade-progress">Question ${index + 1} of ${total}</div>
      ${countdown}
      <div class="arcade-prompt">${esc(promptLabel)}</div>
      <div class="arcade-choices">${choiceButtons}</div>
      ${revealBlock}${next}
    </div>`;
}

export function questionHTML(round, index, state) {
  const q = round.questions[index];
  const total = round.questions.length;
  if (round.format === "rapid_fire") {
    return choiceQuestionHTML(index, total, state, q.choices, q.prompt, q.answer, q.reveal);
  }
  if (round.format === "true_false") {
    return choiceQuestionHTML(index, total, state, ["True", "False"], q.statement, q.answer ? 0 : 1, q.reveal);
  }
  if (round.format === "odd_one_out") {
    return choiceQuestionHTML(index, total, state, q.items, "Which one doesn't belong?", q.answer, q.reveal);
  }
  // spot_the_lie
  return choiceQuestionHTML(index, total, state, q.statements, "Which statement is the lie?", q.answer, q.reveal);
}

// ---- match_up: pure interaction state (app.js wires taps to this) ----

function defaultShuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function matchUpInit(board, shuffle = defaultShuffle) {
  return {
    leftSelected: null,
    matched: {},
    wrongAttempts: {},
    rightOrder: shuffle(board.pairs.map((_, i) => i)),
    correct: null,
  };
}

export function matchUpSelectLeft(state, leftIndex) {
  if (state.matched[leftIndex]) return state;
  return { ...state, leftSelected: leftIndex, correct: null };
}

// `rightPairIndex` is the ORIGINAL pair index the tapped right-column item
// belongs to (matchBoardHTML renders data-match-right with that original
// index, so the caller never has to un-shuffle it).
export function matchUpSelectRight(state, board, rightPairIndex) {
  if (state.leftSelected === null) return { ...state, correct: null };
  const left = state.leftSelected;
  const correct = left === rightPairIndex;
  if (correct) {
    return { ...state, matched: { ...state.matched, [left]: true }, leftSelected: null, correct: true };
  }
  return {
    ...state,
    wrongAttempts: { ...state.wrongAttempts, [left]: (state.wrongAttempts[left] || 0) + 1 },
    leftSelected: null,
    correct: false,
  };
}

export function matchUpComplete(state, board) {
  return board.pairs.every((_, i) => !!state.matched[i]);
}

// First-attempt-correct pairs count toward the round score; every pair
// solved only after >=1 wrong tap counts as a miss for the board's lesson.
export function matchUpScore(state, board) {
  let correct = 0;
  for (let i = 0; i < board.pairs.length; i++) {
    if (state.matched[i] && !state.wrongAttempts[i]) correct += 1;
  }
  return { correct, total: board.pairs.length };
}

export function matchBoardHTML(round, boardIndex, state) {
  const board = round.questions[boardIndex];
  const total = round.questions.length;
  const leftItems = board.pairs.map((p, i) => {
    const solved = !!state.matched[i];
    const selected = state.leftSelected === i;
    let cls = "arcade-match-item";
    if (solved) cls += " solved";
    else if (selected) cls += " selected";
    return `<button class="${cls}" data-match-left="${i}" ${solved ? "disabled" : ""}>${esc(p.left)}</button>`;
  }).join("");
  const rightItems = state.rightOrder.map((origIndex) => {
    const solved = !!state.matched[origIndex];
    const cls = "arcade-match-item" + (solved ? " solved" : "");
    return `<button class="${cls}" data-match-right="${origIndex}" ${solved ? "disabled" : ""}>${esc(board.pairs[origIndex].right)}</button>`;
  }).join("");
  const complete = matchUpComplete(state, board);
  const revealBlock = complete ? `<div class="arcade-reveal">${esc(board.reveal)}</div>` : "";
  const next = complete ? `<button class="btn-primary" data-action="arcade-next">Next</button>` : "";
  return `
    <div class="arcade-question arcade-match card">
      <div class="arcade-progress">Board ${boardIndex + 1} of ${total}</div>
      <div class="arcade-match-cols">
        <div class="arcade-match-col">${leftItems}</div>
        <div class="arcade-match-col">${rightItems}</div>
      </div>
      ${revealBlock}${next}
    </div>`;
}

// ---- end of round ----

export function arcadeResultHTML(playState) {
  const pct = playState.total ? Math.round((playState.score / playState.total) * 100) : 0;
  return `
    <div class="arcade-result card">
      <div class="eyebrow">ROUND COMPLETE</div>
      <h1 class="session-topic">${pct}%</h1>
      <div class="arcade-score-note">${playState.score} / ${playState.total} correct</div>
      <button class="btn-primary" data-action="arcade-play-again">Play again</button>
      <button class="btn-secondary" data-action="arcade-back">Back to Arcade</button>
    </div>`;
}
