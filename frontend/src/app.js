import { esc } from "./escape.js";
import { themedMermaid } from "./figuretheme.js";
import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile, saveProfile, buildProfile } from "./profile.js";
import { timerView, TOTAL_SECONDS } from "./timer.js";
import { listCourses, loadCourse, loadLesson, getLessonStatus, createCourse, loadReviews, loadReviewItems, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, loadCourseNotes, loadMisconceptions, deleteMisconception, compileProgram, reviseCourse, applyRevision, explainAnswer, gradeTeaching, startExam, submitExam, startRemediation, loadTranscript, gradeRemediationApply, submitCapstone, sendFeedback, getQuizRound, postQuizResults, getQuizStats, makeHighlightReviewItem, startLessonGeneration, getGenerationProgress, listGenerationJobs } from "./courses.js";
import { loadStats, loadActivity } from "./stats.js";
import { arcadeHTML, arcadeGeneratingHTML, arcadeLockedHTML, arcadeTimeoutHTML, hostIntroHTML, questionHTML, gradeChoice, matchBoardHTML, matchUpInit, matchUpSelectLeft, matchUpSelectRight, matchUpScore, arcadeResultHTML } from "./views/arcade.js";
import { shellHTML, feedbackBarHTML } from "./views/shell.js";
import { homeHTML } from "./views/home.js";
import { dashboardHTML } from "./views/dashboard.js";
import { lessonHTML, ratingLocked } from "./views/lesson.js";
import { activateHTML } from "./views/activate.js";
import { curriculumHTML } from "./views/curriculum.js";
import { capstoneHTML } from "./views/capstone.js";
import { libraryHTML } from "./views/library.js";
import { myNotesHTML } from "./views/mynotes.js";
import { misconceptionsHTML } from "./views/misconceptions.js";
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
import { autoGrowTextarea } from "./autogrow.js";
import { countOccurrencesBefore, flattenTextNodes, applyHighlight, applyHighlights, removeHighlightMarks } from "./highlights.js";
import { genFeedHTML, genLineHTML, genErrorHTML, genChipHTML, formatElapsed } from "./views/genfeed.js";

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

  // ---- auto-growing textareas (every chat/notes/answer box in the app) ----
  // Grows while typing (input listener) AND when a screen paints with a textarea
  // already holding content — e.g. reopening a lesson with saved notes, or an
  // in-progress exam answer — via a MutationObserver on every root repaint, so
  // no individual paint function needs to remember to call this itself.
  root.addEventListener("input", (e) => {
    if (e.target.tagName === "TEXTAREA") autoGrowTextarea(e.target);
  });
  if (typeof window.MutationObserver === "function") {
    // A streamed chat reply repaints its thread once PER CHUNK — dozens of
    // mutations a second on a fast stream. Coalesce to at most once per
    // animation frame instead of re-measuring every textarea on every chunk.
    let growPending = false;
    const rAF = typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame.bind(window)
      : (fn) => window.setTimeout(fn, 16);
    new window.MutationObserver(() => {
      if (growPending) return;
      growPending = true;
      rAF(() => {
        growPending = false;
        root.querySelectorAll("textarea").forEach(autoGrowTextarea);
      });
    }).observe(root, { childList: true, subtree: true });
  }

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
    arcade: null,
    arcadeCourseId: null,
    quizPlay: null,
    arcadePollTimer: null,
    feedback: { open: false, sending: false, text: "", notice: "", activeWhere: "top" },
    profile: null,
    continueToLessonAfterReview: false,
    curriculumNotedIds: null,
    genJob: null,
    genRetry: null,
    genPollTimer: null,
  };

  // ---- feedback bar (global; delegated on root so it survives every shell repaint) ----
  // Two slots can exist at once (the topbar's, always present, plus the lesson
  // screen's second slot below the workspace panel) — both share the one
  // ui.feedback state and are kept in sync by painting into every slot found.
  function paintFeedbackBar() {
    root.querySelectorAll("[data-fb-slot]").forEach((slot) => {
      slot.innerHTML = feedbackBarHTML(ui.feedback);
    });
  }

  // Focuses the input in a SPECIFIC entry point (falls back to the first found)
  // so a lesson-side toggle/send doesn't yank focus up to a possibly-offscreen
  // topbar box — used both when opening and after a failed send.
  function focusFbInput(where) {
    const scoped = where && root.querySelector(`[data-fb-slot="${where}"] [data-field="fb-text"]`);
    const inp = scoped || root.querySelector('[data-field="fb-text"]');
    if (inp) inp.focus();
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
      focusFbInput(fb.activeWhere);
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
    const mark = e.target.closest("mark.highlight");
    if (mark) { showHighlightMenu(mark); return; }
    if (highlightMenu && !e.target.closest(".highlight-menu")) hideHighlightMenu();
    if (e.target.closest('[data-action="gen-retry"]')) {
      const t = ui.genRetry;
      ui.genRetry = null;
      if (t) openLesson(t.lessonId);
      return;
    }
    if (e.target.closest('[data-action="gen-open"]')) { openGenTarget(); return; }
    const fbToggle = e.target.closest('[data-action="feedback-toggle"]');
    if (fbToggle) {
      // Navigation repaints the shell with an empty slot without touching
      // ui.feedback.open, so the DOM — not the flag — is the truth for
      // whether the bar is currently showing. Toggling off the flag alone
      // would make the first tap after navigating do nothing. Any slot
      // reflects the same shared state, so checking one is representative
      // even when a second entry point (e.g. the lesson screen's) exists.
      const slot = root.querySelector("[data-fb-slot]");
      const visiblyOpen = !!(slot && slot.firstElementChild);
      if (visiblyOpen && ui.feedback.sending) return; // never hide an in-flight send
      ui.feedback.open = !visiblyOpen;
      ui.feedback.notice = "";
      // Remember which entry point the learner is using — reused by both this
      // open-focus and a later failed-send's refocus.
      ui.feedback.activeWhere = fbToggle.dataset.fbToggle || "top";
      paintFeedbackBar();
      if (ui.feedback.open) focusFbInput(ui.feedback.activeWhere);
      return;
    }
    if (e.target.closest('[data-action="feedback-send"]')) submitFeedback();
  });
  root.addEventListener("input", (e) => {
    if (e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      // Update state without a repaint (focus-steal rule). Two feedback-bar
      // instances can be on screen at once (topbar + lesson-side); sync every
      // Send button's disabled state, and mirror the typed value into any
      // OTHER instance's input (never the one being typed in — that would
      // steal the caret) so both stay visually consistent.
      ui.feedback.text = e.target.value;
      const ownSlot = e.target.closest("[data-fb-slot]");
      if (ownSlot) ui.feedback.activeWhere = ownSlot.getAttribute("data-fb-slot");
      root.querySelectorAll('[data-action="feedback-send"]').forEach((btn) => {
        btn.disabled = ui.feedback.sending || !e.target.value.trim();
      });
      root.querySelectorAll('[data-field="fb-text"]').forEach((inp) => {
        if (inp !== e.target) inp.value = e.target.value;
      });
    }
  });
  root.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches && e.target.matches('[data-field="fb-text"]')) {
      submitFeedback();
    }
  });

  // ---- lesson prose highlights: selection capture + "Highlight" button ----
  // Scoped ONLY to the lesson's own prose (.prompt inside #view) -- never the
  // exercise/solution/checks sections or the side chat/notes workspace. Purely
  // visual: nothing here reads or reacts to what's highlighted.
  let highlightBtn = null; // the floating button, created once and repositioned/reused
  function hideHighlightBtn() {
    if (highlightBtn) { highlightBtn.remove(); highlightBtn = null; }
  }
  function promptContainer() {
    if (ui.screen !== "lesson") return null;
    const view = root.querySelector("#view");
    return view ? view.querySelector(".prompt") : null;
  }
  function showHighlightBtn(range) {
    if (!highlightBtn) {
      highlightBtn = doc.createElement("button");
      highlightBtn.type = "button";
      highlightBtn.className = "highlight-btn";
      highlightBtn.textContent = "Highlight";
      // Stop the button's own mousedown from collapsing the selection it needs to read.
      highlightBtn.addEventListener("mousedown", (e) => e.preventDefault());
      highlightBtn.addEventListener("click", addHighlightFromSelection);
      doc.body.appendChild(highlightBtn);
    }
    const rect = range.getBoundingClientRect();
    highlightBtn.style.top = `${Math.max(8, rect.top - 40)}px`;
    highlightBtn.style.left = `${rect.left}px`;
  }
  // Fires on every selectionchange -- covers both desktop click-drag and mobile
  // long-press-drag with one listener. Shows the button only when the selection is
  // non-collapsed AND fully contained within .prompt (the scope rule) -- a selection
  // touching the exercise, checks, or side-chat area never shows it.
  function captureSelectionForHighlight() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) { hideHighlightBtn(); return; }
    const container = promptContainer();
    if (!container) { hideHighlightBtn(); return; }
    const range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      hideHighlightBtn();
      return;
    }
    showHighlightBtn(range);
  }
  doc.addEventListener("selectionchange", captureSelectionForHighlight);

  // Tapping the floating button: reads the live selection, computes `occurrence`
  // (which match of the exact selected text this is, counted across the container's
  // flattened text at THIS moment -- the anchoring rule), saves it, and applies the
  // mark immediately.
  function addHighlightFromSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) { hideHighlightBtn(); return; }
    const container = promptContainer();
    if (!container) { hideHighlightBtn(); return; }
    const range = sel.getRangeAt(0);
    const text = sel.toString();
    const { text: fullText, nodes } = flattenTextNodes(container);
    const startEntry = nodes.find((n) => n.node === range.startContainer);
    hideHighlightBtn();
    sel.removeAllRanges();
    if (!text.trim() || !startEntry) return; // can't anchor it -> no-op, never guess
    const ws = ui.lessonState.ws;
    if (!ws) return;
    const startOffset = startEntry.start + range.startOffset;
    const occurrence = countOccurrencesBefore(fullText, text, startOffset);
    const highlight = { id: newId("hl-"), text, occurrence };
    ws.highlights = [...(ws.highlights || []), highlight];
    applyHighlight(container, highlight);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }
  // Removes one highlight: drop its id from the stored list, unwrap its mark(s) back
  // into plain text (no re-render needed -- this mutates the live DOM directly), and
  // save immediately (same non-debounced trigger as creation).
  function removeHighlightAt(mark) {
    const container = promptContainer();
    const id = mark.dataset.highlightId;
    const ws = ui.lessonState.ws;
    if (!container || !id || !ws) return;
    ws.highlights = (ws.highlights || []).filter((h) => h.id !== id);
    removeHighlightMarks(container, id);
    saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
  }

  // Tapping any <mark> opens a small 2-action menu instead of removing it outright:
  // "Remove" (the old behavior) or "Make review item" (a paid, one-shot Claude call
  // that turns the highlighted passage into a retrieval-practice question, persisted
  // server-side at backend/review_items.py's userItems -- a store independent of this
  // workspace's highlights list, so removing the highlight afterward never deletes the
  // item it produced). Tapping the same mark again toggles the menu closed.
  let highlightMenu = null;
  let highlightMenuId = null;
  function hideHighlightMenu() {
    if (highlightMenu) { highlightMenu.remove(); highlightMenu = null; }
    highlightMenuId = null;
  }
  function showHighlightMenu(mark) {
    const id = mark.dataset.highlightId;
    if (!id) return;
    if (highlightMenuId === id) { hideHighlightMenu(); return; }
    hideHighlightMenu();
    const menu = doc.createElement("div");
    menu.className = "highlight-menu";
    menu.innerHTML =
      '<button type="button" data-action="hl-review">Make review item</button>' +
      '<button type="button" data-action="hl-remove">Remove</button>';
    doc.body.appendChild(menu);
    const rect = mark.getBoundingClientRect();
    menu.style.top = `${Math.max(8, rect.top - 76)}px`;
    menu.style.left = `${rect.left}px`;
    menu.querySelector('[data-action="hl-remove"]').addEventListener("click", () => {
      removeHighlightAt(mark);
      hideHighlightMenu();
    });
    menu.querySelector('[data-action="hl-review"]').addEventListener("click", () => makeReviewItemFromHighlight(mark, menu));
    highlightMenu = menu;
    highlightMenuId = id;
  }
  // Busy-guards both buttons for the duration of the call (the double-click-races-a-
  // paid-call idiom used elsewhere -- e.g. teach-start's `entering` guard) so a fast
  // second tap can't fire two generations for the same highlight.
  function makeReviewItemFromHighlight(mark, menu) {
    const id = mark.dataset.highlightId;
    const ws = ui.lessonState.ws;
    const highlight = ws && (ws.highlights || []).find((h) => h.id === id);
    if (!highlight) { hideHighlightMenu(); return; }
    const reviewBtn = menu.querySelector('[data-action="hl-review"]');
    const removeBtn = menu.querySelector('[data-action="hl-remove"]');
    reviewBtn.disabled = true;
    removeBtn.disabled = true;
    reviewBtn.textContent = "Adding…";
    const courseId = ui.courseId;
    const lessonId = ui.lesson.id;
    makeHighlightReviewItem({ fetch, courseId, lessonId, text: highlight.text }).then((res) => {
      if (highlightMenu !== menu) return; // menu was dismissed or replaced mid-request
      if (res.error) {
        reviewBtn.textContent = "Couldn't add — try again";
        reviewBtn.disabled = false;
        removeBtn.disabled = false;
        return;
      }
      reviewBtn.textContent = "Added to review";
      window.setTimeout(() => { if (highlightMenu === menu) hideHighlightMenu(); }, 900);
    });
  }

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
      ui.profile = profile;
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
    const arc = view.querySelector('[data-action="arcade"]');
    if (arc) arc.addEventListener("click", showArcade);
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
      contract: (ui.manifest && ui.manifest.schemaVersion >= 2) ? {
        level: (ui.manifest.level && (ui.manifest.level.label || ui.manifest.level.code)) || "",
        hours: ui.manifest.targetHours || null,
        skills: ui.manifest.skills || [],
      } : null,
      streakDays: (ui.stats && ui.stats.streakDays) || 0,
      streakCadence: (ui.stats && ui.stats.streakCadence) || "daily",
      heatmap: ui.stats && ui.stats.heatmap,
    };
  }

  function paintCourse() {
    const view = root.querySelector("#view");
    view.innerHTML = dashboardHTML(sessionData(), timerView(ui.timer.elapsed));
    view.querySelector('[data-action="start-session"]').addEventListener("click", startLesson);
    view.querySelector('[data-action="review"]').addEventListener("click", () => {
      // The standalone Review button must always land back on the dashboard when
      // it finishes, even if a "Start session" review-then-lesson flow was
      // interrupted earlier and left the flag set.
      ui.continueToLessonAfterReview = false;
      startReviewSession();
    });
    const cur = view.querySelector('[data-action="curriculum"]');
    if (cur) cur.addEventListener("click", showCurriculum);
    const lib = view.querySelector('[data-action="library"]');
    if (lib) lib.addEventListener("click", showLibrary);
    const mn = view.querySelector('[data-action="mynotes"]');
    if (mn) mn.addEventListener("click", showMyNotes);
    const mc = view.querySelector('[data-action="misconceptions"]');
    if (mc) mc.addEventListener("click", showMisconceptions);
    const ref = view.querySelector('[data-action="refine"]');
    if (ref) ref.addEventListener("click", startRefine);
    const cadenceBtn = view.querySelector('[data-action="streak-cadence"]');
    if (cadenceBtn) cadenceBtn.addEventListener("click", toggleStreakCadence);
  }

  // Flips the streak cadence setting (daily <-> weekly, charter Tier 1 #4) and
  // persists it via the SAME profile blob the onboarding diagnostic writes —
  // POST /api/profile replaces the whole record, so this always sends the full
  // merged object, never just the one changed key (would silently drop the
  // diagnostic answers otherwise). Re-fetches stats so the streak number itself
  // reflects the new cadence immediately, not just its label.
  async function toggleStreakCadence() {
    const btn = root.querySelector('[data-action="streak-cadence"]');
    if (btn) btn.disabled = true;
    const current = (ui.stats && ui.stats.streakCadence) || "daily";
    const next = current === "weekly" ? "daily" : "weekly";
    const merged = { ...(ui.profile || {}), streakCadence: next };
    await saveProfile({ fetch, endpoint: PROFILE_ENDPOINT, profile: merged });
    ui.profile = merged;
    ui.stats = (await loadStats({ fetch })) || ui.stats;
    if (ui.screen === "course") paintCourse();
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

  // "My notes" (charter Tier 3 #20): a read-only per-course aggregate of every
  // lesson's notes + highlights. Display only, mirrors showLibrary's shape.
  async function showMyNotes() {
    pauseTimer();
    ui.screen = "mynotes";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Loading your notes…</div></div>`;
    const data = await loadCourseNotes({ fetch, courseId: ui.courseId });
    if (ui.screen !== "mynotes") return; // navigated away mid-load
    view.innerHTML = myNotesHTML(data);
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
  }

  // Misconceptions profile (charter Tier 2 item 7): read-only + delete-only,
  // mirrors showMyNotes's shape exactly.
  async function showMisconceptions() {
    pauseTimer();
    ui.screen = "misconceptions";
    root.innerHTML = shellHTML({ back: ui.manifest ? ui.manifest.title : "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Loading your misconceptions…</div></div>`;
    const data = await loadMisconceptions({ fetch, courseId: ui.courseId });
    if (ui.screen !== "misconceptions") return; // navigated away mid-load
    paintMisconceptions(data);
  }

  function paintMisconceptions(data) {
    const view = root.querySelector("#view");
    view.innerHTML = misconceptionsHTML(data);
    view.querySelector('[data-action="back"]').addEventListener("click", showCourse);
    view.querySelectorAll('[data-action="delete-misconception"]').forEach((btn) => {
      btn.addEventListener("click", () => deleteMisconceptionEntry(btn, data));
    });
  }

  // Busy-guards the clicked button for the duration of the call (the
  // double-click-races-a-request idiom used elsewhere, e.g. the highlight
  // menu's guard) so a fast second click can't double-fire the DELETE.
  async function deleteMisconceptionEntry(btn, data) {
    if (btn.disabled) return;
    btn.disabled = true;
    const entryId = btn.getAttribute("data-entry");
    const res = await deleteMisconception({ fetch, courseId: ui.courseId, entryId });
    if (ui.screen !== "misconceptions") return; // navigated away mid-request
    if (res.error) {
      btn.disabled = false;
      return;
    }
    data.entries = data.entries.filter((e) => e.id !== entryId);
    paintMisconceptions(data);
  }

  function showCurriculum() {
    pauseTimer();
    ui.screen = "curriculum";
    ui.curriculumNotedIds = null; // stale from a previous course — reload before showing any indicator
    root.innerHTML = shellHTML({ back: ui.manifest.title });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showCourse);
    paintCurriculum();
    loadCurriculumNotedIds();
  }

  // Background, non-blocking (charter Tier 3 #20's curriculum-row indicator):
  // the curriculum itself renders immediately from data already in memory;
  // this repaints once the notes summary lands, same idiom as fetchFreshItems.
  function loadCurriculumNotedIds() {
    const courseId = ui.courseId;
    loadCourseNotes({ fetch, courseId }).then((data) => {
      if (ui.courseId !== courseId || ui.screen !== "curriculum") return;
      ui.curriculumNotedIds = new Set((data.lessons || []).map((l) => l.lessonId));
      paintCurriculum();
    }).catch(() => {});
  }

  function paintCurriculum() {
    const view = root.querySelector("#view");
    view.innerHTML = curriculumHTML(ui.manifest, (ui.manifest && ui.manifest.mastery) || {}, currentLessonId(), ui.manifest && ui.manifest.exams, !!(ui.manifest && ui.manifest.coursePassed), ui.curriculumNotedIds);
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

  // ---- Arcade: surprise-format quiz rounds over completed lessons ----

  // Cleans up any in-flight arcade play state — the rapid-fire countdown interval and
  // the round-generation poll timeout — so a leaked timer can't fire later and repaint
  // the shared #view node the user has since navigated off of. Called at the top of
  // showArcade so every route back through the Arcade grid (from arcade-loading or
  // arcade-play) tears down its timers. Belt-and-braces: the countdown tick itself
  // also carries a screen guard (see startCountdown) for exits that bypass showArcade
  // entirely (home nav, course nav).
  // ui.quizPlay = null also discards any open qchat thread with it (design decision 2:
  // ephemeral, cleared on resetArcadePlay) — nothing further to do for that here.
  function resetArcadePlay() {
    if (ui.quizPlay && ui.quizPlay.countdownTimer) window.clearInterval(ui.quizPlay.countdownTimer);
    if (ui.arcadePollTimer) window.clearTimeout(ui.arcadePollTimer);
    ui.arcadePollTimer = null;
    ui.quizPlay = null;
  }

  async function showArcade() {
    pauseTimer();
    resetArcadePlay();
    ui.screen = "arcade";
    root.innerHTML = shellHTML({ back: "Courses" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showHome);
    const view = root.querySelector("#view");
    view.innerHTML = `<div class="card"><div class="prompt">Loading the Arcade…</div></div>`;
    const courseList = await listCourses({ fetch, endpoint: COURSES_ENDPOINT });
    if (ui.screen !== "arcade") return; // navigated away mid-load
    const statsByCourseId = {};
    await Promise.all(
      courseList
        .filter((c) => c.progress && c.progress.done > 0)
        .map(async (c) => { statsByCourseId[c.id] = await getQuizStats({ fetch, courseId: c.id }); }),
    );
    if (ui.screen !== "arcade") return; // navigated away mid-load
    ui.arcade = { courses: courseList, statsByCourseId };
    paintArcade();
  }

  function paintArcade() {
    const view = root.querySelector("#view");
    view.innerHTML = arcadeHTML(ui.arcade.courses, ui.arcade.statsByCourseId);
    view.querySelectorAll("[data-arcade-play]").forEach((btn) => {
      btn.addEventListener("click", () => startArcadeRound(btn.getAttribute("data-arcade-play")));
    });
  }

  async function startArcadeRound(courseId) {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "arcade-loading";
    ui.arcadeCourseId = courseId;
    root.innerHTML = shellHTML({ back: "Arcade" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showArcade);
    const view = root.querySelector("#view");
    view.innerHTML = arcadeGeneratingHTML();
    pollArcadeRound(courseId, seq, 0);
  }

  async function pollArcadeRound(courseId, seq, elapsedMs) {
    const data = await getQuizRound({ fetch, courseId });
    if (ui.screen !== "arcade-loading" || ui.loadSeq !== seq) return; // navigated away mid-poll
    if (data.status === "locked") {
      root.querySelector("#view").innerHTML = arcadeLockedHTML();
      return;
    }
    if (data.status === "ready" && data.round) {
      beginRound(data.round);
      return;
    }
    const nextElapsed = elapsedMs + 3000;
    if (nextElapsed >= 90000) {
      const view = root.querySelector("#view");
      view.innerHTML = arcadeTimeoutHTML();
      view.querySelector('[data-action="arcade-retry"]').addEventListener("click", () => startArcadeRound(courseId));
      return;
    }
    ui.arcadePollTimer = window.setTimeout(() => pollArcadeRound(courseId, seq, nextElapsed), 3000);
  }

  function beginRound(round) {
    ui.screen = "arcade-play";
    root.innerHTML = shellHTML({ back: "Arcade" });
    root.querySelector('[data-action="nav-back"]').addEventListener("click", showArcade);
    ui.quizPlay = {
      round, phase: "intro", index: 0, score: 0, total: 0, missed: {},
      answered: false, selected: null, countdown: null, countdownTimer: null,
      matchState: round.format === "match_up" ? matchUpInit(round.questions[0]) : null,
      qchat: null, // post-answer "Ask about this question" thread — ephemeral (design decision 2)
    };
    paintArcadePlay();
  }

  function paintArcadePlay() {
    const st = ui.quizPlay;
    const view = root.querySelector("#view");
    if (st.phase === "intro") {
      view.innerHTML = hostIntroHTML(st.round);
      view.querySelector('[data-action="arcade-begin"]').addEventListener("click", () => {
        st.phase = "playing";
        if (st.round.format === "rapid_fire") startCountdown();
        paintArcadePlay();
      });
      return;
    }
    if (st.phase === "result") {
      const saveNotice = st.saveFailed
        ? `<div class="prompt">Score could not be saved.</div>` +
          `<button class="btn-secondary" data-action="arcade-retry-save" ${st.saving ? "disabled" : ""}>${st.saving ? "Retrying…" : "Retry save"}</button>`
        : "";
      view.innerHTML = arcadeResultHTML(st, st.lessonTitles || {}) + saveNotice;
      view.querySelector('[data-action="arcade-play-again"]').addEventListener("click", () => startArcadeRound(ui.arcadeCourseId));
      view.querySelector('[data-action="arcade-back"]').addEventListener("click", showArcade);
      if (st.saveFailed && !st.saving) {
        view.querySelector('[data-action="arcade-retry-save"]').addEventListener("click", retrySaveResult);
      }
      view.querySelectorAll("[data-lesson]").forEach((b) => {
        b.addEventListener("click", () => openMissedLesson(b.getAttribute("data-lesson")));
      });
      return;
    }
    if (st.round.format === "match_up") {
      view.innerHTML = matchBoardHTML(st.round, st.index, st.matchState, st.qchat);
      view.querySelectorAll("[data-match-left]").forEach((b) => {
        b.addEventListener("click", () => tapMatchLeft(Number(b.getAttribute("data-match-left"))));
      });
      view.querySelectorAll("[data-match-right]").forEach((b) => {
        b.addEventListener("click", () => tapMatchRight(Number(b.getAttribute("data-match-right"))));
      });
      const next = view.querySelector('[data-action="arcade-next"]');
      if (next) next.addEventListener("click", advanceMatchBoard);
      bindQuizChat(view);
      return;
    }
    view.innerHTML = questionHTML(st.round, st.index, st);
    view.querySelectorAll("[data-arcade-choice]").forEach((b) => {
      b.addEventListener("click", () => answerChoice(Number(b.getAttribute("data-arcade-choice"))));
    });
    const next = view.querySelector('[data-action="arcade-next"]');
    if (next) next.addEventListener("click", advanceQuestion);
    bindQuizChat(view);
  }

  // ---- post-answer "Ask about this question" chat (design: 2026-07-17) ----
  // Ephemeral, stateless thread on ui.quizPlay.qchat — never persisted, no events.
  // The "Ask about this question" button/panel is only ever painted post-answer
  // (reveal phase) or after a completed match-up board — see arcade.js's gating.

  function bindQuizChat(view) {
    const st = ui.quizPlay;
    const openBtn = view.querySelector('[data-action="quiz-chat-open"]');
    if (openBtn) openBtn.addEventListener("click", () => {
      if (st.qchat) return; // already open — the toggle button isn't even painted once open
      st.qchat = { open: true, messages: [], streaming: false };
      paintArcadePlay();
    });
    const sendBtn = view.querySelector('[data-action="quiz-chat-send"]');
    if (sendBtn) sendBtn.addEventListener("click", sendQuizChat);
    const thread = view.querySelector(".qc-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  // Shapes the learner's answer to match how `question.answer` itself is represented
  // for that format, so the prompt never has to reverse-engineer a UI-only index:
  // true_false's answer is a boolean (the True/False buttons are index 0/1 only in the
  // DOM), match_up has no single answer at all — send its first-attempt score instead —
  // and the remaining choice formats already use a plain index, same as their own
  // `answer` field, so the raw selection passes through untouched.
  function quizChatAnswerGiven(st, q) {
    if (st.round.format === "match_up") {
      const { correct, total } = matchUpScore(st.matchState, q);
      return { correct, total };
    }
    if (st.round.format === "true_false") {
      return st.selected === null || st.selected === undefined ? null : st.selected === 0;
    }
    return st.selected;
  }

  // question.format isn't on the per-question object itself (it's a property of the
  // whole round) — merge it in so the chat prompt always knows which format it's
  // explaining, per the design doc's question shape.
  function quizChatQuestion(st, q) {
    return { format: st.round.format, ...q };
  }

  function sendQuizChat() {
    const st = ui.quizPlay;
    const qchat = st && st.qchat;
    if (!qchat || qchat.streaming) return; // guards a double-fire while a reply streams
    const ta = root.querySelector('[data-field="qc-input"]');
    const text = ta ? ta.value.trim() : "";
    if (!text) return;
    qchat.messages.push({ role: "user", content: text });
    streamQuizChatReply(st, qchat);
  }

  async function streamQuizChatReply(st, qchat) {
    qchat.streaming = true;
    const reply = { role: "assistant", content: "" };
    // Captures BOTH the play state and the specific qchat thread object: advanceQuestion/
    // advanceMatchBoard/resetArcadePlay all clear qchat (set it to null or a fresh object)
    // rather than replacing ui.quizPlay itself, so a late chunk after advancing to the next
    // question must be dropped even though `ui.quizPlay === st` is still true.
    const onScreen = () => ui.quizPlay === st && st.qchat === qchat && ui.screen === "arcade-play";
    paintArcadePlay();
    const q = st.round.questions[st.index];
    await streamChat({
      fetch,
      endpoint: `/api/courses/${ui.arcadeCourseId}/quiz/question-chat`,
      messages: qchat.messages.map((m) => ({ role: m.role, content: m.content })),
      extra: { lesson_id: q.lesson_id, question: quizChatQuestion(st, q), answerGiven: quizChatAnswerGiven(st, q) },
      onDelta: (d) => {
        reply.content += d;
        if (!onScreen()) return;
        const thread = root.querySelector(".qc-thread");
        if (thread) {
          const typing = thread.querySelector(".qc-typing");
          if (typing) typing.remove();
          let live = thread.querySelector(".qc-live");
          if (!live) { live = doc.createElement("div"); live.className = "qc-msg qc-ai qc-live"; thread.appendChild(live); }
          live.textContent = reply.content;
          thread.scrollTop = thread.scrollHeight;
        }
      },
      onDone: () => {
        qchat.streaming = false;
        if (reply.content.trim()) qchat.messages.push(reply);
        if (onScreen()) paintArcadePlay();
      },
      onError: (e) => {
        // Plain-text error line, no emoji (spec copy rule) — unlike the lesson
        // workspace chat's "⚠️ " prefix, this feature's copy is emoji-free throughout.
        qchat.streaming = false;
        qchat.messages.push({ role: "assistant", content: (e && e.message) || "Claude is unavailable right now." });
        if (onScreen()) paintArcadePlay();
      },
    });
  }

  function clearCountdown() {
    const st = ui.quizPlay;
    if (st.countdownTimer) window.clearInterval(st.countdownTimer);
    st.countdownTimer = null;
  }

  function startCountdown() {
    const st = ui.quizPlay;
    st.countdown = 15;
    clearCountdown();
    st.countdownTimer = window.setInterval(() => {
      // Belt-and-braces: resetArcadePlay() (called from showArcade) already clears this
      // interval on every nav-back through the Arcade grid. This guard catches any exit
      // that bypasses showArcade (home nav, course nav) — without it, a leaked tick would
      // call answerChoice(null) -> paintArcadePlay() and clobber whatever screen the user
      // has navigated to since, because paintArcadePlay overwrites the shared #view node.
      if (ui.screen !== "arcade-play" || ui.quizPlay !== st) {
        window.clearInterval(st.countdownTimer);
        return;
      }
      st.countdown -= 1;
      if (st.countdown <= 0) {
        clearCountdown();
        if (!st.answered) answerChoice(null); // timeout — no selection made, always a miss
        return;
      }
      const el = root.querySelector(".arcade-countdown");
      if (el) el.textContent = `${st.countdown}s`;
    }, 1000);
  }

  function answerChoice(selected) {
    const st = ui.quizPlay;
    if (st.answered) return;
    clearCountdown();
    const correct = gradeChoice(st.round, st.index, selected);
    st.answered = true;
    st.selected = selected;
    st.total += 1;
    if (correct) {
      st.score += 1;
    } else {
      const lessonId = st.round.questions[st.index].lesson_id;
      st.missed[lessonId] = (st.missed[lessonId] || 0) + 1;
    }
    paintArcadePlay();
  }

  function advanceQuestion() {
    const st = ui.quizPlay;
    st.index += 1;
    st.answered = false;
    st.selected = null;
    st.countdown = null;
    st.qchat = null; // ephemeral — discarded on advance (design decision 1/2)
    if (st.index >= st.round.questions.length) {
      finishRound();
      return;
    }
    if (st.round.format === "rapid_fire") startCountdown();
    paintArcadePlay();
  }

  function tapMatchLeft(leftIndex) {
    const st = ui.quizPlay;
    st.matchState = matchUpSelectLeft(st.matchState, leftIndex);
    paintArcadePlay();
  }

  function tapMatchRight(rightPairIndex) {
    const st = ui.quizPlay;
    const board = st.round.questions[st.index];
    st.matchState = matchUpSelectRight(st.matchState, board, rightPairIndex);
    paintArcadePlay();
  }

  function advanceMatchBoard() {
    const st = ui.quizPlay;
    const board = st.round.questions[st.index];
    const { correct, total } = matchUpScore(st.matchState, board);
    st.score += correct;
    st.total += total;
    const missCount = total - correct;
    if (missCount > 0) st.missed[board.lesson_id] = (st.missed[board.lesson_id] || 0) + missCount;
    st.qchat = null; // ephemeral — discarded on advance (design decision 1/2)
    st.index += 1;
    if (st.index >= st.round.questions.length) {
      finishRound();
      return;
    }
    st.matchState = matchUpInit(st.round.questions[st.index]);
    paintArcadePlay();
  }

  async function finishRound() {
    const st = ui.quizPlay;
    st.phase = "result";
    st.saveFailed = false;
    st.saving = false;
    // Fixed at finish time and reused on retry — the backend is idempotent on
    // client_event_id, so re-posting the same payload after a failure is safe.
    st.savePayload = {
      client_event_id: newId("qr-"),
      session_id: sessionId,
      round_id: st.round.round_id,
      format: st.round.format,
      score: st.score,
      total: st.total,
      missed: st.missed,
    };
    if (Object.keys(st.missed).length) loadMissedTitles(st).catch(() => {});
    paintArcadePlay();
    await saveRoundResult(st);
  }

  // Shared by finishRound and the result screen's "Retry save" button.
  async function saveRoundResult(st) {
    const result = await postQuizResults({ fetch, courseId: ui.arcadeCourseId, result: st.savePayload });
    if (ui.quizPlay !== st || ui.screen !== "arcade-play") return; // navigated away mid-save
    st.saving = false;
    st.saveFailed = !result || !!result.error;
    if (st.phase === "result") paintArcadePlay();
  }

  // Titles for the result screen's missed-lesson chips. Fail-open: the score renders
  // immediately with raw-id chips; titles repaint when (if) the manifest arrives.
  async function loadMissedTitles(st) {
    const course = await loadCourse({ fetch, courseId: ui.arcadeCourseId });
    if (ui.quizPlay !== st || ui.screen !== "arcade-play") return; // navigated away mid-fetch
    if (!course || course.error) return;
    const titles = {};
    (course.modules || []).forEach((m) => (m.lessons || []).forEach((l) => { titles[l.id] = l.title; }));
    st.lessonTitles = titles;
    if (st.phase === "result") paintArcadePlay();
  }

  // Chip tap: enter the course's context first (the Arcade is course-less), then open
  // the lesson so Prev/Next/curriculum all work. Mirrors openCourse's manifest guard.
  // Guarded like loadMissedTitles/saveRoundResult: bail if the player navigated away
  // (Play again / Back to Arcade) while refreshSummary was in flight.
  async function openMissedLesson(lessonId) {
    const st = ui.quizPlay;
    ui.courseId = ui.arcadeCourseId;
    await refreshSummary();
    if (ui.quizPlay !== st || ui.screen !== "arcade-play") return; // navigated away mid-fetch
    if (!ui.manifest) { showHome(); return; }
    openLesson(lessonId);
  }

  function retrySaveResult() {
    const st = ui.quizPlay;
    if (!st || st.phase !== "result" || !st.saveFailed || st.saving) return;
    st.saving = true;
    paintArcadePlay();
    saveRoundResult(st);
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
    // Rejoining a lesson whose generation is already running: skip the status
    // check and the prior-knowledge card (it was answered when the job started)
    // and drop straight back into the live feed.
    if (ui.genJob && ui.genJob.courseId === ui.courseId
        && ui.genJob.lessonId === lessonId && ui.genJob.status === "running") {
      ui.reviewQueue = [];
      ui.loadSeq = (ui.loadSeq || 0) + 1;
      startGenerationFeed(lessonId, ui.loadSeq);
      return;
    }
    // A finished job's chip is only meaningful until its lesson is opened. Any
    // direct open of that lesson (syllabus, next-lesson button) retires the chip
    // and, via pollGeneration's !job guard, ends the keep-alive loop.
    if (ui.genJob && ui.genJob.courseId === ui.courseId
        && ui.genJob.lessonId === lessonId && ui.genJob.status !== "running") {
      ui.genJob = null;
      paintGenChip();
    }
    ui.reviewQueue = [];
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "lesson-loading";
    // Cache-first: nearly every open is an already-generated lesson that resolves in a
    // few hundred ms, and painting the skeleton immediately made every open flash it.
    // Delay the paint; the re-check makes a fast open (or navigating away) skip it, and
    // the slow paths (generation, slow Pi) still get the skeleton after 200ms.
    window.setTimeout(() => {
      if (ui.screen !== "lesson-loading" || ui.loadSeq !== seq) return;
      const v = root.querySelector("#view");
      if (v) startLoading(v, "lesson", LESSON_STAGES);
    }, 200);
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
      await startGenerationFeed(lessonId, seq);
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

  // ---- live generation feed (2026-07-21 design) ----
  // The job lives on the server; ui.genJob only mirrors it. The feed's DOM
  // presence (data-gen-feed) is the truth for "is the learner watching" — the
  // same idiom startLoading uses — so roaming needs no bookkeeping.
  function paintGenChip() {
    root.querySelectorAll("[data-gen-chip]").forEach((slot) => {
      slot.innerHTML = genChipHTML(ui.genJob);
    });
  }

  function appendGenEvents(snap) {
    if (ui.genJob) ui.genJob.next = snap.next;
    const feed = root.querySelector("[data-gen-feed]");
    if (feed && (snap.events || []).length) {
      for (const ev of snap.events) feed.insertAdjacentHTML("beforeend", genLineHTML(ev));
      feed.scrollTop = feed.scrollHeight;
    }
    const el = root.querySelector("[data-gen-elapsed]");
    if (el && snap.elapsed != null) el.textContent = formatElapsed(snap.elapsed);
  }

  function scheduleGenPoll() {
    // Clear-then-arm (same idiom as ui.arcadePollTimer): rejoining the feed calls
    // startGenerationFeed again, and without the clear the old chain and the new
    // one would BOTH tick — duplicate polls and duplicated feed lines.
    window.clearTimeout(ui.genPollTimer);
    ui.genPollTimer = window.setTimeout(pollGeneration, 2000);
  }

  async function pollGeneration() {
    const job = ui.genJob;
    if (!job) return; // opened/cleared — the chain ends here
    if (job.status !== "running") {
      // done/error while roaming: no network needed, but keep the chip painted
      // across shell repaints (navigation empties the slot).
      paintGenChip();
      scheduleGenPoll();
      return;
    }
    const snap = await getGenerationProgress({
      fetch, courseId: job.courseId, lessonId: job.lessonId, since: job.next,
    });
    if (ui.genJob !== job) return; // superseded while awaiting
    // A transport failure (network/HTTP) never carries a status field; a real
    // snapshot always does, even for a failed job ({status: "error", error: "..."}).
    // Testing snap.error here would swallow every real job failure as a retry-forever
    // blip and make the error UX (re-auth, took-too-long, retry chip) unreachable.
    if (!snap.status) { scheduleGenPoll(); return; } // network blip — next tick retries
    job.status = snap.status;
    job.elapsed = snap.elapsed;
    appendGenEvents(snap);
    paintGenChip();
    if (snap.status === "running") { scheduleGenPoll(); return; }
    if (snap.status === "done") { onGenerationDone(job); return; }
    onGenerationFailed(job, snap.error || (snap.status === "none"
      ? "Generation was interrupted on the server — try again."
      : "Something went wrong during generation."));
  }

  async function startGenerationFeed(lessonId, seq) {
    // Defensive clear-on-entry (same reason as resetArcadePlay's timer clear):
    // a pending tick or in-flight poll from the roaming chain must not append
    // to the feed we are about to repaint — the POST's from-0 snapshot is the
    // single source of truth for the backfill.
    window.clearTimeout(ui.genPollTimer);
    ui.genJob = null;
    ui.screen = "generating";
    const found = flatLessons().find((l) => l.id === lessonId);
    const view = root.querySelector("#view");
    if (view) view.innerHTML = genFeedHTML(found ? found.title : lessonId);
    const snap = await startLessonGeneration({ fetch, courseId: ui.courseId, lessonId });
    if (ui.loadSeq !== seq) return; // navigated away — the job runs on regardless
    // Same rationale as pollGeneration: a POST rejection (network blip, or the
    // 409 "another lesson is generating") arrives as {error} with no status field.
    if (!snap.status) {
      ui.genRetry = { lessonId };
      if (view && view.isConnected) view.innerHTML = genErrorHTML(snap.error);
      return;
    }
    ui.genJob = {
      courseId: ui.courseId, lessonId, next: 0,
      status: snap.status, elapsed: snap.elapsed || 0,
    };
    appendGenEvents(snap); // POST returns the snapshot from 0 — the backfill on rejoin
    paintGenChip();
    if (snap.status === "done") { onGenerationDone(ui.genJob); return; }
    scheduleGenPoll();
  }

  function onGenerationDone(job) {
    if (ui.screen === "generating" && root.querySelector("[data-gen-feed]")) {
      ui.genJob = null;
      paintGenChip();
      ui.screen = "lesson-loading";
      const v = root.querySelector("#view");
      if (v) startLoading(v, "lesson", LESSON_STAGES);
      finishOpenLesson(job.lessonId, {}, ui.loadSeq);
      return;
    }
    paintGenChip();
    scheduleGenPoll(); // keep the "ready" chip alive across navigations
  }

  function onGenerationFailed(job, message) {
    job.message = message;
    if (ui.screen === "generating" && root.querySelector("[data-gen-feed]")) {
      ui.genJob = null;
      paintGenChip();
      ui.genRetry = { lessonId: job.lessonId };
      const v = root.querySelector("#view");
      if (v) v.innerHTML = genErrorHTML(message);
      return;
    }
    paintGenChip();
    scheduleGenPoll(); // keep the "failed" chip alive across navigations
  }

  // Chip click: a `done` job opens the now-cached lesson instantly; an `error`
  // job re-enters openLesson's normal uncached flow (status check, activate
  // card, fresh POST) — that IS the retry path, no separate branch needed.
  async function openGenTarget() {
    const job = ui.genJob;
    if (!job) return;
    ui.genJob = null;
    paintGenChip();
    if (ui.courseId !== job.courseId) {
      await openCourse(job.courseId);
      // openCourse fails soft to showHome() on a manifest-load failure (no signal to
      // the caller) — bail here instead of falling into openLesson -> showLesson,
      // which dereferences ui.manifest.title and would crash on the null left behind.
      if (!ui.manifest) return;
    }
    openLesson(job.lessonId);
  }

  // Charter Tier 3 #19 — honors the design brief's warm-up promise: due reviews are
  // a quick warm-up before new material, so "Start session" clears them first. The
  // continuation back into a new lesson happens in advanceAfterLesson's empty-queue
  // branch (the existing per-review "what's next" plumbing already runs there for
  // free); this flag is the only thing distinguishing that from a normal review
  // session started via the standalone Review button, which must still land back
  // on the dashboard when it finishes, unchanged.
  function startLesson() {
    if (ui.summary && ui.summary.reviewsDue > 0) {
      ui.continueToLessonAfterReview = true;
      startReviewSession();
      return;
    }
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
    // Matches the sticky two-column breakpoint (styles.css, >=1100px) — below it the
    // workspace has no dedicated column, so it should default closed.
    return { open: window.innerWidth >= 1100, tab: "notes" };
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
                       notes: wsData.notes || "", chat: wsData.chat || [], highlights: wsData.highlights || [],
                       pending: false, saveStatus: "" };
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
    const res = await saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
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
        saveWorkspace({ fetch, storage, courseId: cid, lessonId: lid, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
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

  // ---- drawn diagrams (slice 2): lazy-loaded vendored renderers, cached for the
  // session so a lesson with no drawn figures never pays the cost.
  let _purifyPromise = null;
  let _mermaidPromise = null;

  function loadScript(src, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    return new Promise((resolve, reject) => {
      const el = doc.createElement("script");
      el.src = src;
      el.onload = () => resolve(window[globalName]);
      el.onerror = () => reject(new Error(`failed to load ${src}`));
      doc.head.appendChild(el);
    });
  }

  function loadPurify() {
    if (!_purifyPromise) _purifyPromise = loadScript("/vendor/purify.min.js", "DOMPurify");
    return _purifyPromise;
  }

  function loadMermaidLib() {
    if (!_mermaidPromise) {
      _mermaidPromise = loadScript("/vendor/mermaid.min.js", "mermaid").then((m) => {
        m.initialize({ startOnLoad: false, securityLevel: "strict" });
        return m;
      });
    }
    return _mermaidPromise;
  }

  // Client-side SVG sanitization (defense in depth — the server allowlist in
  // backend/figures.py already ran at generation time; this also guards a hand-edited
  // cached lesson). DOMPurify's svg profile reassigns ALLOWED_TAGS/ALLOWED_ATTR from
  // USE_PROFILES, so those explicit lists are advisory intent, not the operative filter;
  // the FORBID_TAGS/FORBID_ATTR below ARE operative and remove the external-ref elements
  // (image/style/use/a/foreignObject/script and href/xlink:href) on top of DOMPurify's
  // core stripping of on* handlers and javascript: URLs. Effective client filter is thus
  // the hardened svg profile — intentionally broader than the server's strict allowlist.
  const SVG_SANITIZE_CONFIG = {
    USE_PROFILES: { svg: true, svgFilters: true },
    ALLOWED_TAGS: ["svg","g","rect","circle","ellipse","line","polyline","polygon","path","text","tspan","title","defs","marker"],
    ALLOWED_ATTR: ["viewBox","x","y","x1","y1","x2","y2","cx","cy","r","rx","ry","width","height","d","points","transform","fill","stroke","stroke-width","stroke-dasharray","font-size","font-family","font-weight","text-anchor","dominant-baseline","opacity","fill-opacity","marker-end","marker-start","id","class"],
    FORBID_TAGS: ["style","image","use","a","foreignObject","script"],
    FORBID_ATTR: ["href","xlink:href"],
  };

  // Hydrates every svg/mermaid figure placeholder currently painted in `view`. Called
  // once at the end of every paintLesson() repaint. lesson.js never string-interpolates
  // figure code into the template (see its comment on drawnFigurePlaceholderHTML), so
  // this is the ONLY place svg code is sanitized-again (DOMPurify, defense in depth over
  // the server-side allowlist) and mermaid code is rendered. `lesson` is captured by
  // value so a slow lazy-load that resolves after the learner has navigated away can
  // never inject into a detached node (mirrors the onScreen staleness guard used by
  // seedWorkspace/explain-grade elsewhere in this file) — repaints rebuild placeholders
  // from scratch, so a fresh hydration on a fresh node is naturally idempotent.
  function hydrateFigures(view, lesson) {
    const entries = Array.isArray(lesson.images) ? lesson.images : [];
    const byN = new Map(entries.map((e) => [e.n, e]));
    const stillFresh = () => ui.screen === "lesson" && ui.lesson === lesson;

    view.querySelectorAll("[data-fig-svg]").forEach((fig) => {
      const entry = byN.get(Number(fig.dataset.figSvg));
      if (!entry || typeof entry.code !== "string") return;
      loadPurify()
        .then((DOMPurify) => {
          if (!stillFresh() || !fig.isConnected) return;
          const clean = DOMPurify.sanitize(entry.code, SVG_SANITIZE_CONFIG);
          fig.insertAdjacentHTML("afterbegin", clean);
        })
        .catch(() => {}); // lazy-load/sanitize failure -> the caption already shown is the fallback
    });

    view.querySelectorAll("[data-fig-mermaid]").forEach((fig) => {
      const entry = byN.get(Number(fig.dataset.figMermaid));
      if (!entry || typeof entry.code !== "string") return;
      const renderId = `mermaid-fig-${entry.n}-${Math.random().toString(36).slice(2)}`;
      loadMermaidLib()
        .then((mermaid) => mermaid.render(renderId, themedMermaid(entry.code)))
        .then(({ svg }) => {
          if (!stillFresh() || !fig.isConnected) return;
          fig.insertAdjacentHTML("afterbegin", svg);
        })
        .catch(() => {}); // parse/render failure -> caption-as-text fallback (nothing injected)
    });
  }

  function paintLesson() {
    hideHighlightBtn(); // the DOM this button points at is about to be rebuilt
    hideHighlightMenu(); // same reason -- its target mark is about to be rebuilt
    const view = root.querySelector("#view");
    const nav = { hasPrev: !!adjacentLesson(-1), hasNext: !!adjacentLesson(1) };
    view.innerHTML = lessonHTML(ui.lesson, ui.lessonState, nav);
    hydrateFigures(view, ui.lesson);
    const promptEl = view.querySelector(".prompt");
    if (promptEl && ui.lessonState.ws) applyHighlights(promptEl, ui.lessonState.ws.highlights);
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
      const btn = view.querySelector('[data-action="check-answer"]');
      if (btn) btn.disabled = !ta.value.trim() || !!ui.lessonState.grading;

      // Keep reveal-solution button appearance in sync with the answer state
      const revealBtn = view.querySelector('[data-action="reveal-solution"]');
      if (revealBtn && !ui.lessonState.solutionRevealed) {
        const REVEAL_TEXT = { locked: "Attempt first to unlock the solution", ready: "Reveal solution", shown: "Solution shown" };
        const newState = ta.value.trim() ? "ready" : "locked";
        revealBtn.className = "reveal " + newState;
        const span = revealBtn.querySelector("span");
        if (span) span.textContent = REVEAL_TEXT[newState];
      }
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
      saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
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
        saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
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
        saveWorkspace({ fetch, storage, courseId: ui.courseId, lessonId: ui.lesson.id, notes: ws.notes, chat: ws.chat, highlights: ws.highlights });
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
    // Narrow-screen floating toggle: re-styles the SAME .lesson-side node (never
    // duplicated) between its in-flow position and a fixed bottom drawer. Bound here,
    // not inside bindWorkspace, so it works even in the brief window before
    // seedWorkspace resolves (the button doesn't depend on ws being seeded).
    const drawerToggle = view.querySelector('[data-action="ws-drawer-toggle"]');
    if (drawerToggle) drawerToggle.addEventListener("click", () => {
      ui.lessonState.drawerOpen = !ui.lessonState.drawerOpen;
      paintLesson();
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
      if (lessonFailed(ui.lesson)) {
        ui.continueToLessonAfterReview = false;
        await refreshSummary();
        if (ui.screen !== "lesson") return;
        showCourse();
        return;
      }
      ui.lessonState = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {}, stage: "main", isReview: true };
      fetchFreshItems(ui.lessonState, ui.lesson);
      log("lesson_view", { courseId: ui.courseId, topicId: nextId });
      showLesson();
      return;
    }
    await refreshSummary();
    if (ui.screen !== "lesson") return; // navigated away — don't yank them to the dashboard
    if (ui.continueToLessonAfterReview) {
      ui.continueToLessonAfterReview = false;
      startLesson(); // reviewsDue is now 0 (refreshSummary just reloaded it) — opens the next lesson
      return;
    }
    showCourse();
  }

  async function startReviewSession() {
    ui.loadSeq = (ui.loadSeq || 0) + 1;
    const seq = ui.loadSeq;
    ui.screen = "review-loading";
    const due = await loadReviews({ fetch, courseId: ui.courseId });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    log("review_opened", { courseId: ui.courseId });
    if (!due.length) { ui.continueToLessonAfterReview = false; showCourse(); return; }
    ui.reviewQueue = due.slice(1);
    const lesson = await loadLesson({ fetch, courseId: ui.courseId, lessonId: due[0] });
    if (ui.screen !== "review-loading" || ui.loadSeq !== seq) return; // navigated away
    ui.lesson = lesson;
    if (lessonFailed(ui.lesson)) { ui.continueToLessonAfterReview = false; showCourse(); return; }
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
  ui.profile = profile;
  if (profile) showHome();
  else showDiagnostic();

  // A page reload must not orphan a running generation: rejoin it and show the
  // chip. Fire-and-forget — boot never blocks on this.
  listGenerationJobs({ fetch }).then((resp) => {
    const running = (resp.jobs || []).find((j) => j.status === "running");
    if (!running || ui.genJob) return;
    ui.genJob = {
      courseId: running.courseId, lessonId: running.lessonId,
      next: 0, status: "running", elapsed: running.elapsed || 0,
    };
    paintGenChip();
    scheduleGenPoll();
  });
}
