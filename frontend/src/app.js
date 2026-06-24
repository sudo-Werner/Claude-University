import { esc } from "./escape.js";
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { listCourses, loadCourse, loadLesson, createCourse, loadReviews, gradeAnswer, deepenLesson, loadCapstone } from "./courses.js";
import { shellHTML } from "./views/shell.js";
import { homeHTML } from "./views/home.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML } from "./views/lesson.js";
import { curriculumHTML } from "./views/curriculum.js";
import { capstoneHTML } from "./views/capstone.js";
import { loadingHTML, LESSON_STAGES, DEEPEN_STAGES, CAPSTONE_STAGES } from "./views/loading.js";
import { diagnosticHTML } from "./views/diagnostic.js";
import { chatHTML } from "./views/chat.js";
import { gradeCheck } from "./views/checks.js";
import { streamChat } from "./chat.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const COURSES_ENDPOINT = "/api/courses";
const FLUSH_INTERVAL_MS = 15000;
const SESSION_MIN = 90;

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
    chat: null,
    reviewQueue: [],
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
    pauseTimer();
    ui.screen = "home";
    ui.courseId = null;
    root.innerHTML = shellHTML({});
    const view = root.querySelector("#view");
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    view.innerHTML = homeHTML(courses);
    view.querySelectorAll("[data-course]").forEach((card) => {
      card.addEventListener("click", () => openCourse(card.getAttribute("data-course")));
    });
    view.querySelector('[data-action="add-course"]').addEventListener("click", () => {
      log("add_course_clicked");
      showChat();
    });
  }

  // ---- course session screen ----
  async function refreshSummary() {
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    ui.summary = courses.find((c) => c.id === ui.courseId) || null;
    // Reload the manifest too: its mastery/masteryCounts change as lessons are
    // completed, so the dashboard breakdown stays current after a lesson.
    ui.manifest = (await loadCourse({ fetch, courseId: ui.courseId })) || ui.manifest;
  }

  async function openCourse(courseId) {
    ui.courseId = courseId;
    await refreshSummary();
    if (!ui.manifest) { showHome(); return; }
    log("course_opened", { courseId });
    showCourse();
  }

  function flatLessons() {
    const out = [];
    const mods = (ui.manifest && ui.manifest.modules) || [];
    mods.forEach((m) => (m.lessons || []).forEach((l) => out.push(l)));
    return out;
  }

  function currentLessonId() {
    if (ui.lesson) return ui.lesson.id;
    return ui.summary && ui.summary.nextLesson ? ui.summary.nextLesson.id : null;
  }

  function adjacentLesson(offset) {
    const flat = flatLessons();
    const i = flat.findIndex((l) => ui.lesson && l.id === ui.lesson.id);
    if (i < 0) return null;
    const j = i + offset;
    return j >= 0 && j < flat.length ? flat[j] : null;
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
      masteryCounts: (ui.manifest && ui.manifest.masteryCounts) || {},
    };
  }

  function paintCourse() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(sessionData(), timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startLesson);
    view.querySelector('[data-action="review"]').addEventListener("click", startReviewSession);
    const cur = view.querySelector('[data-action="curriculum"]');
    if (cur) cur.addEventListener("click", showCurriculum);
  }

  function showCourse() {
    pauseTimer();
    ui.screen = "course";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintCourse();
  }

  function showCurriculum() {
    pauseTimer();
    ui.screen = "curriculum";
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintCurriculum();
  }

  function paintCurriculum() {
    const view = root.querySelector("#view");
    view.innerHTML = curriculumHTML(ui.manifest, (ui.manifest && ui.manifest.mastery) || {}, currentLessonId());
    view.querySelectorAll("[data-lesson]").forEach((row) => {
      row.addEventListener("click", () => openLesson(row.getAttribute("data-lesson")));
    });
    view.querySelectorAll("[data-capstone]").forEach((b) => {
      b.addEventListener("click", () => showCapstone(b.getAttribute("data-capstone")));
    });
  }

  // #1: real-world connections capstone for a completed module (scope = module id)
  // or the whole course (scope = "course"). Generated on first open, cached after.
  async function showCapstone(scope) {
    pauseTimer();
    ui.screen = "capstone";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCurriculum);
    const view = root.querySelector("#view");
    startLoading(view, "capstone", CAPSTONE_STAGES);
    log("capstone_opened", { courseId: ui.courseId, topicId: scope });
    const cap = await loadCapstone({ fetch, courseId: ui.courseId, scope });
    if (ui.screen !== "capstone") return;
    if (!cap || cap.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((cap && cap.error) || "Couldn't load this right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
      return;
    }
    view.innerHTML = capstoneHTML(cap);
    view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
  }

  // #3b: render a skeleton + cycle the "what Claude is doing" status. The interval
  // self-clears once its status node leaves the DOM (i.e. the view was repainted or
  // the user navigated away), so no caller bookkeeping is needed.
  function startLoading(view, kind, stages) {
    view.innerHTML = loadingHTML(kind, stages[0]);
    const msg = view.querySelector(".load-msg");
    let i = 1;
    const id = window.setInterval(() => {
      if (!msg || !msg.isConnected) { window.clearInterval(id); return; } // repainted/navigated away
      msg.textContent = stages[i % stages.length];
      i += 1;
    }, 1800);
  }

  // ---- lesson ----
  async function openLesson(lessonId) {
    if (!lessonId) return;
    ui.reviewQueue = [];
    const view = root.querySelector("#view");
    if (view) startLoading(view, "lesson", LESSON_STAGES);
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId });
    if (lessonFailed(ui.lesson)) { showLessonError(ui.lesson && ui.lesson.error || "Couldn't load this lesson."); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: lessonId });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  function startLesson() {
    const next = ui.summary && ui.summary.nextLesson;
    if (next) openLesson(next.id);
  }

  // #5: the learner says they're rusty — regenerate THIS lesson deeper (assume less
  // prior knowledge, add fundamentals) and overwrite the cache. Logged so we can see
  // which lessons were pitched too high (the depth-scoping signal). Long wait, so show
  // a loading card; discard the result if the learner navigated away meanwhile.
  async function deepenCurrentLesson() {
    if (!ui.lesson) return;
    const lessonId = ui.lesson.id;
    log("lesson_deepened", { courseId: ui.courseId, topicId: lessonId });
    const view = root.querySelector("#view");
    if (view) startLoading(view, "lesson", DEEPEN_STAGES);
    const deeper = await deepenLesson({ fetch, courseId: ui.courseId, lessonId });
    if (ui.screen !== "lesson" || !ui.lesson || ui.lesson.id !== lessonId) return;
    if (lessonFailed(deeper)) {
      ui.lessonState = { ...ui.lessonState, deepenError: (deeper && deeper.error) || "Couldn't rewrite this lesson right now." };
      showLesson();
      return;
    }
    ui.lesson = deeper;
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: lessonId });
    showLesson();
  }

  function showLesson() {
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintLesson();
  }

  function paintLesson() {
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
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
    // #4: Claude grades the typed answer on demand (decoupled from reveal, so the
    // learner can check, revise, and re-check before giving up). Transient — not
    // logged. Capture lessonState identity + screen so a result that lands after
    // the learner has navigated away is discarded rather than painted over.
    const checkBtn = view.querySelector('[data-action="check-answer"]');
    if (checkBtn) checkBtn.addEventListener("click", async () => {
      const answer = ui.lessonState.answer.trim();
      if (!answer || ui.lessonState.grading) return;
      ui.lessonState.grading = true;
      paintLesson();
      const lessonState = ui.lessonState;
      const grade = await gradeAnswer({ fetch, courseId: ui.courseId, lessonId: ui.lesson.id, answer });
      if (ui.lessonState !== lessonState || ui.screen !== "lesson") return;
      lessonState.grading = false;
      lessonState.grade = grade;
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
    view.querySelectorAll('[data-quality]').forEach((btn) => {
      btn.addEventListener("click", async () => {
        const quality = btn.getAttribute("data-quality");
        log("lesson_reviewed", { courseId: ui.courseId, topicId: ui.lesson.id, payload: { quality } });
        await doFlush();
        await advanceAfterLesson();
      });
    });
    view.querySelectorAll('[data-check-input]').forEach((inp) => {
      inp.addEventListener("input", () => {
        const i = Number(inp.getAttribute("data-check-input"));
        ui.lessonState.checkAnswers[i] = inp.value;
      });
    });
    view.querySelectorAll('[data-choice]').forEach((btn) => {
      btn.addEventListener("click", () =>
        answerCheck(Number(btn.getAttribute("data-check")), Number(btn.getAttribute("data-choice"))),
      );
    });
    view.querySelectorAll('[data-action="check-fill"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = Number(btn.getAttribute("data-check"));
        const inp = view.querySelector(`[data-check-input="${i}"]`);
        answerCheck(i, inp ? inp.value : "");
      });
    });
    const deepenBtn = view.querySelector('[data-action="deepen-lesson"]');
    if (deepenBtn) deepenBtn.addEventListener("click", deepenCurrentLesson);
    const curBtn = view.querySelector('[data-action="curriculum"]');
    if (curBtn) curBtn.addEventListener("click", showCurriculum);
    const prevBtn = view.querySelector('[data-action="prev-lesson"]');
    if (prevBtn) prevBtn.addEventListener("click", () => { const a = adjacentLesson(-1); if (a) openLesson(a.id); });
    const nextBtn = view.querySelector('[data-action="next-lesson"]');
    if (nextBtn) nextBtn.addEventListener("click", () => { const a = adjacentLesson(1); if (a) openLesson(a.id); });
  }

  function answerCheck(i, answer) {
    const check = ui.lesson.checks && ui.lesson.checks[i];
    if (!check || ui.lessonState.checkResults[i]) return;
    const result = gradeCheck(check, answer);
    ui.lessonState.checkAnswers[i] = answer;
    ui.lessonState.checkResults[i] = { correct: result.correct };
    log("lesson_check", {
      courseId: ui.courseId,
      topicId: ui.lesson.id,
      payload: { index: i, type: check.type, correct: result.correct },
    });
    paintLesson();
  }

  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (lessonFailed(ui.lesson)) { await refreshSummary(); showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    showCourse();
  }

  async function startReviewSession() {
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    ui.lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (lessonFailed(ui.lesson)) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  // ---- course creation chat ----
  function showChat() {
    pauseTimer();
    ui.screen = "chat";
    ui.chat = { messages: [], proposal: null, pending: false };
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintChat();
  }

  function paintChat() {
    const view = root.querySelector("#view");
    view.innerHTML = chatHTML(ui.chat.messages, { pending: ui.chat.pending });
    if (ui.chat.proposal) {
      const card = doc.createElement("div");
      card.className = "card proposal";
      card.innerHTML =
        `<div class="eyebrow">PROPOSED COURSE</div>` +
        `<h2 class="session-topic">${esc(ui.chat.proposal.title)}</h2>` +
        `<div class="session-sub">${esc(ui.chat.proposal.subtitle || "")}</div>` +
        `<button class="btn-primary" data-action="create-course">Create this course</button>`;
      view.querySelector(".chat-thread").appendChild(card);
      card.querySelector('[data-action="create-course"]').addEventListener("click", createFromProposal);
    }
    const send = view.querySelector('[data-action="send"]');
    if (send) send.addEventListener("click", sendChat);
  }

  async function sendChat() {
    const ta = root.querySelector('[data-field="chat"]');
    const text = ta.value.trim();
    if (!text || ui.chat.pending) return;
    ui.chat.messages.push({ role: "user", content: text });       // raw
    const reply = { role: "assistant", content: "" };
    ui.chat.messages.push(reply);
    ui.chat.pending = true;
    paintChat();
    const history = ui.chat.messages
      .filter((m) => m !== reply)                                  // exclude the in-progress placeholder
      .map((m) => ({ role: m.role, content: m.content }));
    await streamChat({
      fetch,
      messages: history,
      onDelta: (d) => { reply.content += d; paintChat(); },
      onProposal: (p) => { ui.chat.proposal = p; },
      onDone: () => { ui.chat.pending = false; paintChat(); },
      onError: (e) => { reply.content = "⚠️ " + (e.message || "Claude is unavailable right now."); ui.chat.pending = false; paintChat(); },
    });
  }

  async function createFromProposal() {
    const course = await createCourse({ fetch, proposal: ui.chat.proposal });
    if (course) { log("course_created", { courseId: course.id }); openCourse(course.id); }
  }

  function lessonFailed(l) { return !l || l.error; }

  function showLessonError(message) {
    pauseTimer();
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card lesson"><div class="prompt">${esc(message)}</div>` +
      `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
  }

  // The session clock counts only while you're actively in a lesson. start/resume
  // is idempotent; pauseTimer freezes elapsed when you leave the lesson screen.
  function startTimer() {
    if (ui.timer.running) return;
    ui.timer.running = true;
    if (ui.timer.elapsed === 0) log("session_timer_start", { courseId: ui.courseId });
    ui.timer.intervalId = window.setInterval(() => {
      ui.timer.elapsed += 1;
      if (ui.timer.elapsed >= TOTAL_SECONDS) {
        pauseTimer();
        log("session_timer_complete", { courseId: ui.courseId });
      }
    }, 1000);
  }

  function pauseTimer() {
    if (ui.timer.intervalId) window.clearInterval(ui.timer.intervalId);
    ui.timer.intervalId = null;
    ui.timer.running = false;
  }

  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  if (profile) showHome();
  else showDiagnostic();
}
