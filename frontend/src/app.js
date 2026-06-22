import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { DASHBOARD_SEED, SAMPLE_LESSON } from "./seed.js";
import { shellHTML } from "./views/shell.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML } from "./views/lesson.js";
import { diagnosticHTML } from "./views/diagnostic.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const FLUSH_INTERVAL_MS = 15000;

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const doc = window.document;
  const sessionId = getSessionId(storage);

  const log = (type, payload = null) =>
    appendEvent(storage, buildEvent({ type, sessionId, payload, now: () => new Date(), newId }));
  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });

  log("session_start");
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const root = doc.getElementById("app");

  // ---- mutable UI state ----
  const ui = {
    tab: "dashboard",
    timer: { running: false, elapsed: 0, intervalId: null },
    lesson: { answer: "", hintVisible: false, solutionRevealed: false },
    diagnostic: {},
  };

  // ---- diagnostic flow ----
  function showDiagnostic() {
    root.innerHTML = diagnosticHTML(ui.diagnostic);
    root.querySelectorAll("[data-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        let v = btn.getAttribute("data-value");
        if (v === "true") v = true;
        else if (v === "false") v = false;
        ui.diagnostic[btn.getAttribute("data-q")] = v;
        showDiagnostic();
      });
    });
    const finish = root.querySelector('[data-action="finish-diagnostic"]');
    finish.addEventListener("click", async () => {
      const profile = buildProfile(ui.diagnostic);
      log("diagnostic_completed", profile);
      await saveProfile({ fetch, endpoint: PROFILE_ENDPOINT, profile });
      await doFlush();
      showApp();
    });
  }

  // ---- dashboard render helper (used on first render and each timer tick) ----
  function paintDashboard() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(DASHBOARD_SEED, timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startSession);
    view.querySelector('[data-action="review"]').addEventListener("click", () => log("review_opened"));
  }

  // ---- main app (shell + tabbed views) ----
  function renderView() {
    if (ui.tab === "dashboard") {
      paintDashboard();
    } else {
      const view = root.querySelector("#view");
      view.innerHTML = lessonHTML(SAMPLE_LESSON, ui.lesson);
      const ta = view.querySelector('[data-field="answer"]');
      ta.addEventListener("input", () => {
        ui.lesson.answer = ta.value;
        const sel = ta.selectionStart;
        renderView();
        const ta2 = root.querySelector('[data-field="answer"]');
        ta2.focus();
        ta2.setSelectionRange(sel, sel);
      });
      view.querySelector('[data-action="toggle-hint"]').addEventListener("click", () => {
        ui.lesson.hintVisible = !ui.lesson.hintVisible;
        if (ui.lesson.hintVisible) log("hint_revealed", { topic: SAMPLE_LESSON.topic });
        renderView();
      });
      view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
        if (!ui.lesson.answer.trim()) return; // gate: must attempt first
        if (!ui.lesson.solutionRevealed) log("solution_revealed", { topic: SAMPLE_LESSON.topic });
        ui.lesson.solutionRevealed = true;
        renderView();
      });
      view.querySelector('[data-action="back"]').addEventListener("click", () => switchTab("dashboard"));
      view.querySelector('[data-action="continue"]').addEventListener("click", () =>
        log("lesson_continue", { step: SAMPLE_LESSON.step }),
      );
    }
  }

  function bindTabs() {
    root.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
    });
  }

  function switchTab(tab) {
    if (tab === ui.tab) return;
    ui.tab = tab;
    log("view_switch", { to: tab });
    showApp();
  }

  function startSession() {
    if (ui.timer.running) return;
    ui.timer.running = true;
    log("session_timer_start", { topic: DASHBOARD_SEED.topic });
    ui.timer.intervalId = window.setInterval(() => {
      ui.timer.elapsed += 1;
      if (ui.timer.elapsed >= TOTAL_SECONDS) {
        window.clearInterval(ui.timer.intervalId);
        ui.timer.running = false;
        log("session_timer_complete");
      }
      if (ui.tab === "dashboard") paintDashboard();
    }, 1000);
  }

  function showApp() {
    root.innerHTML = shellHTML({ activeTab: ui.tab, streakDays: DASHBOARD_SEED.streakDays });
    bindTabs();
    renderView();
  }

  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  if (profile) showApp();
  else showDiagnostic();
}
