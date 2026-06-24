export const PHASE_SECONDS = [900, 3600, 900];
export const TOTAL_SECONDS = PHASE_SECONDS.reduce((a, b) => a + b, 0);
export const PHASE_NAMES = ["Warm-up", "Peak focus", "Cool-down"];

function mmss(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function timerView(elapsedSeconds) {
  const e = Math.max(0, Math.min(elapsedSeconds, TOTAL_SECONDS));
  const fills = [];
  let remaining = e;
  for (const len of PHASE_SECONDS) {
    const inThis = Math.max(0, Math.min(remaining, len));
    fills.push(len === 0 ? 0 : inThis / len);
    remaining -= inThis;
  }

  let activePhaseIndex = 0;
  let acc = 0;
  for (let i = 0; i < PHASE_SECONDS.length; i++) {
    acc += PHASE_SECONDS[i];
    if (e < acc) {
      activePhaseIndex = i;
      break;
    }
    activePhaseIndex = i;
  }

  const complete = e >= TOTAL_SECONDS;
  const statusLabel = complete
    ? "<b>Session complete</b>"
    : `<b>${PHASE_NAMES[activePhaseIndex]}</b> in progress`;

  return { fills, activePhaseIndex, statusLabel, clock: `${mmss(e)} / ${mmss(TOTAL_SECONDS)}` };
}
