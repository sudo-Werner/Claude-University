export const DIAGNOSTIC = [
  {
    key: "contentOrder",
    question: "When learning something new, what works better for you?",
    options: [
      { label: "Give me the rule/theory first, then code", value: "theory_first" },
      { label: "Show me examples; I'll figure out the rule", value: "examples_first" },
    ],
  },
  {
    key: "stuckStrategy",
    question: "You're stuck 20 minutes into a lesson. What helps most?",
    options: [
      { label: "Push through — confusion is part of learning", value: "push" },
      { label: "Review the prerequisite first", value: "review_prereq" },
      { label: "Skip it and come back later", value: "skip" },
    ],
  },
  {
    key: "wrongAnswerFeedback",
    question: "You get a quiz question wrong. What do you want?",
    options: [
      { label: "Show the correct answer immediately", value: "immediate" },
      { label: "Give a hint and let me try again", value: "hint" },
      { label: "Just flag it wrong — I'll work it out", value: "self" },
    ],
  },
  {
    key: "sessionStyle",
    question: "When you study, how do you prefer to focus?",
    options: [
      { label: "Go deep on one topic at a time", value: "deep_block" },
      { label: "Move across several topics", value: "sprints" },
    ],
  },
  {
    key: "lessonStructure",
    question: "Starting a new lesson, where do you like to begin?",
    options: [
      { label: "Big picture first, then zoom into detail", value: "top_down" },
      { label: "Smallest building block first, build up", value: "bottom_up" },
    ],
  },
  {
    key: "analogies",
    question: "Do analogies (e.g. 'a neural net is like the brain') help you?",
    options: [
      { label: "Yes — they help me grasp things faster", value: true },
      { label: "No — I prefer direct explanation", value: false },
    ],
  },
];

export function buildProfile(answers) {
  return {
    contentOrder: answers.contentOrder,
    stuckStrategy: answers.stuckStrategy,
    wrongAnswerFeedback: answers.wrongAnswerFeedback,
    sessionStyle: answers.sessionStyle,
    lessonStructure: answers.lessonStructure,
    analogies: answers.analogies,
  };
}

export async function saveProfile({ fetch, endpoint, profile }) {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  return resp.json();
}

export async function loadProfile({ fetch, endpoint }) {
  const resp = await fetch(endpoint);
  if (!resp.ok) throw new Error(`profile fetch failed: ${resp.status}`);
  const body = await resp.json();
  return body && body.data ? body.data : null;
}
