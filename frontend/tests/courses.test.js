import { test } from "node:test";
import assert from "node:assert/strict";
import { listCourses, loadCourse, loadLesson, getLessonStatus, loadReviews, loadReviewItems, gradeAnswer, deepenLesson, loadCapstone, loadLibrary, loadCourseNotes, loadMisconceptions, deleteMisconception, compileProgram, reviseCourse, applyRevision, explainAnswer, gradeTeaching, startExam, submitExam, startRemediation, loadTranscript, getQuizRound, postQuizResults, getQuizStats, makeHighlightReviewItem, startLessonGeneration, getGenerationProgress, listGenerationJobs } from "../src/courses.js";

test("listCourses returns the courses array", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ courses: [{ id: "machine-learning" }] }) };
  };
  const result = await listCourses({ fetch, endpoint: "/api/courses" });
  assert.equal(url, "/api/courses");
  assert.deepEqual(result, [{ id: "machine-learning" }]);
});

test("listCourses defaults to [] when none", async () => {
  const fetch = async () => ({ ok: true, json: async () => ({}) });
  assert.deepEqual(await listCourses({ fetch }), []);
});

test("loadCourse fetches the manifest by id", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ id: "machine-learning", modules: [] }) };
  };
  const c = await loadCourse({ fetch, courseId: "machine-learning" });
  assert.equal(url, "/api/courses/machine-learning");
  assert.equal(c.id, "machine-learning");
});

test("listCourses returns [] when fetch responds with non-ok status", async () => {
  const fetch = async () => ({ ok: false, status: 500 });
  assert.deepEqual(await listCourses({ fetch }), []);
});

test("loadLesson fetches by course and lesson id, error shape on miss", async () => {
  let url;
  const ok = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ id: "ml-m3-l2" }) };
  };
  const lesson = await loadLesson({ fetch: ok, courseId: "machine-learning", lessonId: "ml-m3-l2" });
  assert.equal(url, "/api/courses/machine-learning/lessons/ml-m3-l2");
  assert.equal(lesson.id, "ml-m3-l2");

  const missing = async () => ({ ok: false, status: 404 });
  const result = await loadLesson({ fetch: missing, courseId: "x", lessonId: "y" });
  assert.ok(result && result.error, "expected an error shape on miss");

  const withBody = async () => ({ ok: false, status: 503, json: async () => ({ error: "Claude auth expired" }) });
  const result2 = await loadLesson({ fetch: withBody, courseId: "x", lessonId: "y" });
  assert.equal(result2.error, "Claude auth expired");
});

test("loadReviews returns the due array", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ due: ["c-l1", "c-l2"] }) }; };
  const due = await loadReviews({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/reviews");
  assert.deepEqual(due, ["c-l1", "c-l2"]);
});

test("loadReviews returns [] on non-ok", async () => {
  assert.deepEqual(await loadReviews({ fetch: async () => ({ ok: false, status: 500 }), courseId: "c" }), []);
});

test("gradeAnswer posts the answer and returns the verdict", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ verdict: "correct", note: "Spot on." }) };
  };
  const r = await gradeAnswer({ fetch, courseId: "c", lessonId: "c-l1", answer: "42" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/grade");
  assert.equal(opts.method, "POST");
  assert.deepEqual(JSON.parse(opts.body), { answer: "42" });
  assert.equal(r.verdict, "correct");
});

test("gradeAnswer returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 502, json: async () => ({ error: "down" }) });
  const r = await gradeAnswer({ fetch, courseId: "c", lessonId: "c-l1", answer: "x" });
  assert.equal(r.error, "down");
});

test("deepenLesson POSTs to the deepen endpoint and returns the new lesson", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ id: "c-l1", promptHtml: "<p>deeper</p>" }) };
  };
  const r = await deepenLesson({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/deepen");
  assert.equal(opts.method, "POST");
  assert.equal(r.promptHtml, "<p>deeper</p>");
});

test("deepenLesson returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 503, json: async () => ({ error: "reauth" }) });
  const r = await deepenLesson({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(r.error, "reauth");
});

test("makeHighlightReviewItem posts the highlighted text and returns the item", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ item: { id: "hi-1", prompt: "q", source: "highlight" } }) };
  };
  const r = await makeHighlightReviewItem({ fetch, courseId: "c", lessonId: "c-l1", text: "worth remembering" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/highlight-review-item");
  assert.equal(opts.method, "POST");
  assert.deepEqual(JSON.parse(opts.body), { text: "worth remembering" });
  assert.equal(r.item.id, "hi-1");
});

test("makeHighlightReviewItem returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 502, json: async () => ({ error: "down" }) });
  const r = await makeHighlightReviewItem({ fetch, courseId: "c", lessonId: "c-l1", text: "x" });
  assert.equal(r.error, "down");
});

