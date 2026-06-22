import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { listCourses, loadCourse, loadLesson } from "./courses.js";
import { shellHTML } from "./views/shell.js";
import { homeHTML } from "./views/home.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML } from "./views/lesson.js";
import { diagnosticHTML } from "./views/diagnostic.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const COURSES_ENDPOINT = "/api/courses";
const FLUSH_INTERVAL_MS = 15000;
const SESSION_MIN = 90;
const STREAK_DAYS = 12; // placeholder until a stats endpoint exists

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const doc = window.document;
  const sessionId = getSessionId(storage);

  const log = (type, { courseId = null, topicId = null, payload = null } = {}) =>
    appendEvent(
      storage,
      buildEvent({ type, sessionId, courseId, topicId, payload, now: () => new Date(), newId }),
    );
  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });

  log("session_start");
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const root = doc.getElementById("app");

  const ui = {
    screen: "home",
    courseId: null,
    manifest: null,
    summary: null,
    lesson: null,
    lessonState: { answer: "", hintVisible: false, solutionRevealed: false },
    timer: { running: false, elapsed: 0, intervalId: null },
    diagnostic: {},
  };

  // ---- diagnostic (unchanged flow, now lands on the home) ----
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
    root.querySelector('[data-action="finish-diagnostic"]').addEventListener("click", async () => {
      const profile = buildProfile(ui.diagnostic);
      log("diagnostic_completed", { payload: profile });
      await saveProfile({ fetch, endpoint: PROFILE_ENDPOINT, profile });
      await doFlush();
      showHome();
    });
  }

  // ---- home ----
  async function showHome() {
    ui.screen = "home";
    ui.courseId = null;
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS });
    const view = root.querySelector("#view");
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    view.innerHTML = homeHTML(courses);
    view.querySelectorAll("[data-course]").forEach((card) => {
      card.addEventListener("click", () => openCourse(card.getAttribute("data-course")));
    });
    view.querySelector('[data-action="add-course"]').addEventListener("click", () => {
      log("add_course_clicked");
      window.alert("Course creation is coming soon.");
    });
  }

  // ---- course session screen ----
  async function refreshSummary() {
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    ui.summary = courses.find((c) => c.id === ui.courseId) || null;
  }

  async function openCourse(courseId) {
    ui.courseId = courseId;
    ui.manifest = await loadCourse({ fetch, courseId });
    await refreshSummary();
    log("course_opened", { courseId });
    showCourse();
  }

  function sessionData() {
    const next = ui.summary && ui.summary.nextLesson;
    const p = ui.summary ? ui.summary.progress : { done: 0, total: 0, pct: 0 };
    return {
      topic: next ? next.title : "Course complete",
      sub: next ? `${next.moduleTitle} · ${ui.manifest.title}` : ui.manifest.title,
      durationMin: SESSION_MIN,
      progressPct: p.pct,
      lessonsDone: p.done,
      lessonsTotal: p.total,
      reviewsDue: ui.summary ? ui.summary.reviewsDue : 0,
      streakDays: STREAK_DAYS,
    };
  }

  function paintCourse() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(sessionData(), timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startLesson);
    view.querySelector('[data-action="review"]').addEventListener("click", () =>
      log("review_opened", { courseId: ui.courseId }),
    );
  }

  function showCourse() {
    ui.screen = "course";
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintCourse();
  }

  // ---- lesson ----
  async function startLesson() {
    const next = ui.summary && ui.summary.nextLesson;
    if (!next) return;
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: next.id });
    if (!ui.lesson) return;
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false };
    log("lesson_view", { courseId: ui.courseId, topicId: next.id });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  function showLesson() {
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ streakDays: STREAK_DAYS, back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintLesson();
  }

  function paintLesson() {
    const view = root.querySelector("#view");
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState);
    const ta = view.querySelector('[data-field="answer"]');
    ta.addEventListener("input", () => {
      ui.lessonState.answer = ta.value;
      const sel = ta.selectionStart;
      paintLesson();
      const ta2 = root.querySelector('[data-field="answer"]');
      ta2.focus();
      ta2.setSelectionRange(sel, sel);
    });
    view.querySelector('[data-action="toggle-hint"]').addEventListener("click", () => {
      ui.lessonState.hintVisible = !ui.lessonState.hintVisible;
      if (ui.lessonState.hintVisible) log("hint_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      paintLesson();
    });
    view.querySelector('[data-action="reveal-solution"]').addEventListener("click", () => {
      if (!ui.lessonState.answer.trim()) return;
      if (!ui.lessonState.solutionRevealed)
        log("solution_revealed", { courseId: ui.courseId, topicId: ui.lesson.id });
      ui.lessonState.solutionRevealed = true;
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
    view.querySelector('[data-action="continue"]').addEventListener("click", async () => {
      log("lesson_completed", { courseId: ui.courseId, topicId: ui.lesson.id });
      await doFlush();
      await refreshSummary(); // progress advances; next lesson moves on
      showCourse();
    });
  }

  function startTimer() {
    ui.timer.running = true;
    log("session_timer_start", { courseId: ui.courseId });
    ui.timer.intervalId = window.setInterval(() => {
      ui.timer.elapsed += 1;
      if (ui.timer.elapsed >= TOTAL_SECONDS) {
        window.clearInterval(ui.timer.intervalId);
        ui.timer.running = false;
        log("session_timer_complete", { courseId: ui.courseId });
      }
      if (ui.screen === "course") paintCourse();
    }, 1000);
  }

  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  if (profile) showHome();
  else showDiagnostic();
}
