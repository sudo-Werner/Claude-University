import { test } from "node:test";
import assert from "node:assert/strict";
import { shellHTML, feedbackBarHTML } from "../src/views/shell.js";
import { dashboardHTML } from "../src/views/dashboard.js";
import { lessonHTML, ratingLocked, suggestedQuality, expandFigureTokens } from "../src/views/lesson.js";
import { diagnosticHTML } from "../src/views/diagnostic.js";
import { curriculumHTML, lessonStatus, moduleProgress, recommendedStep } from "../src/views/curriculum.js";
import { capstoneHTML } from "../src/views/capstone.js";
import { loadingHTML, LESSON_STAGES, CAPSTONE_STAGES } from "../src/views/loading.js";
import { libraryHTML } from "../src/views/library.js";
import { syllabusHTML } from "../src/views/syllabus.js";
import { homeHTML } from "../src/views/home.js";
import { activateHTML } from "../src/views/activate.js";
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

test("lesson renders no concept chip row when concepts is absent or empty", () => {
  const absent = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(absent, /concept-row/);
  const empty = lessonHTML({ ...SAMPLE_LESSON, concepts: [] }, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(empty, /concept-row/);
});

test("lesson renders an escaped chip per concept term", () => {
  const withConcepts = { ...SAMPLE_LESSON, concepts: ["Gradient", "<script>alert(1)</script>"] };
  const html = lessonHTML(withConcepts, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /concept-row/);
  assert.match(html, /Stuck on a concept\? Tap it for a different angle\./);
  assert.match(html, /data-action="analogy-chip" data-index="0"/);
  assert.match(html, /data-action="analogy-chip" data-index="1"/);
  assert.match(html, />Gradient</);
  assert.doesNotMatch(html, /<script>alert\(1\)/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});

test("lesson disables concept chips while the workspace is pending", () => {
  const withConcepts = { ...SAMPLE_LESSON, concepts: ["Gradient"] };
  const idle = lessonHTML(withConcepts, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "" } });
  assert.doesNotMatch(idle, /data-action="analogy-chip" data-index="0" disabled/);
  const pending = lessonHTML(withConcepts, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [], pending: true, saveStatus: "" } });
  assert.match(pending, /data-action="analogy-chip" data-index="0" disabled/);
  const noWs = lessonHTML(withConcepts, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(noWs, /data-action="analogy-chip" data-index="0" disabled/);
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
    { title: "arXiv survey", url: "https://arxiv.org/abs/1404.7828", type: "preprint", note: "overview" },
  ] };
  const html = libraryHTML(lib);
  assert.match(html, /Library/);
  assert.match(html, /University/);
  assert.match(html, /Preprint \/ scholarly/);
  assert.match(html, /href="https:\/\/cs231n\.stanford\.edu\/"[^>]*target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /src-university/);
  assert.match(html, /src-preprint/);
  assert.match(html, /data-action="back"/);
});

test("libraryHTML handles an empty source list", () => {
  const html = libraryHTML({ courseId: "c", title: "X", sources: [] });
  assert.match(html, /No grounded sources/);
});

test("libraryHTML shows a 'used in your lessons' roll-up when present", () => {
  const html = libraryHTML({ courseId: "c", title: "X", sources: [],
    lessonSources: [{ title: "MIT OCW", url: "https://mit.edu/ocw", type: "university" }] });
  assert.match(html, /USED IN YOUR LESSONS/);
  assert.match(html, /MIT OCW/);
  assert.match(html, /href="https:\/\/mit\.edu\/ocw"[^>]*target="_blank"/);
});

test("lesson renders its grounded sources section", () => {
  const withSources = { ...SAMPLE_LESSON, sources: [
    { title: "Stanford CS231n", url: "https://cs231n.stanford.edu/", type: "university" }] };
  const html = lessonHTML(withSources, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /lesson-sources/);
  assert.match(html, /Stanford CS231n/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /src-university/);
  assert.match(html, /Grounded sources this lesson drew on/);
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

test("exercise shows the socratic start button only before the solution is revealed", () => {
  const before = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(before, /data-action="socratic-start"/);
  assert.match(before, /Work through it with Claude/);
  const after = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.doesNotMatch(after, /data-action="socratic-start"/);
});

test("workspace chat shows the socratic banner and Exit only when the mode is on", () => {
  const base = { answer: "", hintVisible: false, solutionRevealed: false };
  const wsOn = { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "", socratic: true };
  const on = lessonHTML(SAMPLE_LESSON, { ...base, ws: wsOn });
  assert.match(on, /Working through the exercise — Claude will guide with questions, not answers\./);
  assert.match(on, /data-action="socratic-exit"/);
  assert.ok(on.indexOf("ws-socratic") < on.indexOf("ws-thread")); // banner sits above the thread
  const off = lessonHTML(SAMPLE_LESSON, { ...base, ws: { ...wsOn, socratic: false } });
  assert.doesNotMatch(off, /ws-socratic/);
  assert.doesNotMatch(off, /data-action="socratic-exit"/);
  // A falsy flag renders byte-identically to a workspace that has never seen the mode.
  const legacy = lessonHTML(SAMPLE_LESSON, { ...base, ws: { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "" } });
  assert.equal(off, legacy);
});

test("expandFigureTokens renders a figure with caption, credit, and license link", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "Notice the valves",
    credit: "Heart diagram — Jane Doe — CC BY-SA 4.0", license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0", sourceUrl: "https://commons.wikimedia.org/x" }] };
  const { html, figuresBlock } = expandFigureTokens("<p>Intro.</p>[[figure:1]]<p>More.</p>", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig">/);
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
  assert.match(html, /loading="lazy"/);
  assert.match(html, /alt="Notice the valves"/);
  assert.match(html, /Notice the valves/);
  assert.match(html, /Heart diagram — Jane Doe — CC BY-SA 4\.0/);
  assert.match(html, /href="https:\/\/creativecommons\.org\/licenses\/by-sa\/4\.0"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, />CC BY-SA 4\.0<\/a>/);
  assert.equal(figuresBlock, "");
});

test("expandFigureTokens falls back to sourceUrl when licenseUrl is null", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "c",
    credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "https://commons.wikimedia.org/x" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /href="https:\/\/commons\.wikimedia\.org\/x"/);
});

