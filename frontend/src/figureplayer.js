// Trusted app-side figure player. The model-generated SVG stays pure declarative
// markup; the app pauses the SVG's own SMIL clock and advances it manually each
// frame at the chosen speed, so play/pause/replay/speed all ride one clock.
// (Mechanism verified in the 2026-07-23 heart mockup: rate 1.0 = true time,
// setCurrentTime advances the paused clock.) No executable code ever lives in a
// figure — this is why interactivity stays inside the sanitizer's security model.

export const SPEED_MIN = 0.25;
export const SPEED_MAX = 2.5;

export function clampSpeed(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 1;
  return Math.min(SPEED_MAX, Math.max(SPEED_MIN, n));
}

export function nextTime(t, dtSeconds, speed) {
  const nt = t + Math.max(0, dtSeconds) * clampSpeed(speed);
  return nt < 0 ? 0 : nt;
}

const CONTROLS_HTML =
  '<div class="fig-controls" role="group" aria-label="Figure playback controls">' +
  '<button type="button" data-fig-play aria-pressed="false">Play</button>' +
  '<button type="button" data-fig-replay>Replay</button>' +
  '<label class="fig-speed">Speed ' +
  '<input type="range" min="0.25" max="2.5" step="0.25" value="1" data-fig-speed ' +
  'aria-label="Playback speed"></label></div>';

export function attachFigurePlayer(fig, { reducedMotion = false, win = window } = {}) {
  const svg = fig.querySelector("svg");
  if (!svg || typeof svg.setCurrentTime !== "function") return null;
  if (typeof svg.pauseAnimations === "function") svg.pauseAnimations();

  let playing = false;
  let speed = 1;
  let t = 0;
  let last = null;
  let rafId = null;
  let onScreen = true;

  fig.insertAdjacentHTML("beforeend", CONTROLS_HTML);
  const playBtn = fig.querySelector("[data-fig-play]");
  const replayBtn = fig.querySelector("[data-fig-replay]");
  const speedInput = fig.querySelector("[data-fig-speed]");

  function render() {
    playBtn.textContent = playing ? "Pause" : "Play";
    playBtn.setAttribute("aria-pressed", String(playing));
  }
  function frame(ts) {
    if (!fig.isConnected) {           // figure was detached by a lesson repaint -> stop leaking
      if (observer) observer.disconnect();
      return;                          // do NOT reschedule -> the rAF loop ends
    }
    if (last === null) last = ts;
    const dt = (ts - last) / 1000;
    last = ts;
    if (playing && onScreen) {
      t = nextTime(t, dt, speed);
      svg.setCurrentTime(t);
    }
    rafId = win.requestAnimationFrame(frame);
  }
  function setPlaying(on) {
    playing = on;
    last = null;
    render();
  }

  playBtn.addEventListener("click", () => setPlaying(!playing));
  replayBtn.addEventListener("click", () => {
    t = 0;
    svg.setCurrentTime(0);
    setPlaying(true);
  });
  speedInput.addEventListener("input", () => { speed = clampSpeed(speedInput.value); });

  // Pause off-screen figures; resume only if the learner had it playing.
  let observer = null;
  if (typeof win.IntersectionObserver === "function") {
    observer = new win.IntersectionObserver((entries) => {
      for (const e of entries) onScreen = e.isIntersecting;
    });
    observer.observe(fig);
  }

  setPlaying(false); // default paused: read-first / low-glare — reduced-motion is satisfied by the default too
  render();
  rafId = win.requestAnimationFrame(frame);

  return {
    isPlaying: () => playing,
    setPlaying,
    destroy() {
      if (rafId) win.cancelAnimationFrame(rafId);
      if (observer) observer.disconnect();
    },
  };
}