test("loadCapstone fetches by course and scope", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ scope: "m1", items: [] }) }; };
  const cap = await loadCapstone({ fetch, courseId: "c", scope: "m1" });
  assert.equal(url, "/api/courses/c/capstone/m1");
  assert.equal(cap.scope, "m1");
});

test("loadCapstone returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 502, json: async () => ({ error: "down" }) });
  const r = await loadCapstone({ fetch, courseId: "c", scope: "course" });
  assert.equal(r.error, "down");
});

test("loadLibrary fetches the course library", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ courseId: "c", sources: [] }) }; };
  const lib = await loadLibrary({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/library");
  assert.equal(lib.courseId, "c");
});

test("loadCourseNotes fetches the course notes summary", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ lessons: [{ lessonId: "c-l1" }] }) }; };
  const data = await loadCourseNotes({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/notes");
  assert.deepEqual(data.lessons, [{ lessonId: "c-l1" }]);
});

test("loadCourseNotes fails open to an empty list on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 500 });
  const data = await loadCourseNotes({ fetch, courseId: "c" });
  assert.deepEqual(data.lessons, []);
});

test("loadMisconceptions fetches the course misconceptions summary", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ entries: [{ id: "mc-1" }] }) }; };
  const data = await loadMisconceptions({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/misconceptions");
  assert.deepEqual(data.entries, [{ id: "mc-1" }]);
});

test("loadMisconceptions fails open to an empty list on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 500 });
  const data = await loadMisconceptions({ fetch, courseId: "c" });
  assert.deepEqual(data.entries, []);
});

test("deleteMisconception DELETEs the entry and returns the parsed body", async () => {
  let url, opts;
  const fetch = async (u, o) => { url = u; opts = o; return { ok: true, json: async () => ({ ok: true }) }; };
  const r = await deleteMisconception({ fetch, courseId: "c", entryId: "mc-1" });
  assert.equal(url, "/api/courses/c/misconceptions/mc-1");
  assert.equal(opts.method, "DELETE");
  assert.equal(r.ok, true);
});

test("deleteMisconception returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 404, json: async () => ({ error: "not found" }) });
  const r = await deleteMisconception({ fetch, courseId: "c", entryId: "mc-1" });
  assert.equal(r.error, "not found");
});

test("loadLibrary returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 503, json: async () => ({ error: "reauth" }) });
  const r = await loadLibrary({ fetch, courseId: "c" });
  assert.equal(r.error, "reauth");
});

test("compileProgram posts the brief and returns the proposed course", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ course: { title: "Deep ML", level: { code: "master" } } }) }; };
  const course = await compileProgram({ fetch, learnerBrief: { goal: "g" } });
  assert.equal(sent.url, "/api/courses/compile");
  assert.deepEqual(sent.body, { learnerBrief: { goal: "g" } });
  assert.equal(course.level.code, "master");
});

test("compileProgram returns an error object on failure", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "couldn't build your program, try again" }) });
  const r = await compileProgram({ fetch, learnerBrief: { goal: "g" } });
  assert.ok(r.error);
});

test("reviseCourse POSTs to the revise endpoint and returns full body", async () => {
  let sent = null;
  const fetch = async (url, opts) => {
    sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ course: { title: "ML" }, changeSummary: "Updated intro", progressAtRisk: false }) };
  };
  const result = await reviseCourse({ fetch, courseId: "c", messages: [{ role: "user", content: "make it harder" }] });
  assert.equal(sent.url, "/api/courses/c/revise");
  assert.equal(sent.body.messages[0].content, "make it harder");
  assert.equal(result.course.title, "ML");
  assert.equal(result.changeSummary, "Updated intro");
  assert.equal(result.progressAtRisk, false);
});

test("reviseCourse returns an error object on failure", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "Couldn't propose changes right now. Please try again." }) });
  const r = await reviseCourse({ fetch, courseId: "c", messages: [] });
  assert.ok(r.error);
});

test("applyRevision POSTs to the apply-revision endpoint and returns the course", async () => {
  let sent = null;
  const fetch = async (url, opts) => {
    sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ course: { title: "ML revised" } }) };
  };
  const result = await applyRevision({ fetch, courseId: "c", course: { title: "ML revised" } });
  assert.equal(sent.url, "/api/courses/c/apply-revision");
  assert.deepEqual(sent.body.course, { title: "ML revised" });
  assert.equal(result.title, "ML revised");
});

test("applyRevision returns an error object on failure", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "couldn't apply revision" }) });
  const r = await applyRevision({ fetch, courseId: "c", course: {} });
  assert.ok(r.error);
});

test("explainAnswer posts the explanation and returns the verdict", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, opts }; return { ok: true, json: async () => ({ verdict: "correct", note: "n" }) }; };
  const out = await explainAnswer({ fetch, courseId: "c1", lessonId: "c1-l1", explanation: "words" });
  assert.equal(out.verdict, "correct");
  assert.equal(sent.url, "/api/courses/c1/lessons/c1-l1/explain");
  assert.equal(JSON.parse(sent.opts.body).explanation, "words");
});