test("expandFigureTokens escapes caption, credit, and license text (no raw HTML)", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "<script>alert(1)</script>",
    credit: '"><img src=x onerror=alert(1)>',
    license: "</a><b>x</b>", licenseUrl: "https://example.org", sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<\/a><b>/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /&quot;&gt;&lt;img/);
  assert.match(html, /&lt;\/a&gt;&lt;b&gt;x&lt;\/b&gt;/);
});

test("expandFigureTokens rejects javascript: URLs in licenseUrl and renders text only", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "c", credit: "cr", license: "CC0",
    licenseUrl: "javascript:alert(1)", sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<a[^>]*href/);  // NO <a> tag with href
  assert.match(html, /CC0/);  // license text is still there
  assert.doesNotMatch(html, /javascript:/);  // malicious URL stripped
});

test("expandFigureTokens rejects data: URLs in sourceUrl and renders text only", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "c", credit: "cr", license: "CC0",
    licenseUrl: null, sourceUrl: "data:text/html,<script>alert(1)</script>" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<a[^>]*href/);  // NO <a> tag with href
  assert.match(html, /CC0/);  // license text still rendered
  assert.doesNotMatch(html, /data:/);  // malicious URL stripped
});

test("expandFigureTokens renders normal https URLs as clickable links", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "c", credit: "cr", license: "CC BY 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by/4.0", sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<a[^>]*href="[^"]*https:\/\/creativecommons/);
  assert.match(html, /CC BY 4\.0<\/a>/);  // text inside the link
});

test("expandFigureTokens skips an entry whose filename fails the client-side regex", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "../evil.jpg",
    caption: "c", credit: "c", license: "CC0", licenseUrl: null, sourceUrl: "" }] };
  const { html, figuresBlock } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<figure/);
  assert.equal(html, "");
  assert.equal(figuresBlock, "");
});

test("expandFigureTokens strips a token with no matching images entry", () => {
  const lesson = { images: [] };
  const { html } = expandFigureTokens("<p>a</p>[[figure:1]]<p>b</p>", lesson, "demo");
  assert.equal(html, "<p>a</p><p>b</p>");
});

test("expandFigureTokens expands only the first occurrence of a duplicated token", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "c", credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "" }] };
  const { html } = expandFigureTokens("[[figure:1]]x[[figure:1]]", lesson, "demo");
  const count = (html.match(/<figure class="lesson-fig">/g) || []).length;
  assert.equal(count, 1);
});

test("expandFigureTokens renders a tokenless entry in a trailing Figures block", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg",
    caption: "Retro caption", credit: "cr", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const { html, figuresBlock } = expandFigureTokens("<p>no tokens here</p>", lesson, "demo");
  assert.equal(html, "<p>no tokens here</p>");
  assert.match(figuresBlock, /<section class="card lesson-figures">/);
  assert.match(figuresBlock, />Figures</);
  assert.match(figuresBlock, /Retro caption/);
});

test("expandFigureTokens renders nothing for an unknown figure type", () => {
  const lesson = { images: [{ n: 1, type: "carousel", code: "x", caption: "c" }] };
  const { html, figuresBlock } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.equal(html, "");
  assert.equal(figuresBlock, "");
});

// ---- drawn diagrams (slice 2): svg/mermaid arms render a placeholder, never raw code ----

