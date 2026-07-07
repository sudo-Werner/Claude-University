import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML } from "../src/views/shell.js";
import { dashboardHTML } from "../src/views/dashboard.js";
import { lessonHTML } from "../src/views/lesson.js";
import { diagnosticHTML } from "../src/views/diagnostic.js";
import { curriculumHTML, lessonStatus, moduleProgress } from "../src/views/curriculum.js";
import { capstoneHTML } from "../src/views/capstone.js";
import { loadingHTML, LESSON_STAGES, CAPSTONE_STAGES } from "../src/views/loading.js";
import { libraryHTML } from "../src/views/library.js";
import { syllabusHTML } from "../src/views/syllabus.js";
const DASHBOARD_SEED = {
  topic: "Backpropagation, intuitively",
  sub: "Module 3 · Neural Networks · Lesson 2",
  durationMin: 90, progressPct: 30, lessonsDone: 12, lessonsTotal: 40,
  reviewsDue: 8,
};
const SAMPLE_LESSON = {
  step: 4, totalSteps: 5, topic: "Backpropagation", eyebrow: "EXERCISE",
  promptHtml: "A weight <code>w</code> has gradient <code>∂L/∂w = 0.4</code>.",
  hintHtml: "Gradient descent moves <em>against</em> the gradient.",
  solutionAns: "w ← w − 0.04",
  solutionNote: "A small move downhill on the loss.",
};

const idleTimer = {
  fills: [0, 0, 0],
  activePhaseIndex: 0,
  statusLabel: "<b>Warm-up</b> in progress",
  clock: "0:00 / 90:00",
};

test("shell shows back control only when given", () => {
  const home = shellHTML({});
  assert.match(home, /id="view"/);
  assert.doesNotMatch(home, /data-action="nav-back"/);
  assert.doesNotMatch(home, /streak/i);

  const inCourse = shellHTML({ back: "Courses" });
  assert.match(inCourse, /data-action="nav-back"/);
  assert.match(inCourse, /Courses/);
});

test("dashboard renders the seeded session and stats", () => {
  const html = dashboardHTML(DASHBOARD_SEED, idleTimer);
  assert.match(html, /Backpropagation, intuitively/);
  assert.match(html, /TODAY'S SESSION/);
  assert.match(html, /Warm-up/);
  assert.match(html, /Peak focus/);
  assert.match(html, /Cool-down/);
  assert.match(html, /30<\/span>/); // progress number
  assert.match(html, /12 of 40 lessons/);
  assert.match(html, />8<\/span>/); // reviews due
  assert.match(html, /data-action="start-session"/);
});

test("lesson locks the solution with an empty answer", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /class="reveal locked"/);
  assert.doesNotMatch(html, /class="solution"/); // panel hidden
  assert.doesNotMatch(html, /<div class="hint"/); // hint panel hidden (not the toggle)
  assert.match(html, /data-field="answer"/);
});

test("lesson makes the solution revealable once answered", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: false, solutionRevealed: false });
  assert.match(html, /class="reveal ready"/);
});

test("lesson shows the solution panel once revealed", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: true, solutionRevealed: true });
  assert.match(html, /class="reveal shown"/);
  assert.match(html, /class="solution"/);
  assert.match(html, /w − 0.04/);
  assert.match(html, /<div class="hint"/); // hint panel visible
});

test("lesson enables Check my answer once there is an answer", () => {
  const empty = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(empty, /data-action="check-answer"[^>]*disabled/);
  const answered = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: false, solutionRevealed: false });
  assert.match(answered, /data-action="check-answer"(?![^>]*disabled)/);
});

test("grading works independently of revealing the solution", () => {
  // The grade banner appears from grading state alone — no reveal required.
  const html = lessonHTML(SAMPLE_LESSON, { answer: "w - 0.04", hintVisible: false, solutionRevealed: false, grading: true });
  assert.match(html, /grade-loading/);
  assert.match(html, /Checking your answer/);
  assert.doesNotMatch(html, /class="solution"/); // solution still hidden
});

test("lesson renders the verdict banner once graded", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "w - 0.04", hintVisible: false, solutionRevealed: false,
    grade: { verdict: "close", note: "Right idea; mind the sign." },
  });
  assert.match(html, /grade-close/);
  assert.match(html, /Almost there/);
  assert.match(html, /mind the sign/);
  assert.match(html, />Check again</); // button invites a re-check
});

test("lesson grade banner escapes an error message (no raw HTML)", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: false,
    grade: { error: "<img src=x onerror=alert(1)>" },
  });
  assert.match(html, /grade-soft/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img/);
});