test("explainAnswer surfaces the server error message", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  const out = await explainAnswer({ fetch, courseId: "c1", lessonId: "c1-l1", explanation: "w" });
  assert.equal(out.error, "boom");
});

test("startExam posts and maps errors", async () => {
  const calls = [];
  const fetch = async (url, opts) => { calls.push([url, opts]); return { ok: true, json: async () => ({ examKey: "m1", questions: [] }) }; };
  const exam = await startExam({ fetch, courseId: "c1", examKey: "m1" });
  assert.equal(calls[0][0], "/api/courses/c1/exams/m1");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(exam.examKey, "m1");
  const failing = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  assert.equal((await startExam({ fetch: failing, courseId: "c1", examKey: "m1" })).error, "boom");
});

test("startExam threads the error code through (e.g. gap-review retake gate)", async () => {
  const gated = async () => ({ ok: false, json: async () => ({ error: "Complete the gap review before retaking — that's the corrective step.", code: "gap-review" }) });
  const out = await startExam({ fetch: gated, courseId: "c1", examKey: "m1" });
  assert.equal(out.code, "gap-review");
  const noCode = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  assert.equal((await startExam({ fetch: noCode, courseId: "c1", examKey: "m1" })).code, undefined);
});

test("submitExam posts answers and maps errors", async () => {
  const calls = [];
  const fetch = async (url, opts) => { calls.push([url, opts]); return { ok: true, json: async () => ({ passed: true }) }; };
  const res = await submitExam({ fetch, courseId: "c1", examKey: "final", answers: [1, "a"] });
  assert.equal(calls[0][0], "/api/courses/c1/exams/final/submit");
  assert.deepEqual(JSON.parse(calls[0][1].body), { answers: [1, "a"] });
  assert.equal(res.passed, true);
  const failing = async () => ({ ok: false, json: async () => { throw new Error("no body"); } });
  assert.ok((await submitExam({ fetch: failing, courseId: "c1", examKey: "final", answers: [] })).error);
});

test("startRemediation maps errors and returns session JSON", async () => {
  const ok = { examKey: "m1", gaps: [] };
  let session = await startRemediation({
    fetch: async () => ({ ok: true, json: async () => ok }), courseId: "c1", examKey: "m1" });
  assert.deepEqual(session, ok);
  session = await startRemediation({
    fetch: async () => ({ ok: false, json: async () => ({ error: "nothing to review" }) }),
    courseId: "c1", examKey: "m1" });
  assert.equal(session.error, "nothing to review");
});

test("loadTranscript returns body or null", async () => {
  const body = { courses: [] };
  assert.deepEqual(await loadTranscript({ fetch: async () => ({ ok: true, json: async () => body }) }), body);
  assert.equal(await loadTranscript({ fetch: async () => ({ ok: false }) }), null);
});

test("loadReviewItems fetches by course and lesson id and returns items", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ items: [{ type: "fill", prompt: "p", answer: "a", explanation: "e" }] }) };
  };
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/review-items");
  assert.ok(opts.signal instanceof AbortSignal);
  assert.equal(res.items.length, 1);
});

test("loadReviewItems returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "could not prepare fresh review questions" }) });
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(res.error, "could not prepare fresh review questions");
});

test("loadReviewItems returns an error shape when the fetch is aborted", async () => {
  const fetch = async () => { throw new DOMException("The operation was aborted.", "AbortError"); };
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(res.error);
});

test("loadReviewItems returns an error shape when the body parse rejects", async () => {
  const fetch = async () => ({ ok: true, json: () => Promise.reject(new Error("boom")) });
  const res = await loadReviewItems({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(res.error);
});

test("getLessonStatus fetches by course and lesson id and returns the parsed body", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ generated: true }) }; };
  const status = await getLessonStatus({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.equal(url, "/api/courses/c/lessons/c-l1/status");
  assert.deepEqual(status, { generated: true });
});

