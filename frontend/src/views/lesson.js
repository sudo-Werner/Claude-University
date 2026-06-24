import { solutionState } from "../reveal.js";
import { checksHTML } from "./checks.js";

const BULB = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.2 1 2.5h6c0-1.3.3-1.8 1-2.5A6 6 0 0012 3z" stroke="#e0892f" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const LOCK = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 11V8a4 4 0 018 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`;
const ARROW = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const REVEAL_TEXT = {
  locked: "Attempt first to unlock the solution",
  ready: "Reveal solution",
  shown: "Solution shown",
};
const HINT_TEXT = { true: "Hide hint", false: "Show hint" };

export function lessonHTML(lesson, state) {
  const segs = Array.from({ length: lesson.totalSteps }, (_, i) => {
    if (i + 1 < lesson.step) return '<i class="done"></i>';
    if (i + 1 === lesson.step) return '<i class="now"></i>';
    return "<i></i>";
  }).join("");

  const sol = solutionState({ answer: state.answer, revealed: state.solutionRevealed });
  const hint = state.hintVisible
    ? `<div class="hint" style="margin-bottom:10px">${lesson.hintHtml}</div>`
    : "";
  const solutionPanel = state.solutionRevealed
    ? `<div class="solution"><div class="lbl">SOLUTION</div><div class="ans">${lesson.solutionAns}</div><div class="note">${lesson.solutionNote}</div></div>`
    : "";

  return `
    <div class="lesson-col">
    <div>
      <div class="steps">${segs}</div>
      <div class="steprow"><span>Step ${lesson.step} of ${lesson.totalSteps} · <b>Exercise</b></span><span class="right">${lesson.topic}</span></div>
    </div>
    <section class="card lesson">
      <span class="eyebrow">${lesson.eyebrow}</span>
      <p class="prompt">${lesson.promptHtml}</p>
      <textarea data-field="answer" placeholder="Write your update here…" style="min-height:64px; margin:12px 0">${state.answer}</textarea>
      <button class="hint-toggle" data-action="toggle-hint" style="margin-bottom:10px">${BULB}<span style="flex:1">${HINT_TEXT[state.hintVisible]}</span></button>
      ${hint}
      <button class="reveal ${sol}" data-action="reveal-solution">${LOCK}<span style="flex:1">${REVEAL_TEXT[sol]}</span></button>
      ${solutionPanel}
    </section>
    ${state.solutionRevealed ? checksHTML(lesson.checks || [], state) : ""}
    <div class="nav">
      <button class="btn-back" data-action="back">Back</button>
      ${
        state.solutionRevealed
          ? `<div class="rate" role="group" aria-label="Rate recall">
               <span class="rate-q">How well did you recall this?</span>
               <button class="rate-btn" data-quality="again">Again</button>
               <button class="rate-btn" data-quality="hard">Hard</button>
               <button class="rate-btn" data-quality="good">Good</button>
               <button class="rate-btn" data-quality="easy">Easy</button>
             </div>`
          : `<button class="btn-primary" data-action="continue" disabled>Reveal solution to finish</button>`
      }
    </div>
    </div>
  `;
}