test("lesson offers an Explain more deeply button", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /data-action="deepen-lesson"/);
  assert.match(html, /Explain it more deeply/);
});

test("lesson shows a soft error if deepening failed", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false, deepenError: "Couldn't rewrite this lesson right now." });
  assert.match(html, /grade-soft/);
  assert.match(html, /Couldn't rewrite this lesson/);
});

test("lesson shows no grade banner before checking", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(html, /class="grade /);
});

test("loadingHTML renders a skeleton and the first status message", () => {
  const html = loadingHTML("lesson", LESSON_STAGES[0]);
  assert.match(html, /skeleton/);
  assert.match(html, /class="sk /);                 // shimmer blocks present
  assert.match(html, /load-msg/);
  assert.match(html, /Reading the topic/);          // first staged message
  assert.ok(LESSON_STAGES.length >= 3 && CAPSTONE_STAGES.length >= 3);
});

test("libraryHTML groups sources by type with badges and real links", () => {
  const lib = { courseId: "c", title: "Intro ML", sources: [
    { title: "Stanford CS231n", url: "https://cs231n.stanford.edu/", type: "university", note: "course notes" },
    { title: "arXiv survey", url: "https://arxiv.org/abs/1404.7828", type: "peer-reviewed", note: "overview" },
  ] };
  const html = libraryHTML(lib);
  assert.match(html, /Library/);
  assert.match(html, /University/);
  assert.match(html, /Peer-reviewed/);
  assert.match(html, /href="https:\/\/cs231n\.stanford\.edu\/"[^>]*target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /src-university/);
  assert.match(html, /data-action="back"/);
});

test("libraryHTML handles an empty source list", () => {
  const html = libraryHTML({ courseId: "c", title: "X", sources: [] });
  assert.match(html, /No accredited sources/);
});

test("libraryHTML shows a 'used in your lessons' roll-up when present", () => {
  const html = libraryHTML({ courseId: "c", title: "X", sources: [],
    lessonSources: [{ title: "MIT OCW", url: "https://mit.edu/ocw", type: "university" }] });
  assert.match(html, /USED IN YOUR LESSONS/);
  assert.match(html, /MIT OCW/);
  assert.match(html, /href="https:\/\/mit\.edu\/ocw"[^>]*target="_blank"/);
});

test("lesson renders its accredited sources section", () => {
  const withSources = { ...SAMPLE_LESSON, sources: [
    { title: "Stanford CS231n", url: "https://cs231n.stanford.edu/", type: "university" }] };
  const html = lessonHTML(withSources, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /lesson-sources/);
  assert.match(html, /Stanford CS231n/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /src-university/);
});

test("lesson omits the sources section when there are none", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(html, /lesson-sources/);
});

test("lesson shows a collapsed workspace toggle by default", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /data-action="ws-toggle"/);
  assert.match(html, /Notes/);
  assert.doesNotMatch(html, /data-field="ws-notes"/); // collapsed: no textarea yet
});

test("open workspace shows notes textarea with escaped value", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "notes", notes: "<b>hi</b>", chat: [], pending: false, saveStatus: "saved" } });
  assert.match(html, /data-field="ws-notes"/);
  assert.match(html, /&lt;b&gt;hi&lt;\/b&gt;/); // value escaped
  assert.match(html, /saved/);
});

test("open workspace chat tab escapes message content", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "<script>x</script>" }], pending: false, saveStatus: "" } });
  assert.match(html, /data-action="ws-send"/);
  assert.doesNotMatch(html, /<script>x/);
  assert.match(html, /&lt;script&gt;x&lt;\/script&gt;/);
});