test("getLessonStatus returns an error shape on non-ok", async () => {
  const fetch = async () => ({ ok: false, status: 500 });
  const status = await getLessonStatus({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(status.error);
});

test("getLessonStatus returns an error shape (never rejects) when fetch rejects", async () => {
  const fetch = async () => { throw new Error("network down"); };
  const status = await getLessonStatus({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(status.error);
});

test("getLessonStatus returns an error shape when resp.json() rejects", async () => {
  const fetch = async () => ({ ok: true, json: () => Promise.reject(new Error("boom")) });
  const status = await getLessonStatus({ fetch, courseId: "c", lessonId: "c-l1" });
  assert.ok(status.error);
});

test("gradeTeaching posts the teaching transcript and returns the verdict", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, opts }; return { ok: true, json: async () => ({ verdict: "close", note: "n" }) }; };
  const messages = [{ role: "user", content: "A GET request fetches data." }];
  const out = await gradeTeaching({ fetch, courseId: "c1", lessonId: "c1-l1", messages });
  assert.equal(out.verdict, "close");
  assert.equal(sent.url, "/api/courses/c1/lessons/c1-l1/teach");
  assert.deepEqual(JSON.parse(sent.opts.body).messages, messages);
});

test("gradeTeaching surfaces the server error message", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "teach something first" }) });
  const out = await gradeTeaching({ fetch, courseId: "c1", lessonId: "c1-l1", messages: [] });
  assert.equal(out.error, "teach something first");
});

test("getQuizRound fetches the round endpoint and returns the parsed body", async () => {
  let url;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ status: "ready", round: { round_id: "round-x" } }) }; };
  const data = await getQuizRound({ fetch, courseId: "c" });
  assert.equal(url, "/api/courses/c/quiz/round");
  assert.equal(data.status, "ready");
});

test("getQuizRound returns an error shape on non-ok or network failure", async () => {
  const notOk = async () => ({ ok: false, status: 500 });
  assert.ok((await getQuizRound({ fetch: notOk, courseId: "c" })).error);
  const rejecting = async () => { throw new Error("down"); };
  assert.ok((await getQuizRound({ fetch: rejecting, courseId: "c" })).error);
});

test("postQuizResults posts the result payload and returns the body", async () => {
  let sent = null;
  const fetch = async (url, opts) => { sent = { url, body: JSON.parse(opts.body) }; return { ok: true, json: async () => ({ ok: true }) }; };
  const result = { client_event_id: "ce1", session_id: "s1", round_id: "round-x", format: "rapid_fire", score: 6, total: 8, missed: {} };
  const out = await postQuizResults({ fetch, courseId: "c", result });
  assert.equal(sent.url, "/api/courses/c/quiz/results");
  assert.deepEqual(sent.body, result);
  assert.deepEqual(out, { ok: true });
});

test("postQuizResults returns an error shape on failure", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "boom" }) });
  const out = await postQuizResults({ fetch, courseId: "c", result: {} });
  assert.equal(out.error, "boom");
});

test("getQuizStats fetches the stats endpoint and returns the body, or null on failure", async () => {
  let url;
  const ok = async (u) => { url = u; return { ok: true, json: async () => ({ roundsPlayed: 3 }) }; };
  const stats = await getQuizStats({ fetch: ok, courseId: "c" });
  assert.equal(url, "/api/courses/c/quiz/stats");
  assert.equal(stats.roundsPlayed, 3);
  assert.equal(await getQuizStats({ fetch: async () => ({ ok: false }), courseId: "c" }), null);
});

test("startLessonGeneration POSTs and returns the snapshot", async () => {
  let url, opts;
  const fetch = async (u, o) => {
    url = u; opts = o;
    return { ok: true, json: async () => ({ status: "running", events: [], next: 0 }) };
  };
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.equal(url, "/api/courses/c1/lessons/l1/generate");
  assert.equal(opts.method, "POST");
  assert.equal(snap.status, "running");
});

test("startLessonGeneration surfaces a server error message", async () => {
  const fetch = async () => ({ ok: false, json: async () => ({ error: "lesson not found" }) });
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.equal(snap.error, "lesson not found");
});

test("startLessonGeneration never throws on network failure", async () => {
  const fetch = async () => { throw new Error("offline"); };
  const snap = await startLessonGeneration({ fetch, courseId: "c1", lessonId: "l1" });
  assert.ok(snap.error);
});

test("getGenerationProgress passes since and returns the snapshot", async () => {
  let url;
  const fetch = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ status: "running", events: [{ n: 3 }], next: 4 }) };
  };
  const snap = await getGenerationProgress({ fetch, courseId: "c1", lessonId: "l1", since: 3 });
  assert.equal(url, "/api/courses/c1/lessons/l1/generate?since=3");
  assert.equal(snap.next, 4);
});

test("getGenerationProgress returns error on failure without throwing", async () => {
  const fetch = async () => { throw new Error("offline"); };
  const snap = await getGenerationProgress({ fetch, courseId: "c1", lessonId: "l1", since: 0 });
  assert.ok(snap.error);
});

test("listGenerationJobs returns jobs array, [] on failure", async () => {
  const good = async () => ({ ok: true, json: async () => ({ jobs: [{ courseId: "c1" }] }) });
  const bad = async () => { throw new Error("offline"); };
  assert.deepEqual((await listGenerationJobs({ fetch: good })).jobs, [{ courseId: "c1" }]);
  assert.deepEqual((await listGenerationJobs({ fetch: bad })).jobs, []);
});
