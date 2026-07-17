import test from "node:test";
import assert from "node:assert/strict";
import {
  arcadeHTML, arcadeGeneratingHTML, arcadeLockedHTML, arcadeTimeoutHTML,
  hostIntroHTML, questionHTML, gradeChoice, matchBoardHTML,
  matchUpInit, matchUpSelectLeft, matchUpSelectRight, matchUpComplete, matchUpScore,
  arcadeResultHTML, quizChatHTML,
} from "../src/views/arcade.js";

// ---- arcadeHTML: course cards ----

test("arcadeHTML shows a locked card for a course with zero completed lessons", () => {
  const courses = [{ id: "c1", title: "Course <One>", progress: { done: 0, total: 5, pct: 0 } }];
  const html = arcadeHTML(courses, {});
  assert.ok(html.includes("Course &lt;One&gt;"));
  assert.ok(html.toLowerCase().includes("finish your first lesson to unlock"));
  assert.ok(!html.includes("data-arcade-play"));
});

test("arcadeHTML shows stats and a Play button for an unlocked course", () => {
  const courses = [{ id: "c1", title: "Course One", progress: { done: 3, total: 5, pct: 60 } }];
  const stats = { c1: { roundsPlayed: 4, bestPct: 88, streakDays: 2,
    perFormat: { rapid_fire: { plays: 4, bestPct: 88 } },
    history: [{ date: "2026-07-15", format: "rapid_fire", score: 7, total: 8 }] } };
  const html = arcadeHTML(courses, stats);
  assert.ok(html.includes('data-arcade-play="c1"'));
  assert.ok(html.includes("<b>4</b> rounds"));
  assert.ok(html.includes("88%"));
  assert.ok(html.includes("<b>2</b> day streak"));
  assert.ok(html.includes("Rapid fire"));
  assert.ok(html.includes("2026-07-15"));
});

test("arcadeHTML falls back to zeroed stats when none loaded yet for an unlocked course", () => {
  const courses = [{ id: "c1", title: "Course One", progress: { done: 1, total: 5, pct: 20 } }];
  const html = arcadeHTML(courses, {});
  assert.ok(html.includes('data-arcade-play="c1"'));
  assert.ok(html.includes("<b>0</b> rounds"));
});

// ---- loading / locked / timeout states ----

test("arcadeLockedHTML shows the unlock copy from the spec", () => {
  assert.ok(arcadeLockedHTML().toLowerCase().includes("finish your first lesson to unlock"));
});

test("arcadeGeneratingHTML renders a themed loading card", () => {
  assert.ok(arcadeGeneratingHTML().includes("load-status"));
});

test("arcadeTimeoutHTML offers a retry action", () => {
  assert.ok(arcadeTimeoutHTML().includes('data-action="arcade-retry"'));
});

// ---- host intro ----

test("hostIntroHTML escapes title and host_intro and offers Start", () => {
  const round = { format: "rapid_fire", title: "<b>Hi</b>", host_intro: "<i>Go</i>" };
  const html = hostIntroHTML(round);
  assert.ok(html.includes("&lt;b&gt;Hi&lt;/b&gt;"));
  assert.ok(html.includes("&lt;i&gt;Go&lt;/i&gt;"));
  assert.ok(html.includes('data-action="arcade-begin"'));
});

// ---- single-question formats + grading ----