test("diagnostic renders all six questions and gates Continue", () => {
  const none = diagnosticHTML({});
  assert.equal((none.match(/data-q="/g) || []).length >= 6, true);
  assert.match(none, /data-action="finish-diagnostic"[^>]*disabled/);
});

test("diagnostic enables Continue once all answered and marks selections", () => {
  const all = diagnosticHTML({
    contentOrder: "theory_first",
    stuckStrategy: "push",
    wrongAnswerFeedback: "hint",
    sessionStyle: "deep_block",
    lessonStructure: "top_down",
    analogies: true,
  });
  assert.doesNotMatch(all, /data-action="finish-diagnostic"[^>]*disabled/);
  assert.match(all, /class="opt selected"/);
});

test("lesson shows the recall rating once the solution is revealed", () => {
  const revealed = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.match(revealed, /data-quality="again"/);
  assert.match(revealed, /data-quality="hard"/);
  assert.match(revealed, /data-quality="good"/);
  assert.match(revealed, /data-quality="easy"/);
  assert.match(revealed, /recall/i);

  const notYet = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(notYet, /data-quality=/);
});

test("lesson renders the checks section once the solution is revealed", () => {
  const withChecks = {
    ...SAMPLE_LESSON,
    checks: [{ type: "fill", prompt: "2+2?", answer: "4", explanation: "because" }],
  };
  const revealed = lessonHTML(withChecks, { answer: "x", hintVisible: false, solutionRevealed: true, checkAnswers: {}, checkResults: {} });
  assert.match(revealed, /Check your understanding/);
  assert.match(revealed, /data-check-input="0"/);

  const notYet = lessonHTML(withChecks, { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} });
  assert.doesNotMatch(notYet, /Check your understanding/);
});

test("dashboard shows a mastery breakdown when there is mastery data", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 50, lessonsDone: 2,
      lessonsTotal: 4, reviewsDue: 0,
      masteryCounts: { attempted: 1, familiar: 0, proficient: 1, mastered: 0 } },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" },
  );
  assert.match(html, /Mastery/);
  assert.match(html, /Proficient/i);
});

test("dashboard omits the mastery breakdown when all counts are zero", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 4, reviewsDue: 0,
      masteryCounts: { attempted: 0, familiar: 0, proficient: 0, mastered: 0 } },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" },
  );
  assert.doesNotMatch(html, /class="mastery"/);
});

const SAMPLE_MANIFEST = {
  id: "demo", title: "Demo Course", subtitle: "s",
  modules: [
    { id: "m1", title: "Basics", lessons: [
      { id: "demo-l1", title: "Lesson One" }, { id: "demo-l2", title: "Lesson Two" } ] },
    { id: "m2", title: "Advanced", lessons: [ { id: "demo-l3", title: "Lesson Three" } ] },
  ],
};
const SAMPLE_MASTERY = { "demo-l1": "proficient" };  // l1 done, rest not

test("lessonStatus reflects done / current / todo", () => {
  assert.equal(lessonStatus("demo-l1", SAMPLE_MASTERY, "demo-l2"), "done");
  assert.equal(lessonStatus("demo-l2", SAMPLE_MASTERY, "demo-l2"), "current");
  assert.equal(lessonStatus("demo-l3", SAMPLE_MASTERY, "demo-l2"), "todo");
});

test("moduleProgress counts completed lessons in a module", () => {
  assert.deepEqual(moduleProgress(SAMPLE_MANIFEST.modules[0], SAMPLE_MASTERY), { done: 1, total: 2 });
  assert.deepEqual(moduleProgress(SAMPLE_MANIFEST.modules[1], SAMPLE_MASTERY), { done: 0, total: 1 });
});

test("curriculumHTML renders modules, lessons, progress, badge and hooks", () => {
  const html = curriculumHTML(SAMPLE_MANIFEST, SAMPLE_MASTERY, "demo-l2");
  assert.match(html, /Basics/);
  assert.match(html, /Advanced/);
  assert.match(html, /Lesson One/);
  assert.match(html, /data-lesson="demo-l1"/);
  assert.match(html, /data-lesson="demo-l3"/);
  assert.match(html, /1\/2/);            // module-one progress
  assert.match(html, /Proficient/);      // badge for the completed lesson
  assert.match(html, /1 of 3 lessons/);  // overall header
});

test("curriculumHTML tolerates missing mastery", () => {
  const html = curriculumHTML(SAMPLE_MANIFEST, undefined, null);
  assert.match(html, /0 of 3 lessons/);
  assert.match(html, /data-lesson="demo-l1"/);
});

test("curriculum offers a capstone only for completed modules", () => {
  // partial mastery: no module complete -> no capstone affordance at all
  assert.doesNotMatch(curriculumHTML(SAMPLE_MANIFEST, SAMPLE_MASTERY, "demo-l2"), /data-capstone/);
  // module m1 fully done, m2 not -> m1 capstone shown, m2 not, no course capstone
  const partial = { "demo-l1": "mastered", "demo-l2": "proficient" };
  const html = curriculumHTML(SAMPLE_MANIFEST, partial, "demo-l3");
  assert.match(html, /data-capstone="m1"/);
  assert.doesNotMatch(html, /data-capstone="m2"/);
  assert.doesNotMatch(html, /data-capstone="course"/);
});

