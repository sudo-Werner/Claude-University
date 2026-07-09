import { PHASE_NAMES, PHASE_SECONDS } from "../timer.js";
import { esc } from "../escape.js";

function contractHTML(contract) {
  if (!contract) return "";
  const level = contract.level ? `<span class="level-badge">${esc(contract.level)}</span>` : "";
  const hours = contract.hours ? `<span class="hours-badge">~${contract.hours} h total effort</span>` : "";
  const meta = level || hours ? `<div class="contract-meta">${level}${hours}</div>` : "";
  const skills = (contract.skills || []).slice(0, 8);
  const list = skills.length
    ? `<div class="contract-skills"><span class="eyebrow mut">WHAT YOU'LL BE ABLE TO DO</span>` +
      `<ul>${skills.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>`
    : "";
  if (!meta && !list) return "";
  return `<div class="contract">${meta}${list}</div>`;
}

const CLOCK_ICON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#a59b89" stroke-width="2"/><path d="M12 7v5l3 2" stroke="#a59b89" stroke-width="2" stroke-linecap="round"/></svg>`;
const PLAY_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="#fff"><path d="M7 5l12 7-12 7V5z"/></svg>`;
const MASTERY_LABELS = { attempted: "Attempted", familiar: "Familiar", proficient: "Proficient", mastered: "Mastered" };

function masteryHTML(counts) {
  const c = counts || {};
  const parts = ["mastered", "proficient", "familiar", "attempted"]
    .filter((k) => (c[k] || 0) > 0)
    .map((k) => `<span class="m-item"><b>${c[k]}</b> ${MASTERY_LABELS[k]}</span>`);
  if (!parts.length) return "";
  return `<div class="mastery"><div class="m-label">Mastery</div><div class="m-row">${parts.join("")}</div></div>`;
}

const PHASE_COLORS = ["#3aa0e0", "#7c6aff", "#25b478"];
const PHASE_DUR = PHASE_SECONDS.map((s) => `${s / 60}m`);
const PHASE_FLEX = [15, 60, 15];

export function dashboardHTML(data, timerView) {
  const tracks = PHASE_FLEX.map(
    (flex, i) =>
      `<div class="phase-track" style="flex:${flex} 1 0"><i style="background:${PHASE_COLORS[i]}; width:${Math.round(
        timerView.fills[i] * 100,
      )}%"></i></div>`,
  ).join("");
  const labels = PHASE_FLEX.map(
    (flex, i) =>
      `<div class="${i === timerView.activePhaseIndex ? "active-warm" : ""}" style="flex:${flex} 1 0${i === timerView.activePhaseIndex ? `; --phase-clr:${PHASE_COLORS[i]}` : ""}"><div class="name">${PHASE_NAMES[i]}</div><div class="dur">${PHASE_DUR[i]}</div></div>`,
  ).join("");

  return `
    <div class="dash">
    <div class="greeting"><h1>Good morning, Werner</h1><span>Today</span></div>
    ${contractHTML(data.contract)}
    <section class="card">
      <div class="session-head">
        <span class="eyebrow">TODAY'S SESSION</span>
        <span class="meta">${CLOCK_ICON} ${data.durationMin} min</span>
      </div>
      <h2 class="session-topic">${data.topic}</h2>
      <div class="session-sub">${data.sub}</div>
      <div class="phase-bar" aria-label="Session plan">${tracks}</div>
      <div class="phase-labels">${labels}</div>
      <div class="timer-status"><span>${timerView.statusLabel}</span><span class="clock">${timerView.clock}</span></div>
      <button class="btn-primary" data-action="start-session">${PLAY_ICON} Start session</button>
      <button class="btn-secondary" data-action="curriculum" style="margin-top:8px">View all lessons</button>
      <button class="btn-secondary" data-action="library" style="margin-top:8px">Library · accredited sources</button>
    </section>
    <div class="stat-row">
      <section class="stat">
        <span class="eyebrow mut">COURSE PROGRESS</span>
        <div style="display:flex; align-items:baseline; gap:6px; margin-top:12px"><span class="big">${data.progressPct}</span><span class="unit">%</span></div>
        <div class="bar"><i style="width:${data.progressPct}%"></i></div>
        <div class="stat-note">${data.lessonsDone} of ${data.lessonsTotal} lessons</div>
      </section>
      <section class="stat">
        <span class="eyebrow mut">REVIEWS DUE</span>
        <div style="display:flex; align-items:baseline; gap:6px; margin-top:12px"><span class="big" style="color:var(--blue)">${data.reviewsDue}</span><span class="unit">cards</span></div>
        <div class="stat-note" style="margin:10px 0 14px">Spaced repetition</div>
        <button class="btn-secondary" data-action="review">Review</button>
      </section>
    </div>
    ${masteryHTML(data.masteryCounts)}
    </div>
  `;
}