test("expandFigureTokens renders an svg figure as a placeholder, never the raw code", () => {
  const lesson = { images: [{ n: 1, type: "svg", code: '<svg viewBox="0 0 800 500"><script>alert(1)</script></svg>', caption: "Pump schematic" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig lesson-fig-svg" data-fig-svg="1">/);
  assert.match(html, /Pump schematic/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<svg viewBox/); // the raw code string never appears in the template
});

test("expandFigureTokens renders a mermaid figure as a placeholder with caption", () => {
  const lesson = { images: [{ n: 1, type: "mermaid", code: "graph TD; A-->B;", caption: "Water flow" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig lesson-fig-mermaid" data-fig-mermaid="1">/);
  assert.match(html, /Water flow/);
  assert.doesNotMatch(html, /graph TD/); // raw mermaid source never appears in the template
});

test("drawn figures (svg and mermaid) carry the exact credit 'Drawn by Claude'", () => {
  const svgLesson = { images: [{ n: 1, type: "svg", code: "<svg></svg>", caption: "c" }] };
  const mermaidLesson = { images: [{ n: 1, type: "mermaid", code: "pie", caption: "c" }] };
  const { html: svgHtml } = expandFigureTokens("[[figure:1]]", svgLesson, "demo");
  const { html: mermaidHtml } = expandFigureTokens("[[figure:1]]", mermaidLesson, "demo");
  assert.match(svgHtml, /<span class="fig-credit">Drawn by Claude<\/span>/);
  assert.match(mermaidHtml, /<span class="fig-credit">Drawn by Claude<\/span>/);
});

test("expandFigureTokens escapes the caption on svg/mermaid placeholders", () => {
  const lesson = { images: [{ n: 1, type: "svg", code: "<svg></svg>", caption: "<script>alert(1)</script>" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
});

test("expandFigureTokens web-image arm is unaffected by the svg/mermaid arms (regression)", () => {
  const lesson = { images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "c",
    credit: "cred", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const { html } = expandFigureTokens("[[figure:1]]", lesson, "demo");
  assert.match(html, /<figure class="lesson-fig">/); // NOT lesson-fig-svg/lesson-fig-mermaid
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
  assert.doesNotMatch(html, /Drawn by Claude/);
});

test("expandFigureTokens with no images field leaves promptHtml untouched", () => {
  const { html, figuresBlock } = expandFigureTokens("<p>A weight <code>w</code>.</p>", SAMPLE_LESSON, "demo");
  assert.equal(html, "<p>A weight <code>w</code>.</p>");
  assert.equal(figuresBlock, "");
});

test("lesson renders an expanded figure from lesson.images at its token position", () => {
  const lesson = { ...SAMPLE_LESSON, courseId: "demo",
    promptHtml: "<p>A weight <code>w</code> has gradient.</p>[[figure:1]]",
    images: [{ n: 1, type: "web-image", file: "demo-l1-1.jpg", caption: "See the slope",
               credit: "cred", license: "CC0", licenseUrl: null, sourceUrl: "https://x" }] };
  const html = lessonHTML(lesson, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(html, /<figure class="lesson-fig">/);
  assert.match(html, /src="\/api\/courses\/demo\/images\/demo-l1-1\.jpg"/);
});

test("lesson renders SAMPLE_LESSON (no images field) unaffected by figure expansion", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(html, /lesson-fig/);
});

test("a figure token typed in a chat message is not expanded (chat stays plain esc'd text)", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false,
    ws: { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "[[figure:1]] test" }],
          pending: false, saveStatus: "" } });
  assert.match(html, /\[\[figure:1\]\] test/);
  assert.doesNotMatch(html, /<figure class="lesson-fig">/);
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

const TWO_CHECKS_LESSON = {
  ...SAMPLE_LESSON,
  checks: [
    { type: "fill", prompt: "2+2?", answer: "4", explanation: "because" },
    { type: "fill", prompt: "3+3?", answer: "6", explanation: "because" },
  ],
};

test("ratingLocked is false outside review mode", () => {
  assert.equal(ratingLocked(TWO_CHECKS_LESSON, { isReview: false, checkResults: {} }), false);
  assert.equal(ratingLocked(TWO_CHECKS_LESSON, { checkResults: {} }), false);
});

test("ratingLocked is false in review mode when the lesson has no checks", () => {
  assert.equal(ratingLocked(SAMPLE_LESSON, { isReview: true, checkResults: {} }), false);
});

test("ratingLocked is true in review mode with checks partially answered", () => {
  const state = { isReview: true, checkResults: { 0: { correct: true } } };
  assert.equal(ratingLocked(TWO_CHECKS_LESSON, state), true);
});

test("ratingLocked is false in review mode once all checks are answered", () => {
  const state = { isReview: true, checkResults: { 0: { correct: true }, 1: { correct: false } } };
  assert.equal(ratingLocked(TWO_CHECKS_LESSON, state), false);
});

test("suggestedQuality is null outside review mode", () => {
  assert.equal(suggestedQuality(TWO_CHECKS_LESSON, { isReview: false, checkResults: { 0: { correct: true } } }), null);
});

test("suggestedQuality is null in review mode before any check is answered", () => {
  assert.equal(suggestedQuality(TWO_CHECKS_LESSON, { isReview: true, checkResults: {} }), null);
});

test("suggestedQuality is again when any answered check is wrong", () => {
  const state = { isReview: true, checkResults: { 0: { correct: true }, 1: { correct: false } } };
  assert.equal(suggestedQuality(TWO_CHECKS_LESSON, state), "again");
});

test("suggestedQuality is good when all answered checks are correct", () => {
  const state = { isReview: true, checkResults: { 0: { correct: true }, 1: { correct: true } } };
  assert.equal(suggestedQuality(TWO_CHECKS_LESSON, state), "good");
});

test("lessonHTML locks the rating in review mode until checks are answered", () => {
  const locked = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true,
    checkAnswers: {}, checkResults: { 0: { correct: true } },
  });
  assert.match(locked, /Answer the checks above to rate your recall/);
  const disabledButtons = (locked.match(/class="rate-btn[^"]*" data-quality="[^"]+" disabled/g) || []).length;
  assert.equal(disabledButtons, 4);
});

test("lessonHTML unlocks the rating and suggests a quality once all checks are answered", () => {
  const unlocked = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true,
    checkAnswers: {}, checkResults: { 0: { correct: true }, 1: { correct: false } },
  });
  assert.doesNotMatch(unlocked, /Answer the checks above to rate your recall/);
  assert.doesNotMatch(unlocked, /data-quality="[^"]+" disabled/);
  assert.match(unlocked, /class="rate-btn suggested" data-quality="again"/);
});

test("lessonHTML outside review mode is unaffected by the rating gate", () => {
  const nonReview = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    checkAnswers: {}, checkResults: {},
  });
  assert.doesNotMatch(nonReview, /Answer the checks above to rate your recall/);
  assert.doesNotMatch(nonReview, /data-quality="[^"]+" disabled/);
  assert.doesNotMatch(nonReview, /rate-btn suggested/);
  assert.match(nonReview, /How well did you recall this\?/);
});

test("lessonHTML shows a pending placeholder instead of checks while fresh review items load", () => {
  const pending = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true, freshPending: true,
    checkAnswers: {}, checkResults: {},
  });
  assert.match(pending, /checks-pending/);
  assert.match(pending, /Preparing fresh review questions…/);
  assert.doesNotMatch(pending, /Check your understanding/);

  // once pending resolves (freshPending false) the checks render normally again
  const resolved = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true, freshPending: false,
    checkAnswers: {}, checkResults: {},
  });
  assert.doesNotMatch(resolved, /checks-pending/);
  assert.match(resolved, /Check your understanding/);

  // outside review mode, freshPending has no effect (placeholder never shows)
  const nonReviewPending = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, freshPending: true,
    checkAnswers: {}, checkResults: {},
  });
  assert.doesNotMatch(nonReviewPending, /checks-pending/);
});

