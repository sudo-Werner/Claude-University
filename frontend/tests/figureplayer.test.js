import { test } from "node:test";
import assert from "node:assert/strict";
import { clampSpeed, nextTime, SPEED_MIN, SPEED_MAX, attachFigurePlayer } from "../src/figureplayer.js";

test("clampSpeed clamps to [0.25, 2.5] and defaults non-finite to 1", () => {
  assert.equal(clampSpeed(0.1), SPEED_MIN);
  assert.equal(clampSpeed(9), SPEED_MAX);
  assert.equal(clampSpeed(1.5), 1.5);
  assert.equal(clampSpeed("x"), 1);
});

test("nextTime advances by dt*speed and never goes negative", () => {
  assert.equal(nextTime(0, 1, 1), 1);
  assert.equal(nextTime(2, 0.5, 2.5), 2 + 0.5 * 2.5);
  assert.equal(nextTime(0, -1, 1), 0); // negative dt clamped
});

// Regression guard for the rAF-leak-on-repaint fix: paintLesson() replaces
// view.innerHTML on every repaint (answer checks, stage changes, navigation)
// without ever calling the player's destroy(), so the player itself must
// notice its figure left the document and stop rescheduling its own loop.
// Driven entirely with fakes (no real DOM) so this locks the actual
// attachFigurePlayer code path, not a reimplementation of it.
test("attachFigurePlayer's frame loop self-terminates once its figure is detached", () => {
  const rafCallbacks = [];
  let rafIdCounter = 0;
  let observerDisconnectCalls = 0;

  const fakeObserver = {
    observe() {},
    disconnect() { observerDisconnectCalls++; },
  };

  const fakeWin = {
    requestAnimationFrame(cb) {
      rafCallbacks.push(cb);
      return ++rafIdCounter;
    },
    cancelAnimationFrame() {},
    IntersectionObserver: function FakeIntersectionObserver(_cb) {
      return fakeObserver; // constructor returning an object -> `new` uses it as-is
    },
  };

  const fakeSvg = {
    setCurrentTime() {},
    pauseAnimations() {},
  };

  function fakeControl() {
    return {
      textContent: "",
      addEventListener() {},
      setAttribute() {},
    };
  }
  const playBtn = fakeControl();
  const replayBtn = fakeControl();
  const speedInput = fakeControl();

  const fig = {
    isConnected: true,
    insertAdjacentHTML() {}, // no real DOM -- the controls below are faked via querySelector
    querySelector(sel) {
      if (sel === "svg") return fakeSvg;
      if (sel === "[data-fig-play]") return playBtn;
      if (sel === "[data-fig-replay]") return replayBtn;
      if (sel === "[data-fig-speed]") return speedInput;
      return null;
    },
  };

  const player = attachFigurePlayer(fig, { win: fakeWin });
  assert.ok(player, "attachFigurePlayer should return a player for a valid fig/svg");
  assert.equal(rafCallbacks.length, 1, "attach schedules the first frame");

  // Figure still connected -> the loop must reschedule itself.
  rafCallbacks[0](16);
  assert.equal(rafCallbacks.length, 2, "a connected figure's frame reschedules");
  assert.equal(observerDisconnectCalls, 0);

  // Simulate a lesson repaint (view.innerHTML = ...) detaching this figure.
  fig.isConnected = false;
  rafCallbacks[1](32);

  assert.equal(rafCallbacks.length, 2, "a detached figure's frame must NOT reschedule");
  assert.equal(observerDisconnectCalls, 1, "a detached figure's frame must disconnect its observer");
});
