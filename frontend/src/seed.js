export const DASHBOARD_SEED = {
  topic: "Backpropagation, intuitively",
  sub: "Module 3 · Neural Networks · Lesson 2",
  durationMin: 90,
  progressPct: 30,
  lessonsDone: 12,
  lessonsTotal: 40,
  reviewsDue: 8,
  streakDays: 12,
};

export const SAMPLE_LESSON = {
  step: 4,
  totalSteps: 5,
  topic: "Backpropagation",
  eyebrow: "EXERCISE",
  promptHtml:
    'A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>. ' +
    'With learning rate <code>η = 0.1</code>, write the gradient-descent update for <code>w</code>.',
  hintHtml:
    'Gradient descent moves <em>against</em> the gradient: <span class="mono">w ← w − η · ∂L/∂w</span>',
  solutionAns: "w ← w − (0.1 × 0.4) = w − 0.04",
  solutionNote:
    "Each step subtracts the learning rate times the gradient — a small move downhill on the loss.",
};
