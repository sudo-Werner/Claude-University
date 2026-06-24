import { test } from "node:test";
import assert from "node:assert/strict";
import { listCourses, loadCourse, loadLesson, loadReviews, gradeAnswer, deepenLesson, loadCapstone } from "../src/courses.js";

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