test("lessonHTML shows the fresh-items heading once items have been swapped in (not pending)", () => {
  const html = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true, isReview: true,
    freshPending: false, freshItems: true, checkAnswers: {}, checkResults: {},
  });
  assert.match(html, /Fresh review questions/);
  assert.doesNotMatch(html, /Check your understanding/);
});

test("lessonHTML checks rendering is unaffected by fresh-item fields when absent (byte-identical)", () => {
  const withoutFields = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    checkAnswers: {}, checkResults: {},
  });
  const withFalsyFields = lessonHTML(TWO_CHECKS_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    checkAnswers: {}, checkResults: {}, isReview: false, freshPending: false, freshItems: false,
  });
  assert.equal(withoutFields, withFalsyFields);
});

const FRESH_ITEMS_LESSON = {
  ...SAMPLE_LESSON,
  checks: [
    { type: "mcq", prompt: "Which is prime?", choices: ["4", "7"], answer: 1, explanation: "7 is prime" },
    { type: "fill", prompt: "5+5?", answer: "10", explanation: "sum" },
  ],
};

test("ratingLocked and suggestedQuality work unchanged against a swapped fresh-items set", () => {
  const locked = { isReview: true, freshItems: true, checkResults: { 0: { correct: true } } };
  assert.equal(ratingLocked(FRESH_ITEMS_LESSON, locked), true);
  const unlocked = { isReview: true, freshItems: true, checkResults: { 0: { correct: true }, 1: { correct: true } } };
  assert.equal(ratingLocked(FRESH_ITEMS_LESSON, unlocked), false);
  assert.equal(suggestedQuality(FRESH_ITEMS_LESSON, unlocked), "good");
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

test("dashboard renders the course contract as level, effort, and a readable skills list", () => {
  const html = dashboardHTML(
    { topic: "T", sub: "S", durationMin: 90, progressPct: 5, lessonsDone: 1, lessonsTotal: 22, reviewsDue: 0,
      contract: { level: "Bachelor Year 1", hours: 26,
        skills: ["Explain any homeostatic loop using control-system vocabulary", "Calculate cardiac output"] } },
    { fills: [0,0,0], activePhaseIndex: 0, statusLabel: "", clock: "" },
  );
  assert.match(html, /class="level-badge">Bachelor Year 1</);
  assert.match(html, /~26 h total effort/);
  assert.match(html, /WHAT YOU'LL BE ABLE TO DO/);
  // each skill is its own list item, not run together in one chip
  assert.match(html, /<li>Explain any homeostatic loop using control-system vocabulary<\/li>/);
  assert.match(html, /<li>Calculate cardiac output<\/li>/);
  assert.doesNotMatch(html, /class="chip"/);
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

test("dashboard renders a Refine this course button", () => {
  const html = dashboardHTML(DASHBOARD_SEED, idleTimer);
  assert.match(html, /data-action="refine"/);
  assert.match(html, /Refine this course/);
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

test("syllabusHTML labels a single course, not a program", () => {
  const html = syllabusHTML(COURSE);
  assert.ok(html.includes("PROPOSED COURSE"));
  assert.ok(!html.includes("PROPOSED PROGRAM"));
});

test("syllabusHTML escapes learner-derived text", () => {
  const evil = { ...COURSE, title: "<img src=x onerror=alert(1)>" };
  assert.ok(!syllabusHTML(evil).includes("<img src=x"));
});

// ---- revisionHTML ----
import { revisionHTML } from "../src/views/revision.js";

const REVISION_COURSE = {
  title: "Intro ML", subtitle: "hands-on",
  level: { code: "bachelor-y2", label: "Bachelor Year 2-equivalent" },
  targetHours: 130, skills: [], outcomes: [], groundingSources: [],
  modules: [{ id: "m1", title: "Foundations", outcomes: [],
    lessons: [{ id: "l1", title: "Vectors", estMinutes: 90, objectives: [], prereqs: [] }] }],
};

test("revisionHTML renders the syllabus title", () => {
  const html = revisionHTML({ course: REVISION_COURSE, changeSummary: [], progressAtRisk: [] });
  assert.ok(html.includes("Intro ML"));
});

test("revisionHTML renders a changeSummary item", () => {
  const html = revisionHTML({ course: REVISION_COURSE, changeSummary: ["Added two new modules"], progressAtRisk: [] });
  assert.match(html, /Added two new modules/);
});

test("revisionHTML renders apply-revision and keep-discussing buttons", () => {
  const html = revisionHTML({ course: REVISION_COURSE, changeSummary: [], progressAtRisk: [] });
  assert.match(html, /data-action="apply-revision"/);
  assert.match(html, /data-action="keep-discussing"/);
});

test("revisionHTML suppresses the intake syllabus CTAs (no dead accept/revise buttons)", () => {
  const html = revisionHTML({ course: REVISION_COURSE, changeSummary: [], progressAtRisk: [] });
  assert.ok(!html.includes('data-action="accept-syllabus"'));
  assert.ok(!html.includes('data-action="revise-syllabus"'));
});

test("revisionHTML renders progress-at-risk callout with count when list is non-empty", () => {
  const html = revisionHTML({
    course: REVISION_COURSE,
    changeSummary: [],
    progressAtRisk: [{ title: "Vectors" }, { title: "Gradients" }],
  });
  assert.match(html, /progress-at-risk/);
  assert.match(html, /2 lesson/);
  assert.match(html, /Vectors/);
  assert.match(html, /Gradients/);
});

test("revisionHTML omits progress-at-risk callout when list is empty", () => {
  const html = revisionHTML({ course: REVISION_COURSE, changeSummary: [], progressAtRisk: [] });
  assert.doesNotMatch(html, /progress-at-risk/);
});

test("revisionHTML escapes XSS in changeSummary items (no raw <img)", () => {
  const html = revisionHTML({
    course: REVISION_COURSE,
    changeSummary: ["<img src=x onerror=alert(1)>"],
    progressAtRisk: [],
  });
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img/);
});

test("revisionHTML escapes XSS in progressAtRisk titles", () => {
  const html = revisionHTML({
    course: REVISION_COURSE,
    changeSummary: [],
    progressAtRisk: [{ title: "<script>evil()</script>" }],
  });
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test("dashboardHTML escapes model-derived topic and sub", () => {
  const html = dashboardHTML(
    { topic: "<script>x</script>", sub: "<img src=x onerror=1>", durationMin: 90,
      progressPct: 0, lessonsDone: 0, lessonsTotal: 2, reviewsDue: 0,
      masteryCounts: {}, contract: null, complete: false },
    { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" },
  );
  assert.ok(!html.includes("<script>x</script>"));
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("dashboardHTML disables Start session when the course is complete", () => {
  const data = { topic: "Course complete", sub: "T", durationMin: 90, progressPct: 100,
    lessonsDone: 2, lessonsTotal: 2, reviewsDue: 0, masteryCounts: {}, contract: null,
    complete: true };
  const tv = { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" };
  const html = dashboardHTML(data, tv);
  assert.match(html, /data-action="start-session"[^>]*disabled/);
});

test("dashboardHTML disables Review when nothing is due", () => {
  const data = { topic: "T", sub: "S", durationMin: 90, progressPct: 0, lessonsDone: 0,
    lessonsTotal: 2, reviewsDue: 0, masteryCounts: {}, contract: null, complete: false };
  const tv = { fills: [0, 0, 0], activePhaseIndex: 0, statusLabel: "", clock: "0:00" };
  const html = dashboardHTML(data, tv);
  assert.match(html, /data-action="review"[^>]*disabled/);
  const due = dashboardHTML({ ...data, reviewsDue: 3 }, tv);
  assert.ok(!/data-action="review"[^>]*disabled/.test(due));
});

test("shellHTML escapes the back label", () => {
  const html = shellHTML({ back: '<img src=x onerror=1>' });
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;img"));
});

test("syllabusHTML drops non-http(s) source URLs", () => {
  const course = { title: "T", subtitle: "", level: {}, modules: [],
    groundingSources: [
      { url: "javascript:alert(1)", title: "evil", type: "other" },
      { url: "https://ok.example/x", title: "fine", type: "university" },
    ] };
  const html = syllabusHTML(course);
  assert.ok(!html.includes("javascript:alert"));
  assert.ok(html.includes("https://ok.example/x"));
});

test("syllabusHTML renders builds-on lines from prereqs, skipping unknown ids", () => {
  const course = { ...COURSE, modules: [{ id: "m1", title: "Foundations", outcomes: [OBJ],
    lessons: [
      { id: "l1", title: "Vectors <b>", estMinutes: 90, objectives: [OBJ], prereqs: [] },
      { id: "l2", title: "Matrices", estMinutes: 90, objectives: [OBJ], prereqs: ["l1", "ghost"] },
    ] }] };
  const html = syllabusHTML(course);
  assert.ok(html.includes("Builds on: Vectors &lt;b&gt;"));     // resolved title, esc()'d
  assert.ok(!html.includes("ghost"));                            // unknown id skipped silently
});

test("syllabusHTML omits builds-on when prereqs are empty or absent", () => {
  assert.ok(!syllabusHTML(COURSE).includes("Builds on:"));       // COURSE's lesson has prereqs: []
});

test("dashboard shows the streak tile with day count", () => {
  const html = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 4 }, idleTimer);
  assert.match(html, /STREAK/);
  assert.match(html, />4</);
  assert.match(html, /days/);
});

test("dashboard streak uses singular day and a nudge at zero", () => {
  const one = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 1 }, idleTimer);
  assert.match(one, /day</);
  assert.doesNotMatch(one, /days</);
  const zero = dashboardHTML({ ...DASHBOARD_SEED, streakDays: 0 }, idleTimer);
  assert.match(zero, /Study today to start one/);
});

test("lessonHTML renders the pre-quiz stage instead of the exercise", () => {
  const lesson = { ...SAMPLE_LESSON, preQuiz: { type: "mcq", prompt: "Guess?", choices: ["A", "B"], answer: 0, explanation: "A." } };
  const html = lessonHTML(lesson, { stage: "prequiz", answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.match(html, /BEFORE YOU START/);
  assert.doesNotMatch(html, /data-field="answer"/);
  assert.doesNotMatch(html, /reveal-solution/);
});

test("lessonHTML renders the exercise when stage is main or unset", () => {
  const html = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.match(html, /data-field="answer"/);
  assert.doesNotMatch(html, /BEFORE YOU START/);
});

test("lessonHTML shows the explain-it-back card only after the solution", () => {
  const hidden = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false }, {});
  assert.doesNotMatch(hidden, /Explain it back/);
  const shown = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true }, {});
  assert.match(shown, /Explain it back/);
  assert.match(shown, /data-field="explain"/);
  assert.match(shown, /data-action="explain-grade"/);
});

test("explain card escapes the learner's text and shows the graded note raw", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    explain: { text: "<b>me</b>", grade: { verdict: "close", note: "Good <em>start</em>" } },
  }, {});
  assert.doesNotMatch(html, /<b>me<\/b>/);
  assert.match(html, /&lt;b&gt;me&lt;\/b&gt;/);
  assert.match(html, /Good <em>start<\/em>/);
  assert.match(html, /Almost there/);
});

test("explain card renders followUp question and seed button after grading", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    explain: { text: "my take", grade: { verdict: "close", note: "n", followUp: "Why <em>exactly</em>?" } },
  }, {});
  assert.ok(html.includes("Why <em>exactly</em>?"));          // server-sanitized, rendered raw
  assert.ok(html.includes('data-action="explain-chat"'));
  assert.ok(html.includes("Explore in side-chat"));
});

