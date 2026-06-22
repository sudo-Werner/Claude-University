import { test } from "node:test";
import assert from "node:assert/strict";
import { listCourses, loadCourse, loadLesson } from "../src/courses.js";

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

test("loadLesson fetches by course and lesson id, null on miss", async () => {
  let url;
  const ok = async (u) => {
    url = u;
    return { ok: true, json: async () => ({ id: "ml-m3-l2" }) };
  };
  const lesson = await loadLesson({ fetch: ok, courseId: "machine-learning", lessonId: "ml-m3-l2" });
  assert.equal(url, "/api/courses/machine-learning/lessons/ml-m3-l2");
  assert.equal(lesson.id, "ml-m3-l2");

  const missing = async () => ({ ok: false, status: 404 });
  assert.equal(await loadLesson({ fetch: missing, courseId: "x", lessonId: "y" }), null);
});