test("questionHTML renders rapid_fire choices and escapes an XSS prompt", () => {
  const round = { format: "rapid_fire", questions: [
    { lesson_id: "l1", prompt: "<script>alert(1)</script>", choices: ["<b>a</b>", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const html = questionHTML(round, 0, { answered: false, selected: null });
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<b>a</b>"));
  assert.ok(html.includes("&lt;b&gt;a&lt;/b&gt;"));
});

test("questionHTML shows correct/wrong choice classes once answered", () => {
  const round = { format: "rapid_fire", questions: [
    { lesson_id: "l1", prompt: "P", choices: ["a", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const html = questionHTML(round, 0, { answered: true, selected: 2 });
  // class="..." renders BEFORE data-arcade-choice="..." in the button tag.
  assert.ok(/class="choice correct"[^>]*data-arcade-choice="1"/.test(html));
  assert.ok(/class="choice wrong"[^>]*data-arcade-choice="2"/.test(html));
});

test("questionHTML true_false maps the boolean answer to a 0/1 correct index", () => {
  const round = { format: "true_false", questions: [
    { lesson_id: "l1", statement: "S", answer: false, reveal: "R" },
  ] };
  const html = questionHTML(round, 0, { answered: true, selected: 0 });
  // False (index 1) is correct; class renders before data-arcade-choice.
  assert.ok(/class="choice correct"[^>]*data-arcade-choice="1"/.test(html));
  assert.ok(/class="choice wrong"[^>]*data-arcade-choice="0"/.test(html));
});

test("questionHTML odd_one_out and spot_the_lie render their item/statement lists", () => {
  const ooo = { format: "odd_one_out", questions: [
    { lesson_id: "l1", items: ["a", "b", "c", "d"], answer: 2, reveal: "R" },
  ] };
  const oooHtml = questionHTML(ooo, 0, { answered: false });
  assert.ok(oooHtml.includes("Which one doesn't belong?"));
  assert.ok(oooHtml.includes('data-arcade-choice="3"'));

  const stl = { format: "spot_the_lie", questions: [
    { lesson_id: "l1", statements: ["a", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const stlHtml = questionHTML(stl, 0, { answered: false });
  assert.ok(stlHtml.includes("Which statement is the lie?"));
});

test("gradeChoice grades rapid_fire/odd_one_out/spot_the_lie by index and true_false by boolean", () => {
  const rf = { format: "rapid_fire", questions: [{ answer: 2 }] };
  assert.equal(gradeChoice(rf, 0, 2), true);
  assert.equal(gradeChoice(rf, 0, 1), false);

  const tf = { format: "true_false", questions: [{ answer: true }] };
  assert.equal(gradeChoice(tf, 0, 0), true);  // index 0 = "True"
  assert.equal(gradeChoice(tf, 0, 1), false);
});

test("gradeChoice: no selection (timeout) always grades as a miss, even at index 0", () => {
  const rf = { format: "rapid_fire", questions: [{ answer: 0 }] };
  assert.equal(gradeChoice(rf, 0, null), false);
  assert.equal(gradeChoice(rf, 0, undefined), false);
});

// ---- match_up: pure interaction state + scoring ----

test("matchUpInit sets up unmatched state with the injected shuffle order", () => {
  const board = { lesson_id: "l1", pairs: [
    { left: "A", right: "1" }, { left: "B", right: "2" }, { left: "C", right: "3" },
    { left: "D", right: "4" }, { left: "E", right: "5" },
  ], reveal: "r" };
  const state = matchUpInit(board, (arr) => arr);
  assert.deepEqual(state.rightOrder, [0, 1, 2, 3, 4]);
  assert.deepEqual(state.matched, {});
  assert.equal(state.leftSelected, null);
});

test("matchUpSelectRight marks a correct pair matched and an incorrect one as a wrong attempt", () => {
  const board = { lesson_id: "l1", pairs: [{ left: "A", right: "1" }, { left: "B", right: "2" }], reveal: "r" };
  let state = matchUpInit(board, (arr) => arr);
  state = matchUpSelectLeft(state, 0);
  state = matchUpSelectRight(state, board, 1); // wrong: A pairs with index 0, not 1
  assert.equal(state.correct, false);
  assert.equal(state.wrongAttempts[0], 1);
  assert.equal(state.matched[0], undefined);

  state = matchUpSelectLeft(state, 0);
  state = matchUpSelectRight(state, board, 0); // correct now
  assert.equal(state.correct, true);
  assert.equal(state.matched[0], true);
});

test("matchUpScore only counts pairs solved on the first attempt", () => {
  const board = { lesson_id: "l1", pairs: [
    { left: "A", right: "1" }, { left: "B", right: "2" }, { left: "C", right: "3" },
    { left: "D", right: "4" }, { left: "E", right: "5" },
  ], reveal: "r" };
  let state = matchUpInit(board, (arr) => arr);
  state = matchUpSelectRight(matchUpSelectLeft(state, 0), board, 0);              // pair 0: first try
  state = matchUpSelectRight(matchUpSelectLeft(state, 1), board, 2);              // pair 1: wrong first
  state = matchUpSelectRight(matchUpSelectLeft(state, 1), board, 1);              // pair 1: then right
  const { correct, total } = matchUpScore(state, board);
  assert.equal(correct, 1); // only pair 0 was first-attempt-correct
  assert.equal(total, 5);
});

test("matchUpComplete is true only once every pair is matched", () => {
  const board = { lesson_id: "l1", pairs: [{ left: "A", right: "1" }, { left: "B", right: "2" }], reveal: "r" };
  let state = matchUpInit(board, (arr) => arr);
  assert.equal(matchUpComplete(state, board), false);
  state = matchUpSelectRight(matchUpSelectLeft(state, 0), board, 0);
  state = matchUpSelectRight(matchUpSelectLeft(state, 1), board, 1);
  assert.equal(matchUpComplete(state, board), true);
});

test("matchBoardHTML escapes pair text and shows the reveal + Next only once complete", () => {
  const round = { format: "match_up", questions: [
    { lesson_id: "l1", pairs: [
      { left: "<b>A</b>", right: "1" }, { left: "B", right: "2" }, { left: "C", right: "3" },
      { left: "D", right: "4" }, { left: "E", right: "5" },
    ], reveal: "Because." },
  ] };
  const state = matchUpInit(round.questions[0], (arr) => arr);
  const html = matchBoardHTML(round, 0, state);
  assert.ok(html.includes("&lt;b&gt;A&lt;/b&gt;"));
  assert.ok(!html.includes('data-action="arcade-next"'));
});

// ---- end of round ----

test("arcadeResultHTML shows the rounded percentage and score", () => {
  const html = arcadeResultHTML({ score: 6, total: 8 });
  assert.ok(html.includes("75%"));
  assert.ok(html.includes("6 / 8"));
  assert.ok(html.includes('data-action="arcade-play-again"'));
  assert.ok(html.includes('data-action="arcade-back"'));
});

// ---- post-answer "Ask about this question" chat (design: 2026-07-17) ----

test("questionHTML shows no quiz-chat affordance while a question is still open", () => {
  const round = { format: "rapid_fire", questions: [
    { lesson_id: "l1", prompt: "P", choices: ["a", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const html = questionHTML(round, 0, { answered: false, selected: null });
  assert.ok(!html.includes("Ask about this question"));
  assert.ok(!html.includes('data-action="quiz-chat-open"'));
});

test("questionHTML shows the Ask about this question button once answered, closed by default", () => {
  const round = { format: "rapid_fire", questions: [
    { lesson_id: "l1", prompt: "P", choices: ["a", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const html = questionHTML(round, 0, { answered: true, selected: 1 });
  assert.ok(html.includes("Ask about this question"));
  assert.ok(html.includes('data-action="quiz-chat-open"'));
  assert.ok(!html.includes('data-action="quiz-chat-send"'));
});

test("questionHTML renders the open qchat panel with exact placeholder copy and no emojis", () => {
  const round = { format: "rapid_fire", questions: [
    { lesson_id: "l1", prompt: "P", choices: ["a", "b", "c"], answer: 1, reveal: "R" },
  ] };
  const qchat = { open: true, messages: [], streaming: false };
  const html = questionHTML(round, 0, { answered: true, selected: 1, qchat });
  assert.ok(html.includes("Ask why the answer is what it is..."));
  assert.ok(html.includes('data-action="quiz-chat-send"'));
  assert.ok(!html.includes('data-action="quiz-chat-open"'));
  assert.ok(!/\p{Emoji_Presentation}/u.test(html));
});

test("matchBoardHTML shows no quiz-chat affordance until the board is complete", () => {
  const round = { format: "match_up", questions: [
    { lesson_id: "l1", pairs: [
      { left: "A", right: "1" }, { left: "B", right: "2" }, { left: "C", right: "3" },
      { left: "D", right: "4" }, { left: "E", right: "5" },
    ], reveal: "Because." },
  ] };
  const state = matchUpInit(round.questions[0], (arr) => arr);
  const html = matchBoardHTML(round, 0, state, null);
  assert.ok(!html.includes("Ask about this question"));
});

test("matchBoardHTML shows the Ask about this question button once the board is complete", () => {
  const round = { format: "match_up", questions: [
    { lesson_id: "l1", pairs: [{ left: "A", right: "1" }, { left: "B", right: "2" }], reveal: "r" },
  ] };
  let state = matchUpInit(round.questions[0], (arr) => arr);
  state = matchUpSelectRight(matchUpSelectLeft(state, 0), round.questions[0], 0);
  state = matchUpSelectRight(matchUpSelectLeft(state, 1), round.questions[0], 1);
  const html = matchBoardHTML(round, 0, state, null);
  assert.ok(html.includes("Ask about this question"));
  assert.ok(html.includes('data-action="quiz-chat-open"'));
});

test("quizChatHTML escapes learner and assistant bubbles (XSS case)", () => {
  const qchat = { open: true, streaming: false, messages: [
    { role: "user", content: "<script>alert(1)</script>" },
    { role: "assistant", content: "<b>answer</b>" },
  ] };
  const html = quizChatHTML(qchat);
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<b>answer</b>"));
  assert.ok(html.includes("&lt;b&gt;answer&lt;/b&gt;"));
});

test("quizChatHTML disables input and send while streaming", () => {
  const html = quizChatHTML({ open: true, streaming: true, messages: [] });
  assert.ok(/data-field="qc-input"[^>]*disabled/.test(html));
  assert.ok(/data-action="quiz-chat-send"[^>]*disabled/.test(html));
});

test("quizChatHTML renders the toggle button when qchat is null or unopened", () => {
  assert.ok(quizChatHTML(null).includes('data-action="quiz-chat-open"'));
  assert.ok(quizChatHTML({ open: false }).includes('data-action="quiz-chat-open"'));
});