test("explain seed button disables after seeding", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    explain: { seeded: true, grade: { verdict: "close", note: "n", followUp: "Q?" } },
  }, {});
  assert.ok(/data-action="explain-chat"[^>]*disabled/.test(html));
  assert.ok(html.includes("Sent to side-chat"));
});

test("explain card shows no seed button without followUp", () => {
  const html = lessonHTML(SAMPLE_LESSON, {
    answer: "x", hintVisible: false, solutionRevealed: true,
    explain: { grade: { verdict: "close", note: "n" } },
  }, {});
  assert.ok(!html.includes("explain-chat"));
});

test("curriculumHTML renders exam rows with status and final row", () => {
  const manifest = { title: "T", modules: [{ id: "m1", title: "M1", lessons: [{ id: "l1", title: "L1" }] }] };
  const exams = { m1: { attempts: 2, bestScore: 0.9, passed: true } };
  const html = curriculumHTML(manifest, {}, null, exams, false);
  assert.ok(html.includes('data-exam="m1"'));
  assert.ok(html.includes("Passed — best 90%"));
  assert.ok(html.includes('data-exam="final"'));
  assert.ok(html.includes("Not taken"));
  const passedHtml = curriculumHTML(manifest, {}, null, exams, true);
  assert.ok(passedHtml.includes("Course passed"));
});

