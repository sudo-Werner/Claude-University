// #3b — loading states for the multi-second Claude waits. A skeleton of the layout
// plus a status line that narrates "what Claude is doing" (cycled by app.js). Research:
// skeletons + staged status recover most of the perceived-speed benefit, pure CSS/JS.

export const LESSON_STAGES = [
  "Reading the topic…",
  "Writing the exercise…",
  "Preparing the hint and checks…",
  "Almost ready…",
];
export const DEEPEN_STAGES = [
  "Re-reading the lesson…",
  "Re-establishing the fundamentals…",
  "Working through a clear example…",
  "Almost ready…",
];
export const CAPSTONE_STAGES = [
  "Recalling what you covered…",
  "Finding real-world examples…",
  "Writing the connections…",
  "Almost ready…",
];
export const PROGRAM_STAGES = [
  "Reading your brief…",
  "Searching canonical sources…",
  "Designing modules and lessons…",
  "Writing measurable objectives…",
  "Fact-checking against the sources…",
  "Assembling your syllabus…",
];
export const EXAM_STAGES = [
  "Reading the objectives…",
  "Writing questions that test them…",
  "Setting plausible distractors…",
  "Almost ready…",
];

function bars(kind) {
  if (kind === "capstone") {
    return (
      `<div class="sk sk-line w70"></div><div class="sk sk-line"></div>` +
      `<div class="sk sk-item"></div><div class="sk sk-item"></div><div class="sk sk-item"></div>`
    );
  }
  return (
    `<div class="sk sk-eyebrow"></div><div class="sk sk-line"></div>` +
    `<div class="sk sk-line"></div><div class="sk sk-line w70"></div>` +
    `<div class="sk sk-box"></div>`
  );
}

export function loadingHTML(kind, firstMsg) {
  return (
    `<div class="card lesson loading-card">` +
    `<div class="load-status"><span class="load-dot"></span><span class="load-msg">${firstMsg}</span></div>` +
    `<div class="skeleton">${bars(kind)}</div>` +
    `</div>`
  );
}
