export function canReveal(answer) {
  return typeof answer === "string" && answer.trim().length > 0;
}

export function solutionState({ answer, revealed }) {
  if (revealed) return "shown";
  return canReveal(answer) ? "ready" : "locked";
}