test("curriculumHTML failed exam row shows best score and attempts", () => {
  const manifest = { title: "T", modules: [{ id: "m1", title: "M1", lessons: [{ id: "l1", title: "L1" }] }] };
  const html = curriculumHTML(manifest, {}, null, { m1: { attempts: 1, bestScore: 0.62, passed: false } }, false);
  assert.ok(html.includes("62%") && html.includes("1 attempt"));
});

test("homeHTML shows passed badge on passed courses", () => {
  const courses = [{ id: "c1", title: "T", subtitle: "s", progress: { done: 1, total: 2, pct: 50 }, reviewsDue: 0, passed: true }];
  assert.ok(homeHTML(courses).includes("Passed"));
  courses[0].passed = false;
  assert.ok(!homeHTML(courses).includes("course-passed"));
});

const GATE_MANIFEST = {
  title: "T", modules: [
    { id: "m1", title: "M1", lessons: [{ id: "l1", title: "A" }] },
    { id: "m2", title: "M2", lessons: [{ id: "l2", title: "B" }] },
  ],
};

test("recommendedStep walks lessons, then module exam, then final", () => {
  assert.deepEqual(recommendedStep(GATE_MANIFEST, {}, {}), { type: "lesson", id: "l1" });
  assert.deepEqual(recommendedStep(GATE_MANIFEST, { l1: "familiar" }, {}), { type: "exam", id: "m1" });
  const exams = { m1: { passed: true }, m2: { passed: true } };
  assert.deepEqual(
    recommendedStep(GATE_MANIFEST, { l1: "familiar", l2: "familiar" }, exams),
    { type: "exam", id: "final" });
  assert.equal(
    recommendedStep(GATE_MANIFEST, { l1: "familiar", l2: "familiar" }, { ...exams, final: { passed: true } }),
    null);
});

test("curriculum locks the final until every module exam is passed", () => {
  const html = curriculumHTML(GATE_MANIFEST, {}, null, {}, false);
  assert.ok(html.includes("Locked — pass every module exam first"));
  assert.ok(!html.includes('data-exam="final"'));
  const open = curriculumHTML(GATE_MANIFEST, {}, null,
    { m1: { passed: true, bestScore: 0.9, attempts: 1 }, m2: { passed: true, bestScore: 0.9, attempts: 1 } }, false);
  assert.ok(open.includes('data-exam="final"'));
});

test("curriculum flags a module you moved beyond without passing its exam", () => {
  const html = curriculumHTML(GATE_MANIFEST, { l2: "familiar" }, null, {}, false);
  assert.ok(html.includes("Exam not passed"));
  const none = curriculumHTML(GATE_MANIFEST, { l1: "familiar" }, null, {}, false);
  assert.ok(!none.includes("Exam not passed"));
});

test("curriculum marks the recommended next step with a chip", () => {
  const html = curriculumHTML(GATE_MANIFEST, {}, null, {}, false);
  assert.ok(/data-lesson="l1"[^>]*>[\s\S]*?c-next/.test(html.split('data-lesson="l2"')[0]));
});