test("curriculum offers the course capstone once everything is done", () => {
  const all = { "demo-l1": "mastered", "demo-l2": "mastered", "demo-l3": "mastered" };
  const html = curriculumHTML(SAMPLE_MANIFEST, all, null);
  assert.match(html, /data-capstone="m1"/);
  assert.match(html, /data-capstone="m2"/);
  assert.match(html, /data-capstone="course"/);
});

test("capstoneHTML renders intro, items, and a search-based explore link", () => {
  const cap = {
    scope: "m1", title: "Basics", intro: "Here is where it shows up.",
    items: [
      { title: "AlphaFold", detail: "It predicts protein structures.", source: "DeepMind" },
      { title: "GPS", detail: "Relies on it.", source: "Wikipedia" },
    ],
  };
  const html = capstoneHTML(cap);
  assert.match(html, /Real-world connections/);
  assert.match(html, /AlphaFold/);
  assert.match(html, /predicts protein structures/);
  assert.match(html, /DeepMind/);
  // explore link is a constructed web search (never a model-supplied URL)
  assert.match(html, /href="https:\/\/duckduckgo\.com\/\?q=/);
  assert.match(html, /AlphaFold%20DeepMind/);
  assert.match(html, /data-action="back"/);
});

test("capstone explore link decodes HTML entities before encoding the query", () => {
  // server escapes "AT&T" -> "AT&amp;T"; the search query must be the real text.
  const cap = { scope: "m1", title: "T", intro: "i",
    items: [{ title: "AT&amp;T", detail: "uses it", source: "Wikipedia" }] };
  const html = capstoneHTML(cap);
  assert.match(html, /q=AT%26T%20Wikipedia/);   // & encoded once, not &amp;
  assert.doesNotMatch(html, /amp%3B/);          // no leftover entity in the query
});

test("shell no longer renders a streak pill", () => {
  const html = shellHTML({ back: "Courses" });
  assert.doesNotMatch(html, /streak/i);
});

test("dashboard no longer renders a streak strip", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
      lessonsTotal: 2, reviewsDue: 0, masteryCounts: {} },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" });
  assert.doesNotMatch(html, /streak/i);
});

test("lessonHTML renders player nav with Prev/Next enabled per nav flags", () => {
  // reuse the file's existing SAMPLE_LESSON + a minimal state with solutionRevealed:false
  const state = { answer: "", hintVisible: false, solutionRevealed: false, checkAnswers: {}, checkResults: {} };
  const mid = lessonHTML(SAMPLE_LESSON, state, { hasPrev: true, hasNext: true });
  assert.match(mid, /data-action="curriculum"/);
  assert.match(mid, /data-action="prev-lesson"/);
  assert.match(mid, /data-action="next-lesson"/);
  assert.doesNotMatch(mid, /data-action="prev-lesson"[^>]*disabled/);

  const first = lessonHTML(SAMPLE_LESSON, state, { hasPrev: false, hasNext: true });
  assert.match(first, /data-action="prev-lesson"[^>]*disabled/);
});

const OBJ = { text: "Calculate the gradient", bloom: "apply", knowledge: "procedural" };
const COURSE = {
  title: "Intro ML", subtitle: "hands-on",
  level: { code: "bachelor-y2", label: "Bachelor Year 2-equivalent" },
  targetHours: 130, skills: ["train a model", "evaluate a model"],
  outcomes: [{ text: "Compare two models", bloom: "analyze", knowledge: "conceptual" }],
  groundingSources: [{ title: "MIT 6.036", url: "https://mit.edu/6036", type: "university" }],
  modules: [{ id: "m1", title: "Foundations", outcomes: [OBJ],
    lessons: [{ id: "l1", title: "Vectors", estMinutes: 90, objectives: [OBJ], prereqs: [] }] }],
};

test("syllabusHTML renders level, hours, skills, objectives, and sources", () => {
  const html = syllabusHTML(COURSE);
  assert.ok(html.includes("Bachelor Year 2-equivalent"));
  assert.ok(html.includes("130"));                          // estimated total effort
  assert.ok(html.includes("train a model"));
  assert.ok(html.includes("Calculate the gradient"));       // a lesson objective
  assert.ok(html.includes("MIT 6.036"));
  assert.ok(html.includes('data-action="accept-syllabus"'));
  assert.ok(html.includes('data-action="revise-syllabus"'));
});

test("syllabusHTML escapes learner-derived text", () => {
  const evil = { ...COURSE, title: "<img src=x onerror=alert(1)>" };
  assert.ok(!syllabusHTML(evil).includes("<img src=x"));
});
