import { esc } from "./escape.js";
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { listCourses, loadCourse, loadLesson, getLessonStatus, createCourse, loadReviews, loadReviewItems, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, compileProgram, reviseCourse, applyRevision, explainAnswer, gradeTeaching, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply, submitCapstone, sendFeedback } from "./courses.js";
import { loadStats, loadActivity } from "./stats.js";
import { shellHTML, feedbackBarHTML } from "./views/shell.js";
import { homeHTML } from "./views/home.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML, ratingLocked } from "./views/lesson.js";
import { activateHTML } from "./views/activate.js";
import { curriculumHTML } from "./views/curriculum.js";
import { capstoneHTML } from "./views/capstone.js";
import { libraryHTML } from "./views/library.js";
import { loadingHTML, LESSON_STAGES, DEEPEN_STAGES, CAPSTONE_STAGES, PROGRAM_STAGES, EXAM_STAGES, REMEDIATION_STAGES } from "./views/loading.js";
import { examHTML, examResultHTML, examReady } from "./views/exam.js";
import { diagnosticHTML } from "./views/diagnostic.js";
import { chatHTML } from "./views/chat.js";
import { syllabusHTML } from "./views/syllabus.js";
import { gradeCheck } from "./views/checks.js";
import { revisionHTML } from "./views/revision.js";
import { activityHTML } from "./views/activity.js";
import { remediationHTML, flatPractice } from "./views/remediation.js";
import { transcriptHTML } from "./views/transcript.js";
import { streamChat } from "./chat.js";
import { loadWorkspace, saveWorkspace } from "./notes.js";

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
    stats: null,
    feedback: { open: false, sending: false, text: "", notice: "" },
  };

  // ---- feedback bar (global; delegated on root so it survives every shell repaint) ----
  function paintFeedbackBar() {
    const slot = root.querySelector("[data-fb-slot]");
    if (slot) slot.innerHTML = feedbackBarHTML(ui.feedback);
  }

  async function submitFeedback() {
    const fb = ui.feedback;
    const text = (fb.text || "").trim();
    if (!text || fb.sending) return;
    fb.sending = true;
    fb.notice = "";
    paintFeedbackBar();
    const result = await sendFeedback({
      fetch,
      text,
      screen: ui.screen,
      courseId: ui.courseId,
      lessonId: ui.lesson ? ui.lesson.id : null,
    });
    fb.sending = false;
    if (result && result.error) {
      fb.notice = "error";
      paintFeedbackBar();
      return;
    }
    fb.text = "";
    fb.notice = "sent";
    paintFeedbackBar();
    window.setTimeout(() => {
      // Collapse only if the thank-you is still showing — a toggle or a new
      // note during the 2.5s clears the notice and cancels the auto-collapse.
      if (ui.feedback.notice === "sent") {
        ui.feedback.notice = "";
        ui.feedback.open = false;
        paintFeedbackBar();
      }
    }, 2500);
  }

  root.addEventListener("click", (e) => {
    if (e.target.closest('[data-action="feedback-toggle"]')) {
      ui.feedback.open = !ui.feedback.open;
      ui.feedback.notice = "";
      paintFeedbackBar();
      if (ui.feedback.open) {
        const inp = root.querySelector('[data-field="fb-text"]');
        if (inp) inp.focus();
      }
      return;
    }
    if (e.target.closest('[data-action="feedback-send"]')) submitFeedback();
  });
  root.addEventListener("input", (e) => {
    if (e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      // Update state without a repaint (focus-steal rule); flip only the
      // Send button's disabled property directly.
      ui.feedback.text = e.target.value;
      const btn = root.querySelector('[data-action="feedback-send"]');
      if (btn) btn.disabled = ui.feedback.sending || !e.target.value.trim();
    }
  });
  root.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      submitFeedback();
    }
  });

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
    const act = view.querySelector('[data-action="activity"]');
    if (act) act.addEventListener("click", showActivity);
    const tr = view.querySelector('[data-action="transcript"]');
    if (tr) tr.addEventListener("click", showTranscript);
  }

  // ---- activity log ----
  async function showActivity() {
    pauseTimer();
    ui.screen = "activity";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Loading your activity…</div></div>`;
    const entries = await loadActivity({ fetch });
    if (ui.screen !== "activity") return; // navigated away mid-load
    view.innerHTML = activityHTML(entries, { now: new Date() });
  }

  // ---- course session screen ----
  async function refreshSummary() {
    const courses = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    ui.summary = courses.find((c) => c.id === ui.courseId) || null;
    // Reload the manifest too: its mastery/masteryCounts change as lessons are
    // completed, so the dashboard breakdown stays current after a lesson.
    ui.manifest = (await loadCourse({ fetch, courseId: ui.courseId })) || ui.manifest;
    ui.stats = (await loadStats({ fetch })) || ui.stats;
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
      complete: !next,
      masteryCounts: (ui.manifest && ui.manifest.masteryCounts) || {},
      contract: (ui.manifest && ui.manifest.schemaVersion === 2) ? {
        level: (ui.manifest.level && (ui.manifest.level.label || ui.manifest.level.code)) || "",
        hours: ui.manifest.targetHours || null,
        skills: ui.manifest.skills || [],
      } : null,
      streakDays: (ui.stats && ui.stats.streakDays) || 0,
    };
  }

  function paintCourse() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(sessionData(), timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startLesson);
    view.querySelector('[data-action="review"]').addEventListener("click", startReviewSession);
    const cur = view.querySelector('[data-action="curriculum"]');
    if (cur) cur.addEventListener("click", showCurriculum);
    const lib = view.querySelector('[data-action="library"]');
    if (lib) lib.addEventListener("click", showLibrary);
    const ref = view.querySelector('[data-action="refine"]');
    if (ref) ref.addEventListener("click", startRefine);
  }

  // ---- refine course flow ----
  function startRefine() {
    pauseTimer();
    ui.screen = "refine";
    ui.refine = ui.refine && ui.refine.messages ? ui.refine : { messages: [] };
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintRefine();
  }

  function paintRefine() {
    const view = root.querySelector("#view");
    const msgs = ui.refine.messages;
    view.innerHTML = chatHTML(msgs, {
      pending: false,
      placeholder: "e.g. add a module on transformers, drop the intro lesson, go deeper in module 2",
    });

    // Replace the greeting with a refine-specific lead-in card
    const greeting = view.querySelector(".greeting");
    if (greeting) {
      greeting.innerHTML =
        `<h1>Refine this course</h1>` +
        `<span>Describe what you&rsquo;d like to change in <strong>${esc(ui.manifest.title)}</strong></span>`;
    }

    // Append the action card with the "Propose changes" button
    const thread = view.querySelector(".chat-thread");
    if (thread) {
      const card = doc.createElement("div");
      card.className = "card proposal";
      const empty = msgs.length === 0;
      card.innerHTML =
        `<button class="btn-primary" data-action="propose-revision"${empty ? " disabled" : ""}>Propose changes</button>`;
      thread.appendChild(card);
      card.querySelector('[data-action="propose-revision"]').addEventListener("click", proposeRevision);
    }

    const send = view.querySelector('[data-action="send"]');
    if (send) send.addEventListener("click", sendRefine);
  }

  function sendRefine() {
    const ta = root.querySelector('[data-field="chat"]');
    if (!ta) return;
    const text = ta.value.trim();
    if (!text) return;
    ui.refine.messages.push({ role: "user", content: text });
    paintRefine();
  }

  async function proposeRevision() {
    ui.screen = "revising";
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", startRefine);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", PROGRAM_STAGES);
    const result = await reviseCourse({ fetch, courseId: ui.courseId, messages: ui.refine.messages });
    if (ui.screen !== "revising") return;
    if (!result || result.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((result && result.error) || "Couldn't propose changes right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", startRefine);
      return;
    }
    showRevision(result);
  }

  function showRevision(result) {
    ui.screen = "revision";
    ui.proposedRevision = result;
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", startRefine);
    const view = root.querySelector("#view");
    view.innerHTML = revisionHTML(result);
    view.querySelector('[data-action="apply-revision"]').addEventListener("click", applyRevisionNow);
    view.querySelector('[data-action="keep-discussing"]').addEventListener("click", startRefine);
  }

  async function applyRevisionNow() {
    const course = await applyRevision({ fetch, courseId: ui.courseId, course: ui.proposedRevision.course });
    if (ui.screen !== "revision") return;  // user navigated away mid-apply — don't paint over their new screen
    if (!course || course.error) {
      showRevision(ui.proposedRevision);
      return;
    }
    log("course_revised", { courseId: ui.courseId });
    openCourse(ui.courseId);
  }

  // #accredited-sources — the course Library: real, web-retrieved accredited sources.
  // Generated on first open (a web-search pass, ~50-60s), cached after.
  async function showLibrary() {
    pauseTimer();
    ui.screen = "library";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    const view = root.querySelector("#view");
    startLoading(view, "capstone", ["Searching for grounded sources…", "Checking universities & journals…", "Compiling the reading list…", "Almost ready…"]);
    log("library_opened", { courseId: ui.courseId });
    const library = await loadLibrary({ fetch, courseId: ui.courseId });
    if (ui.screen !== "library") return;
    if (!library || library.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((library && library.error) || "Couldn't load this right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
      return;
    }
    view.innerHTML = libraryHTML(library);
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
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
    view.innerHTML = curriculumHTML(ui.manifest, (ui.manifest && ui.manifest.mastery) || {}, currentLessonId(), ui.manifest && ui.manifest.exams, !!(ui.manifest && ui.manifest.coursePassed));
    view.querySelectorAll("[data-lesson]").forEach((row) => {
      row.addEventListener("click", () => openLesson(row.getAttribute("data-lesson")));
    });
    view.querySelectorAll("[data-capstone]").forEach((b) => {
      b.addEventListener("click", () => showCapstone(b.getAttribute("data-capstone")));
    });
    view.querySelectorAll("[data-exam]").forEach((b) => {
      b.addEventListener("click", () => showExam(b.getAttribute("data-exam")));
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
    ui.capState = { scope, cap, work: "", busy: false, result: null };
    paintCapstone();
  }

  function paintCapstone() {
    const st = ui.capState;
    const view = root.querySelector("#view");
    view.innerHTML = capstoneHTML(st.cap, st);
    view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
    // The textarea updates state without a repaint (a repaint would steal focus
    // on every keystroke); only the submit button's disabled state refreshes.
    const ta = view.querySelector('[data-field="cap-work"]');
    if (ta) ta.addEventListener("input", () => {
      st.work = ta.value;
      const btn = view.querySelector('[data-action="cap-submit"]');
      if (btn) btn.disabled = !ta.value.trim() || st.busy;
    });
    const submit = view.querySelector('[data-action="cap-submit"]');
    if (submit) submit.addEventListener("click", submitCapstoneWork);
  }

  // The server records capstone_result itself — the client logs no event here.
  async function submitCapstoneWork() {
    const st = ui.capState;
    if (!st || st.busy || !(st.work || "").trim()) return;
    st.busy = true;
    paintCapstone();
    const result = await submitCapstone({ fetch, courseId: ui.courseId, scope: st.scope, work: st.work.trim() });
    if (ui.screen !== "capstone" || ui.capState !== st) return; // navigated away mid-grade
    st.busy = false;
    st.result = result || { error: "Couldn't grade your capstone right now." };
    paintCapstone();
  }

  // ---- summative exams (sub-project C) ----
  function examLabel(examKey) {
    if (examKey === "final") return `Final exam — ${(ui.manifest && ui.manifest.title) || ""}`;
    const mod = ((ui.manifest && ui.manifest.modules) || []).find((m) => m.id === examKey);
    return mod ? `Module exam — ${mod.title}` : "Exam";
  }

  async function showExam(examKey) {
    pauseTimer();
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "exam-loading";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCurriculum);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", EXAM_STAGES);
    // A just-completed gap review's markers may still be sitting in the buffer —
    // flush them before the retake gate re-checks the DB, or a freshly unlocked
    // retake 409s in the common case (see doFlush interval above).
    await doFlush();
    if (ui.screen !== "exam-loading" || ui.loadSeq !== seq) return; // navigated away during flush
    const exam = await startExam({ fetch, courseId: ui.courseId, examKey });
    if (ui.screen !== "exam-loading" || ui.loadSeq !== seq) return; // navigated away mid-load
    if (!exam || exam.error) {
      const fixGaps = exam && exam.code === "gap-review";
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((exam && exam.error) || "Couldn't prepare the exam right now.")}</div>` +
        `<div class="nav">${fixGaps ? '<button class="btn-primary" data-action="fix-gaps">Fix the gaps</button>' : ""}` +
        `<button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
      if (fixGaps) {
        view.querySelector('[data-action="fix-gaps"]').addEventListener("click", () => showRemediation(examKey));
      }
      return;
    }
    ui.screen = "exam";
    ui.examState = { examKey, exam, answers: {}, submitting: false, error: "" };
    paintExam();
  }

  function paintExam() {
    const st = ui.examState;
    const view = root.querySelector("#view");
    view.innerHTML = examHTML({ ...st.exam, title: examLabel(st.examKey) }, st);
    view.querySelectorAll("[data-choice]").forEach((b) => {
      b.addEventListener("click", () => {
        st.answers[Number(b.getAttribute("data-q"))] = Number(b.getAttribute("data-choice"));
        paintExam();
      });
    });
    // Textareas update state without a repaint (a repaint would steal focus on
    // every keystroke); only the submit button's disabled state is refreshed.
    view.querySelectorAll("textarea[data-q]").forEach((t) => {
      t.addEventListener("input", () => {
        st.answers[Number(t.getAttribute("data-q"))] = t.value;
        const btn = view.querySelector('[data-action="submit-exam"]');
        if (btn) btn.disabled = !(examReady(st.exam, st.answers) && !st.submitting);
      });
    });
    const submit = view.querySelector('[data-action="submit-exam"]');
    if (submit) submit.addEventListener("click", submitCurrentExam);
  }

  async function submitCurrentExam() {
    const st = ui.examState;
    if (!st || st.submitting || !examReady(st.exam, st.answers)) return;
    st.submitting = true;
    st.error = "";
    paintExam();
    const answers = st.exam.questions.map((q, i) => (q.type === "mcq" ? st.answers[i] : st.answers[i] || ""));
    const result = await submitExam({ fetch, courseId: ui.courseId, examKey: st.examKey, answers });
    if (ui.screen !== "exam" || ui.examState !== st) return; // navigated away mid-grade
    st.submitting = false;
    if (!result || result.error) {
      st.error = (result && result.error) || "Couldn't grade the exam right now — your answers are still here, try again.";
      paintExam();
      return;
    }
    // Paint the result even if the summary refresh fails — this screen is the
    // only place the graded report exists; stale status self-heals on next load.
    try { await refreshSummary(); } catch (e) {}
    if (ui.screen !== "exam" || ui.examState !== st) return; // navigated away during refresh
    ui.screen = "exam-result";
    const view = root.querySelector("#view");
    view.innerHTML = examResultHTML(result);
    view.querySelectorAll("[data-lesson]").forEach((b) => {
      b.addEventListener("click", () => openLesson(b.getAttribute("data-lesson")));
    });
    const rt = view.querySelector('[data-action="retake-exam"]');
    if (rt) rt.addEventListener("click", () => showExam(st.examKey));
    const fix = view.querySelector('[data-action="fix-gaps"]');
    if (fix) fix.addEventListener("click", () => showRemediation(st.examKey));
    view.querySelector('[data-action="back-curriculum"]').addEventListener("click", showCurriculum);
  }

  // ---- gap review (sub-project D): Bloom's corrective loop after a failed exam ----
  async function showRemediation(examKey) {
    pauseTimer();
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "remediation-loading";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCurriculum);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", REMEDIATION_STAGES);
    const session = await startRemediation({ fetch, courseId: ui.courseId, examKey });
    if (ui.screen !== "remediation-loading" || ui.loadSeq !== seq) return; // navigated away
    if (!session || session.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((session && session.error) || "Couldn't prepare the gap review right now.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showCurriculum);
      return;
    }
    ui.screen = "remediation";
    ui.remState = { examKey, session, items: flatPractice(session), answers: {}, results: {},
                    applyAnswers: {}, applyResults: {}, applyBusy: {} };
    log("remediation_started", { courseId: ui.courseId, topicId: examKey });
    paintRemediation();
  }

  function paintRemediation() {
    const st = ui.remState;
    const view = root.querySelector("#view");
    view.innerHTML = remediationHTML(st.session, st, ui.manifest);
    view.querySelectorAll("[data-rq-choice]").forEach((b) => {
      b.addEventListener("click", () =>
        answerPractice(Number(b.getAttribute("data-rq")), Number(b.getAttribute("data-rq-choice"))));
    });
    view.querySelectorAll('[data-action="rq-fill"]').forEach((b) => {
      b.addEventListener("click", () => {
        const k = Number(b.getAttribute("data-rq"));
        const inp = view.querySelector(`[data-rq-input="${k}"]`);
        answerPractice(k, inp ? inp.value : "");
      });
    });
    // Apply-it textareas update state without a repaint (a repaint would steal
    // focus on every keystroke); only their button's disabled state refreshes.
    view.querySelectorAll("textarea[data-rem-apply]").forEach((t) => {
      t.addEventListener("input", () => {
        const gi = Number(t.getAttribute("data-rem-apply"));
        st.applyAnswers[gi] = t.value;
        const btn = view.querySelector(`[data-action="rem-apply"][data-gap="${gi}"]`);
        if (btn) btn.disabled = !t.value.trim() || !!st.applyBusy[gi];
      });
    });
    view.querySelectorAll('[data-action="rem-apply"]').forEach((b) => {
      b.addEventListener("click", () => submitApply(Number(b.getAttribute("data-gap"))));
    });
    // Builds-on chips: trace the weakness to its upstream lesson (Item D).
    view.querySelectorAll("[data-lesson]").forEach((b) => {
      b.addEventListener("click", () => openLesson(b.getAttribute("data-lesson")));
    });
    view.querySelector('[data-action="retake-exam"]').addEventListener("click", () => showExam(st.examKey));
    view.querySelector('[data-action="back-curriculum"]').addEventListener("click", showCurriculum);
  }

  async function submitApply(gi) {
    const st = ui.remState;
    if (!st) return;
    const answer = (st.applyAnswers[gi] || "").trim();
    const prior = st.applyResults[gi];
    if (!answer || st.applyBusy[gi] || (prior && prior.verdict)) return; // one submission per gap
    st.applyBusy[gi] = true;
    paintRemediation();
    const result = await gradeRemediationApply({
      fetch, courseId: ui.courseId, examKey: st.examKey, gapIndex: gi, answer,
    });
    if (ui.screen !== "remediation" || ui.remState !== st) return; // navigated away mid-grade
    st.applyBusy[gi] = false;
    st.applyResults[gi] = result || { error: "Couldn't grade this answer right now." };
    if (result && result.verdict) {
      const gap = st.session.gaps[gi] || {};
      // Apply verdicts feed mastery through the lesson_explained pool; the
      // examKey/attempt/index markers are what the backend retake gate counts.
      log("lesson_explained", {
        courseId: ui.courseId, topicId: gap.lessonId,
        payload: { verdict: result.verdict, source: "remediation",
                   examKey: st.examKey, attempt: st.session.attempt, index: gi },
      });
    }
    paintRemediation();
  }

  function answerPractice(k, answer) {
    const st = ui.remState;
    if (!st || st.results[k]) return; // already answered
    const item = st.items[k];
    if (!item) return;
    const result = gradeCheck(item.check, answer);
    st.answers[k] = answer;
    st.results[k] = result;
    // Practice evidence feeds mastery through the same lesson_check pool as lesson
    // checks; the source tag keeps the provenance readable in the event log.
    log("lesson_check", {
      courseId: ui.courseId, topicId: item.lessonId,
      payload: { index: k, type: item.check.type, correct: result.correct, source: "remediation",
                 examKey: st.examKey, attempt: st.session.attempt },
    });
    paintRemediation();
  }

  // ---- transcript (sub-project D): the global academic record ----
  async function showTranscript() {
    pauseTimer();
    ui.screen = "transcript";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Assembling your record…</div></div>`;
    const data = await loadTranscript({ fetch });
    if (ui.screen !== "transcript") return; // navigated away mid-load
    view.innerHTML = transcriptHTML(data || { courses: [] });
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
  async function openLesson(lessonId, opts = {}) {
    // Note: opts.review is currently dead; review entry points (startReviewSession,
    // advanceAfterLesson) set isReview on their own state literals because openLesson
    // resets reviewQueue and lessonState from scratch.
    if (!lessonId) return;
    ui.reviewQueue = [];
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "lesson-loading";
    const view = root.querySelector("#view");
    if (view) startLoading(view, "lesson", LESSON_STAGES);
    // Prior-knowledge activation: a not-yet-generated lesson gets one free-text
    // question before the slow generation call; an already-generated lesson (or a
    // failed/errored status check) opens exactly as before — the feature only adds.
    if (!opts.review) {
      const status = await getLessonStatus({ fetch, courseId: ui.courseId, lessonId });
      if (ui.screen !== "lesson-loading" || ui.loadSeq !== seq) return; // navigated away mid-check
      if (!status.error && status.generated === false) {
        ui.screen = "activate";
        paintActivate(lessonId, opts, seq);
        return;
      }
    }
    await finishOpenLesson(lessonId, opts, seq);
  }

  // The prior-knowledge question card. Both buttons funnel into the same
  // "continue" path, which re-arms the loading skeleton and hands off to
  // finishOpenLesson — the exact tail a cache hit already takes.
  function paintActivate(lessonId, opts, seq) {
    const view = root.querySelector("#view");
    if (!view) return;
    const found = flatLessons().find((l) => l.id === lessonId);
    const title = found ? found.title : lessonId;
    view.innerHTML = activateHTML(title);
    let text = "";
    let busy = false; // Busy flag to guard against double-click (card is single-use, never cleared).
    // The textarea updates local state without a repaint — a repaint would steal
    // focus on every keystroke (same idiom as the capstone workspace textarea).
    const ta = view.querySelector('[data-field="pk-text"]');
    if (ta) ta.addEventListener("input", () => { text = ta.value; });
    const continueToLesson = async () => {
      ui.screen = "lesson-loading";
      const v = root.querySelector("#view");
      if (v) startLoading(v, "lesson", LESSON_STAGES);
      await finishOpenLesson(lessonId, opts, seq);
    };
    const startBtn = view.querySelector('[data-action="pk-start"]');
    const skipBtn = view.querySelector('[data-action="pk-skip"]');
    if (startBtn) startBtn.addEventListener("click", async () => {
      if (busy) return;
      busy = true;
      startBtn.disabled = true;
      if (skipBtn) skipBtn.disabled = true;
      const trimmed = text.trim();
      if (trimmed) {
        log("prior_knowledge", { courseId: ui.courseId, topicId: lessonId, payload: { text: trimmed } });
        await doFlush(); // the event must be in the DB before the lesson GET reads it
      }
      if (ui.screen !== "activate" || ui.loadSeq !== seq) return; // navigated away mid-flush
      await continueToLesson();
    });
    if (skipBtn) skipBtn.addEventListener("click", () => {
      if (busy) return;
      busy = true;
      startBtn.disabled = true;
      if (skipBtn) skipBtn.disabled = true;
      continueToLesson();
    });
  }

  // Shared tail: load the (now-cached, or freshly generated) lesson and show it.
  // Used both when the status check says "already generated" and by the activate
  // card's two buttons. Identical body to the pre-refactor openLesson tail.
  async function finishOpenLesson(lessonId, opts, seq) {
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId });
    if (ui.screen !== "lesson-loading" || ui.loadSeq !== seq) return; // navigated away mid-load
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showLessonError(ui.lesson && ui.lesson.error || "Couldn't load this lesson."); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, isReview: !!opts.review };
    const completed = !!(ui.manifest && ui.manifest.mastery && ui.manifest.mastery[lessonId]);
    ui.lessonState.stage = ui.lesson.preQuiz && !completed ? "prequiz" : "main";
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
      // Break the shared ws reference and clear any stuck pending, so a chat that was
      // mid-stream when deepen failed doesn't leave the input disabled.
      const keptWs = ui.lessonState.ws ? { ...ui.lessonState.ws, pending: false, grading: false } : undefined;
      ui.lessonState = { ...ui.lessonState, ws: keptWs, deepenError: (deeper && deeper.error) || "Couldn't rewrite this lesson right now." };
      showLesson();
      return;
    }
    ui.lesson = deeper;
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, isReview: ui.lessonState.isReview, stage: "main" };
    log("lesson_view", { courseId: ui.courseId, topicId: lessonId });
    showLesson();
  }

  function showLesson() {
    ui.screen = "lesson";
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintLesson();
    seedWorkspace(ui.lesson, ui.lessonState);
  }

  // ---- lesson workspace (notes + side-chat) ----
  const WS_PREFS = "ws-prefs"; // remembers open/closed + active tab across lessons
  // Client-side canned opener for socratic co-work: instant, zero cost.
  const SOCRATIC_OPENER = "Let's work through this together — I'll ask questions, you do the thinking. What do you think the first step is?";
  // Client-side canned opener for Teach it to Claude: instant, zero cost.
  const TEACH_OPENER = "Okay — teach me! Explain this lesson's idea like I've never seen it before, and I'll ask questions as we go.";
  function wsPrefs() {
    // Default: open on wide screens (the notes sit beside the lesson), collapsed on
    // phone. Once the learner toggles it, their saved choice is respected everywhere.
    try { const p = JSON.parse(storage.getItem(WS_PREFS)); if (p) return p; } catch (e) {}
    return { open: window.innerWidth >= 1200, tab: "notes" };
  }
  function setWsPrefs(patch) {
    try { storage.setItem(WS_PREFS, JSON.stringify({ ...wsPrefs(), ...patch })); } catch (e) {}
  }
  async function seedWorkspace(lesson, lessonState) {
    if (!lesson || lessonState.ws) return; // already seeded for this state
    const prefs = wsPrefs();
    const wsData = await loadWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: lesson.id });
    if (ui.lessonState !== lessonState) return; // navigated away while loading
    lessonState.ws = { open: !!prefs.open, tab: prefs.tab || "notes",
                       notes: wsData.notes || "", chat: wsData.chat || [], pending: false, saveStatus: "" };
    if (ui.screen === "lesson") paintLesson();
  }
  let wsSaveTimer = null;
  function scheduleNotesSave() {
    if (wsSaveTimer) window.clearTimeout(wsSaveTimer);
    ui.lessonState.ws.saveStatus = "saving";
    wsSaveTimer = window.setTimeout(saveWsNow, 1000);
  }
  async function saveWsNow() {
    const ls = ui.lessonState, ws = ls.ws;
    if (!ws) return;
    const res = await saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
    if (ui.lessonState !== ls) return;
    ws.saveStatus = res.ok ? "saved" : "offline";
    const el = root.querySelector(".ws-status");
    if (el) el.textContent = { saving: "saving…", saved: "saved", offline: "offline" }[ws.saveStatus] || "";
  }
  // Shared transport tail for the workspace chat: sets pending, paints once, streams
  // the reply, and persists — used by both the typed textarea path (sendWsChat) and
  // the concept-chip path (startAnalogyChip) so pending/paint/persist/error handling
  // has exactly one implementation. Callers push the learner-visible message onto
  // ws.chat and capture ls/ws/cid/lid BEFORE calling this, so the onScreen staleness
  // check and the eventual save always target the right lesson.
  async function streamWsReply(ls, ws, cid, lid, extra) {
    ws.pending = true;
    const reply = { role: "assistant", content: "" };
    const onScreen = () => ui.lessonState === ls && ui.screen === "lesson";
    paintLesson();
    await streamChat({
      fetch,
      endpoint: `/api/courses/${cid}/lessons/${lid}/chat`,
      messages: ws.chat.map((m) => ({ role: m.role, content: m.content })),
      extra,
      onDelta: (d) => {
        reply.content += d;
        if (!onScreen()) return;
        const thread = root.querySelector(".ws-thread");
        if (thread) {
          const typing = thread.querySelector(".ws-typing");
          if (typing) typing.remove();          // the reply has started; drop the "…" bubble
          let live = thread.querySelector(".ws-live");
          if (!live) { live = doc.createElement("div"); live.className = "ws-msg ws-ai ws-live"; thread.appendChild(live); }
          live.textContent = reply.content;
          thread.scrollTop = thread.scrollHeight;  // follow the streaming reply
        }
      },
      onDone: () => {
        ws.pending = false;                 // always clear pending so the input re-enables
        if (reply.content.trim()) ws.chat.push(reply);
        saveWorkspace({ fetch, storage, courseId: cid, lessonId: lid, notes: ws.notes, chat: ws.chat });
        if (onScreen()) paintLesson();
      },
      onError: (e) => {
        ws.pending = false;
        ws.chat.push({ role: "assistant", content: "⚠️ " + ((e && e.message) || "Claude is unavailable right now.") });
        if (onScreen()) paintLesson();
      },
    });
  }

  async function sendWsChat() {
    const ls = ui.lessonState, ws = ls.ws;
    // Capture the target lesson so the transcript is always persisted to the RIGHT
    // file even if the learner navigates away before the reply finishes.
    const cid = ui.courseId, lid = ui.lesson.id;
    const ta = root.querySelector('[data-field="ws-chat"]');
    const text = ta ? ta.value.trim() : "";
    if (!text || ws.pending || ws.grading) return;
    ws.chat.push({ role: "user", content: text });
    await streamWsReply(ls, ws, cid, lid,
      { solutionRevealed: !!ui.lessonState.solutionRevealed,
        ...(ws.teaching ? { mode: "teach" } : ws.socratic ? { mode: "socratic" } : {}) });
  }

  // #6 analogy on tap: tapping a concept chip sends the canned learner message with
  // mode: "analogy" + the tapped term for a one-off alternative-angle explanation.
  // ws.socratic is untouched — an active socratic session's banner and next typed
  // message are unaffected by this one-off override.
  function startAnalogyChip(index) {
    const ls = ui.lessonState, ws = ls.ws;
    const term = ui.lesson && ui.lesson.concepts && ui.lesson.concepts[index];
    if (!ws || ws.pending || typeof term !== "string") return;
    // Capture the target lesson so the transcript is always persisted to the RIGHT
    // file even if the learner navigates away before the reply finishes.
    const cid = ui.courseId, lid = ui.lesson.id;
    ws.open = true;
    ws.tab = "chat";
    ws.chat.push({ role: "user", content: `Give me a different way to think about "${term}".` });
    streamWsReply(ls, ws, cid, lid,
      { solutionRevealed: !!ui.lessonState.solutionRevealed, mode: "analogy", concept: term });
  }

  // Teach it to Claude (protégé effect): one grading call per "Grade my teaching" click,
  // scored with the same verdict machinery as explain-it-back. Capture-before-await +
  // onScreen staleness mirrors the explain-grade handler — but per the design doc the
  // mastery event is logged unconditionally (the learner earned it even if they have
  // since navigated away); only the repaint is guarded.
  async function submitTeachGrade() {
    const ls = ui.lessonState, ws = ls.ws;
    if (!ws || !ws.teaching || ws.pending || ws.grading) return;
    const cid = ui.courseId, lid = ui.lesson.id;
    const episode = ws.chat.slice(ws.teachStart || 0);
    if (!episode.some((m) => m.role === "user" && (m.content || "").trim())) return;
    ws.grading = true;
    paintLesson();
    const onScreen = () => ui.lessonState === ls && ui.screen === "lesson";
    const messages = episode.map((m) => ({ role: m.role, content: m.content }));
    const result = await gradeTeaching({ fetch, courseId: cid, lessonId: lid, messages });
    ws.grading = false;
    if (result && result.verdict) {
      ws.teachGrade = { verdict: result.verdict, note: result.note };
      ws.teaching = false;
      log("lesson_explained", { courseId: cid, topicId: lid, payload: { verdict: result.verdict, source: "teaching" } });
    } else {
      ws.teachGrade = { error: (result && result.error) || "Couldn't grade your teaching right now." };
    }
    if (onScreen()) paintLesson();
  }

  function paintLesson() {
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    const curBtn = view.querySelector('[data-action="curriculum"]');
    if (curBtn) curBtn.addEventListener("click", showCurriculum);
    const prevBtn = view.querySelector('[data-action="prev-lesson"]');
    if (prevBtn) prevBtn.addEventListener("click", () => { const a = adjacentLesson(-1); if (a) openLesson(a.id); });
    const nextBtn = view.querySelector('[data-action="next-lesson"]');
    if (nextBtn) nextBtn.addEventListener("click", () => { const a = adjacentLesson(1); if (a) openLesson(a.id); });
    if (ui.lessonState.stage === "prequiz") { bindPreQuiz(view); return; }
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
      if (ui.lessonState.ws) ui.lessonState.ws.socratic = false; // mode ends on reveal
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
    const exTa = view.querySelector('[data-field="explain"]');
    if (exTa) exTa.addEventListener("input", () => {
      ui.lessonState.explain = ui.lessonState.explain || {};
      ui.lessonState.explain.text = exTa.value;
      const b = view.querySelector('[data-action="explain-grade"]');
      if (b) b.disabled = !exTa.value.trim() || !!ui.lessonState.explain.grading;
    });
    const exBtn = view.querySelector('[data-action="explain-grade"]');
    if (exBtn) exBtn.addEventListener("click", async () => {
      const ex = ui.lessonState.explain || {};
      const text = (ex.text || "").trim();
      if (!text || ex.grading) return;
      ui.lessonState.explain = { ...ex, grading: true };
      paintLesson();
      const lessonState = ui.lessonState;
      const grade = await explainAnswer({ fetch, courseId: ui.courseId, lessonId: ui.lesson.id, explanation: text });
      if (ui.lessonState !== lessonState || ui.screen !== "lesson") return;
      // A fresh grading brings a fresh followUp — re-arm the seed button.
      lessonState.explain = { ...lessonState.explain, grading: false, grade, seeded: false };
      if (grade && !grade.error) {
        log("lesson_explained", { courseId: ui.courseId, topicId: ui.lesson.id, payload: { verdict: grade.verdict } });
      }
      paintLesson();
    });
    const exChat = view.querySelector('[data-action="explain-chat"]');
    if (exChat) exChat.addEventListener("click", () => {
      const ex = ui.lessonState.explain || {};
      const g = ex.grade;
      const ws = ui.lessonState.ws;
      if (!g || g.error || !g.followUp || ex.seeded || !ws) return;
      ex.seeded = true;
      ws.open = true;
      ws.tab = "chat";
      ws.chat.push({ role: "assistant", content: g.followUp });
      saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
      paintLesson();
    });
    const socBtn = view.querySelector('[data-action="socratic-start"]');
    if (socBtn) socBtn.addEventListener("click", () => {
      const ws = ui.lessonState.ws;
      if (!ws) return; // workspace still seeding; the button works once it has painted
      const entering = !ws.socratic;
      ws.socratic = true;
      ws.open = true;
      ws.tab = "chat";
      if (entering) {
        ws.chat.push({ role: "assistant", content: SOCRATIC_OPENER });
        // Best-effort persist — same fire-and-forget idiom as the explain-chat seeding.
        saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
      }
      paintLesson();
    });
    const teachBtn = view.querySelector('[data-action="teach-start"]');
    if (teachBtn) teachBtn.addEventListener("click", () => {
      const ws = ui.lessonState.ws;
      if (!ws) return; // workspace still seeding; the button works once it has painted
      const entering = !ws.teaching;
      ws.teaching = true;
      ws.open = true;
      ws.tab = "chat";
      if (entering) {
        ws.teachStart = ws.chat.length;
        ws.teachGrade = null;
        ws.chat.push({ role: "assistant", content: TEACH_OPENER });
        // Best-effort persist — same fire-and-forget idiom as the socratic entry above.
        saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat });
      }
      paintLesson();
    });
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
    view.querySelectorAll('[data-quality]').forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (ui.lessonState.rated) return;
        if (ratingLocked(ui.lesson, ui.lessonState)) return;
        ui.lessonState.rated = true;
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
    view.querySelectorAll('[data-action="analogy-chip"]').forEach((btn) => {
      btn.addEventListener("click", () => startAnalogyChip(Number(btn.getAttribute("data-index"))));
    });
    bindWorkspace(view);
  }

  function answerPreQuiz(answer) {
    if (ui.lessonState.preQuiz && ui.lessonState.preQuiz.result) return; // already attempted
    const result = gradeCheck(ui.lesson.preQuiz, answer);
    ui.lessonState.preQuiz = { answer, result };
    log("prequiz_attempt", {
      courseId: ui.courseId, topicId: ui.lesson.id,
      payload: { correct: result.correct, type: ui.lesson.preQuiz.type },
    });
    paintLesson();
  }

  function bindPreQuiz(view) {
    view.querySelectorAll("[data-pq-choice]").forEach((btn) => {
      btn.addEventListener("click", () => answerPreQuiz(Number(btn.getAttribute("data-pq-choice"))));
    });
    const submit = view.querySelector('[data-action="pq-submit"]');
    if (submit) submit.addEventListener("click", () => {
      const inp = view.querySelector("[data-pq-input]");
      const val = inp ? inp.value.trim() : "";
      if (!val) return;
      answerPreQuiz(val);
    });
    const cont = view.querySelector('[data-action="pq-continue"]');
    if (cont) cont.addEventListener("click", () => { ui.lessonState.stage = "main"; paintLesson(); });
  }

  // The chat thread is a fixed-height scroll area that rebuilds on every repaint, so it
  // resets to the top (oldest messages) each time. Pin it to the bottom so the latest
  // message is always in view without manual scrolling.
  function scrollWsThread() {
    const thread = root.querySelector(".ws-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function bindWorkspace(view) {
    if (!ui.lessonState.ws) return;
    const toggle = view.querySelector('[data-action="ws-toggle"]');
    if (toggle) toggle.addEventListener("click", () => {
      ui.lessonState.ws.open = !ui.lessonState.ws.open;
      setWsPrefs({ open: ui.lessonState.ws.open });
      paintLesson();
    });
    view.querySelectorAll('[data-action="ws-tab"]').forEach((b) => b.addEventListener("click", () => {
      ui.lessonState.ws.tab = b.getAttribute("data-tab");
      setWsPrefs({ tab: ui.lessonState.ws.tab });
      paintLesson();
    }));
    const wsNotes = view.querySelector('[data-field="ws-notes"]');
    if (wsNotes) wsNotes.addEventListener("input", () => {
      ui.lessonState.ws.notes = wsNotes.value;
      scheduleNotesSave();
      const el = root.querySelector(".ws-status");
      if (el) el.textContent = "saving…";
    });
    const wsSend = view.querySelector('[data-action="ws-send"]');
    if (wsSend) wsSend.addEventListener("click", sendWsChat);
    const socExit = view.querySelector('[data-action="socratic-exit"]');
    if (socExit) socExit.addEventListener("click", () => {
      ui.lessonState.ws.socratic = false;
      paintLesson();
    });
    const teachExit = view.querySelector('[data-action="teach-exit"]');
    if (teachExit) teachExit.addEventListener("click", () => {
      ui.lessonState.ws.teaching = false;
      paintLesson();
    });
    const teachGradeBtn = view.querySelector('[data-action="teach-grade"]');
    if (teachGradeBtn) teachGradeBtn.addEventListener("click", submitTeachGrade);
    scrollWsThread();  // open/repaint with the newest message in view
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
      payload: {
        index: i, type: check.type, correct: result.correct,
        ...(ui.lessonState.freshItems ? { source: "review" } : {}),
      },
    });
    paintLesson();
  }

  // Fires the fresh-retrieval-items generation for a review lesson right after its
  // lessonState is created. Sets freshPending synchronously — before the caller's first
  // paint — so the placeholder shows immediately. On resolve, adopts the items onto the
  // CAPTURED lesson/lessonState only if the learner is still on that same lessonState
  // (capture-then-guard, per sendWsChat's onScreen idiom) and hasn't already answered
  // with the original checks. Every outcome clears freshPending; repaint only happens
  // while still on the lesson screen for this same lessonState.
  function fetchFreshItems(ls, lesson) {
    ls.freshPending = true;
    loadReviewItems({ fetch, courseId: ui.courseId, lessonId: lesson.id }).then((res) => {
      if (ui.lessonState === ls && !res.error && Array.isArray(res.items) && res.items.length
          && Object.keys(ls.checkResults).length === 0) {
        lesson.checks = res.items;
        ls.freshItems = true;
      }
      ls.freshPending = false;
      if (ui.lessonState === ls && ui.screen === "lesson") paintLesson();
    }).catch(() => {
      // No adoption here (nothing to adopt from a rejection) — original checks stand.
      // Same tail as the .then above: always clear freshPending, repaint only if still here.
      ls.freshPending = false;
      if (ui.lessonState === ls && ui.screen === "lesson") paintLesson();
    });
  }

  async function advanceAfterLesson() {
    if (ui.reviewQueue.length) {
      const nextId = ui.reviewQueue.shift();
      const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: nextId });
      if (ui.screen !== "lesson") return; // navigated away while loading the next review
      ui.lesson = lesson;
      if (lessonFailed(ui.lesson)) { await refreshSummary(); if (ui.screen !== "lesson") return; showCourse(); return; }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
      fetchFreshItems(ui.lessonState, ui.lesson);
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    if (ui.screen !== "lesson") return; // navigated away — don't yank them to the dashboard
    showCourse();
  }

  async function startReviewSession() {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "review-loading";
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { showCourse(); return; }
    ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
    fetchFreshItems(ui.lessonState, ui.lesson);
    log("lesson_view", { courseId: ui.courseId, topicId: due[0] });
    if (!ui.timer.running) startTimer();
    showLesson();
  }

  // ---- course creation chat ----
  function showChat() {
    pauseTimer();
    ui.screen = "chat";
    ui.chat = { messages: [], brief: null, pending: false };
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    paintChat();
  }

  function paintChat() {
    const view = root.querySelector("#view");
    view.innerHTML = chatHTML(ui.chat.messages, { pending: ui.chat.pending });
    if (ui.chat.brief) {
      const card = doc.createElement("div");
      card.className = "card proposal";
      card.innerHTML =
        `<div class="eyebrow">READY TO BUILD</div>` +
        `<h2 class="session-topic">Your learning brief is ready</h2>` +
        `<div class="session-sub">${esc(ui.chat.brief.goal || "")}</div>` +
        `<button class="btn-primary" data-action="build-program">Build my program</button>`;
      view.querySelector(".chat-thread").appendChild(card);
      card.querySelector('[data-action="build-program"]').addEventListener("click", buildProgram);
    }
    const send = view.querySelector('[data-action="send"]');
    if (send) send.addEventListener("click", sendChat);
  }

  async function sendChat() {
    const ta = root.querySelector('[data-field="chat"]');
    const text = ta.value.trim();
    if (!text || ui.chat.pending) return;
    const chat = ui.chat;
    const onScreen = () => ui.screen === "chat" && ui.chat === chat;
    chat.messages.push({ role: "user", content: text });       // raw
    const reply = { role: "assistant", content: "" };
    chat.messages.push(reply);
    chat.pending = true;
    paintChat();
    const history = chat.messages
      .filter((m) => m !== reply)                                  // exclude the in-progress placeholder
      .map((m) => ({ role: m.role, content: m.content }));
    await streamChat({
      fetch,
      messages: history,
      onDelta: (d) => { reply.content += d; if (onScreen()) paintChat(); },
      onBrief: (b) => { chat.brief = b; },
      onDone: () => { chat.pending = false; if (onScreen()) paintChat(); },
      onError: (e) => { reply.content = "⚠️ " + (e.message || "Claude is unavailable right now."); chat.pending = false; if (onScreen()) paintChat(); },
    });
  }

  async function buildProgram() {
    pauseTimer();
    ui.screen = "compiling";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showChat);
    const view = root.querySelector("#view");
    startLoading(view, "lesson", PROGRAM_STAGES);
    const course = await compileProgram({ fetch, learnerBrief: ui.chat.brief });
    if (ui.screen !== "compiling") return;
    if (!course || course.error) {
      view.innerHTML =
        `<div class="card"><div class="prompt">${esc((course && course.error) || "Couldn't build your program.")}</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", showChat);
      return;
    }
    showSyllabus(course);
  }

  function showSyllabus(course) {
    pauseTimer();
    ui.screen = "syllabus";
    ui.proposedCourse = course;
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showChat);
    const view = root.querySelector("#view");
    view.innerHTML = syllabusHTML(course);
    view.querySelector('[data-action="accept-syllabus"]').addEventListener("click", acceptSyllabus);
    view.querySelector('[data-action="revise-syllabus"]').addEventListener("click", showChat);
  }

  async function acceptSyllabus() {
    if (ui.creatingCourse) return;
    ui.creatingCourse = true;
    const proposed = ui.proposedCourse;
    let course = null;
    try {
      course = await createCourse({ fetch, proposal: proposed });
    } catch (e) {
      // network-level failure (connection drop, server restart) — fall through
      // to the same error card as an HTTP failure; course stays null.
    }
    if (ui.screen !== "syllabus") { ui.creatingCourse = false; return; } // navigated away mid-create
    if (!course) {
      ui.creatingCourse = false;
      const view = root.querySelector("#view");
      view.innerHTML =
        `<div class="card"><div class="prompt">Couldn't create the course right now. Your proposal is still here — try again.</div>` +
        `<div class="nav"><button class="btn-back" data-action="back">Back to proposal</button></div></div>`;
      view.querySelector('[data-action="back"]').addEventListener("click", () => showSyllabus(proposed));
      return;
    }
    ui.creatingCourse = false;
    log("course_created", { courseId: course.id });
    openCourse(course.id);
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

  let profile;
  try {
    profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  } catch (e) {
    root.innerHTML =
      `<div class="card"><div class="prompt">Couldn't reach the server. Check that the service is running, then retry.</div>` +
      `<div class="nav"><button class="btn-primary" data-action="retry">Retry</button></div></div>`;
    root.querySelector('[data-action="retry"]').addEventListener("click", () => window.location.reload());
    return;
  }
  if (profile) showHome();
  else showDiagnostic();
}