const CAP = { scope: "m1", title: "Mod A", intro: "i",
  items: [{ title: "A", detail: "d", source: "s" }] };

test("capstone renders a submit-your-work card with busy and disabled states", () => {
  const empty = capstoneHTML(CAP, { work: "", busy: false, result: null });
  assert.match(empty, /data-field="cap-work"/);
  assert.match(empty, /data-action="cap-submit"[^>]*disabled/);
  const ready = capstoneHTML(CAP, { work: "my project", busy: false, result: null });
  assert.doesNotMatch(ready, /data-action="cap-submit"[^>]*disabled/);
  assert.ok(ready.includes("my project"));                            // textarea keeps the draft
  const busy = capstoneHTML(CAP, { work: "my project", busy: true, result: null });
  assert.ok(busy.includes("Grading…"));
  assert.match(busy, /data-action="cap-submit"[^>]*disabled/);
});

test("capstone renders the graded result: badges, raw notes, escaped evidence", () => {
  const result = {
    score: 0.625, passed: false, attempt: 1, summary: "Solid <em>start</em>",
    rubric: [{ criterion: "Uses &lt;b&gt;real&lt;/b&gt; data" }, { criterion: "C1" },
             { criterion: "C2" }, { criterion: "C3" }],
    perCriterion: [
      { index: 0, met: "met", note: "Good <em>use</em>", evidence: "I <scraped> the data" },
      { index: 1, met: "partial", note: "n", evidence: "" },
      { index: 2, met: "unmet", note: "n", evidence: "" },
      { index: 3, met: "partial", note: "n", evidence: "" },
    ],
  };
  const html = capstoneHTML(CAP, { work: "w", busy: false, result });
  assert.ok(html.includes("Uses &lt;b&gt;real&lt;/b&gt; data"));      // criterion raw (pre-escaped server-side)
  assert.ok(html.includes("Good <em>use</em>"));                       // note raw (server-sanitized)
  assert.ok(html.includes("I &lt;scraped&gt; the data"));              // evidence esc()'d
  assert.ok(html.includes("Not passed — 63% (70% needed)"));
  assert.ok(html.includes("Solid <em>start</em>"));                    // summary raw
  assert.ok(html.includes("Partially met") && html.includes("Not met") && html.includes("Met"));
  assert.ok(html.includes("Submit again"));                            // same textarea stays
  const passed = capstoneHTML(CAP, { work: "w", busy: false,
    result: { ...result, score: 0.75, passed: true } });
  assert.ok(passed.includes("Passed — 75%"));
});

test("capstone submit errors render softly and keep the card usable", () => {
  const html = capstoneHTML(CAP, { work: "w", busy: false, result: { error: "boom <x>" } });
  assert.ok(html.includes("boom &lt;x&gt;"));
  assert.doesNotMatch(html, /data-action="cap-submit"[^>]*disabled/);
});

test("activateHTML escapes the title and shows the prior-knowledge question", () => {
  const html = activateHTML("<script>alert(1)</script> Recursion");
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /BEFORE YOU START/);
  assert.match(html, /What do you already know — or suspect — about this topic\?/);
  assert.match(html, /A sentence or two is plenty\. The lesson will build on your answer\./);
  assert.match(html, /maxlength="2000"/);
  assert.match(html, /data-field="pk-text"/);
  assert.match(html, /data-action="pk-start"/);
  assert.match(html, /data-action="pk-skip"/);
  assert.match(html, />Start lesson</);
  assert.match(html, />Skip</);
});

test("exercise shows the Teach it to Claude button only after the solution is revealed", () => {
  const before = lessonHTML(SAMPLE_LESSON, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.doesNotMatch(before, /data-action="teach-start"/);
  const after = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true });
  assert.match(after, /data-action="teach-start"/);
  assert.match(after, /Teach it to Claude/);
});

test("workspace chat shows the teaching banner and Grade button only when ws.teaching is on", () => {
  const base = { answer: "x", hintVisible: false, solutionRevealed: true };
  const wsOn = { open: true, tab: "chat", notes: "",
    chat: [{ role: "assistant", content: "opener" }, { role: "user", content: "teaching turn" }],
    pending: false, saveStatus: "", teaching: true, teachStart: 1 };
  const on = lessonHTML(SAMPLE_LESSON, { ...base, ws: wsOn });
  assert.match(on, /You're the teacher — Claude is your student\./);
  assert.match(on, /data-action="teach-exit"/);
  assert.match(on, /data-action="teach-grade"/);
  assert.ok(on.indexOf("ws-socratic") < on.indexOf("ws-thread")); // banner sits above the thread
  const off = lessonHTML(SAMPLE_LESSON, { ...base, ws: { ...wsOn, teaching: false } });
  assert.doesNotMatch(off, /data-action="teach-exit"/);
  assert.doesNotMatch(off, /data-action="teach-grade"/);
});

test("Grade my teaching button is disabled while pending, grading, or before any teacher turn", () => {
  const base = { answer: "x", hintVisible: false, solutionRevealed: true };
  const noTeacherTurn = { open: true, tab: "chat", notes: "",
    chat: [{ role: "assistant", content: "opener" }], pending: false, saveStatus: "",
    teaching: true, teachStart: 1 };
  const htmlNoTurn = lessonHTML(SAMPLE_LESSON, { ...base, ws: noTeacherTurn });
  assert.match(htmlNoTurn, /data-action="teach-grade"[^>]*disabled/);

  const withTurn = { ...noTeacherTurn, chat: [...noTeacherTurn.chat, { role: "user", content: "here's my explanation" }] };
  const htmlReady = lessonHTML(SAMPLE_LESSON, { ...base, ws: withTurn });
  assert.doesNotMatch(htmlReady, /data-action="teach-grade"[^>]*disabled/);

  const htmlPending = lessonHTML(SAMPLE_LESSON, { ...base, ws: { ...withTurn, pending: true } });
  assert.match(htmlPending, /data-action="teach-grade"[^>]*disabled/);

  const htmlGrading = lessonHTML(SAMPLE_LESSON, { ...base, ws: { ...withTurn, grading: true } });
  assert.match(htmlGrading, /data-action="teach-grade"[^>]*disabled/);
});

test("workspace compose is disabled while grading a teaching episode", () => {
  const ws = { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "x" }],
              pending: false, saveStatus: "", teaching: true, teachStart: 0, grading: true };
  const html = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true, ws });
  assert.match(html, /data-field="ws-chat"[^>]*disabled/);
  assert.match(html, /data-action="ws-send"[^>]*disabled/);
  assert.match(html, /grade-loading/);
  assert.match(html, /Checking your teaching…/);
});

test("teaching verdict block renders from ws.teachGrade after the session ends", () => {
  const ws = { open: true, tab: "chat", notes: "", chat: [], pending: false, saveStatus: "",
              teaching: false, teachGrade: { verdict: "close", note: "Good <em>attempt</em>, but explain X." } };
  const html = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true, ws });
  assert.match(html, /Almost there/);          // GRADE_LABEL.close
  assert.match(html, /Good <em>attempt<\/em>, but explain X\./); // server-sanitized, rendered raw
  assert.doesNotMatch(html, /data-action="teach-exit"/); // session already ended
});

test("teaching grade error paints via grade-soft and keeps the session alive", () => {
  const ws = { open: true, tab: "chat", notes: "", chat: [{ role: "user", content: "x" }],
              pending: false, saveStatus: "", teaching: true, teachStart: 0,
              teachGrade: { error: "Couldn't grade your teaching right now." } };
  const html = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true, ws });
  assert.match(html, /grade-soft/);
  assert.match(html, /Couldn't grade your teaching right now\./);
  assert.match(html, /data-action="teach-exit"/); // still teaching
});

test("teaching chat messages are escaped like any other workspace message", () => {
  const ws = { open: true, tab: "chat", notes: "",
              chat: [{ role: "user", content: "<script>alert(1)</script>" }],
              pending: false, saveStatus: "", teaching: true, teachStart: 0 };
  const html = lessonHTML(SAMPLE_LESSON, { answer: "x", hintVisible: false, solutionRevealed: true, ws });
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});

test("shell renders the global feedback toggle and slot", () => {
  const html = shellHTML({});
  assert.match(html, /data-action="feedback-toggle"/);
  assert.match(html, /Feedback/);
  assert.match(html, /data-fb-slot/);
});

test("feedback bar is empty when closed and shows the composer when open", () => {
  assert.equal(feedbackBarHTML(null), "");
  assert.equal(feedbackBarHTML({ open: false, text: "kept" }), "");
  const open = feedbackBarHTML({ open: true, text: "", sending: false, notice: "" });
  assert.match(open, /data-field="fb-text"/);
  assert.match(open, /Ideas, annoyances, requests — straight to the build loop\./);
  assert.match(open, /<button class="fb-send" data-action="feedback-send" disabled/);
});

test("feedback bar enables Send with text and disables while sending", () => {
  const ready = feedbackBarHTML({ open: true, text: "add dark mode", sending: false, notice: "" });
  assert.match(ready, /<button class="fb-send" data-action="feedback-send" >Send<\/button>/);
  const sending = feedbackBarHTML({ open: true, text: "add dark mode", sending: true, notice: "" });
  assert.match(sending, /Sending…/);
  assert.match(sending, /data-field="fb-text"[^>]*disabled/s);
  assert.match(sending, /<button class="fb-send" data-action="feedback-send" disabled/);
});

test("feedback bar escapes typed text on repaint", () => {
  const html = feedbackBarHTML({ open: true, text: '<script>alert(1)</script>"', sending: false, notice: "" });
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;&quot;/);
});

test("feedback bar renders the sent and error notices with exact copy", () => {
  const sent = feedbackBarHTML({ open: true, text: "", sending: false, notice: "sent" });
  assert.match(sent, /Thanks — noted\./);
  assert.doesNotMatch(sent, /data-field="fb-text"/);
  const err = feedbackBarHTML({ open: true, text: "my note", sending: false, notice: "error" });
  assert.match(err, /Couldn't send — try again\./);
  assert.match(err, /value="my note"/);
});

test("video sources render the Video badge in lesson and library views", () => {
  const lesson = { ...SAMPLE_LESSON, sources: [
    { title: "Amoeba Sisters: Enzymes", url: "https://www.youtube.com/watch?v=abc", type: "video", note: "Visual walkthrough" },
  ] };
  const lessonView = lessonHTML(lesson, { answer: "", hintVisible: false, solutionRevealed: false });
  assert.match(lessonView, /src-badge src-video/);
  assert.match(lessonView, />Video</);

  const lib = libraryHTML({ intro: "i", sources: [
    { title: "Amoeba Sisters: Enzymes", url: "https://www.youtube.com/watch?v=abc", type: "video", note: "Visual walkthrough" },
  ] });
  assert.match(lib, /src-badge src-video/);
  assert.match(lib, />Video</);
  assert.match(lib, /rel="noopener noreferrer"/);
});
