import { test } from "node:test";
import assert from "node:assert/strict";
import { loadWorkspace, saveWorkspace } from "../src/notes.js";

function fakeStorage() {
  const m = {};
  return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } };
}

test("loadWorkspace returns server data and caches it", async () => {
  const storage = fakeStorage();
  const fetch = async () => ({ ok: true, json: async () => ({ notes: "n", chat: [], updatedAt: "t" }) });
  const ws = await loadWorkspace({ fetch, storage, courseId: "c", lessonId: "l1" });
  assert.equal(ws.notes, "n");
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "n");
});

test("loadWorkspace falls back to cache when the request throws", async () => {
  const storage = fakeStorage();
  storage.setItem("ws:c:l1", JSON.stringify({ notes: "cached", chat: [], updatedAt: null }));
  const fetch = async () => { throw new Error("offline"); };
  const ws = await loadWorkspace({ fetch, storage, courseId: "c", lessonId: "l1" });
  assert.equal(ws.notes, "cached");
});

test("saveWorkspace caches first, then PUTs", async () => {
  const storage = fakeStorage();
  let url, opts;
  const fetch = async (u, o) => { url = u; opts = o; return { ok: true, json: async () => ({ updatedAt: "t2" }) }; };
  const r = await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "hi", chat: [] });
  assert.equal(url, "/api/courses/c/lessons/l1/workspace");
  assert.equal(opts.method, "PUT");
  assert.equal(r.ok, true);
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "hi");
});

test("saveWorkspace keeps the cache when the save fails", async () => {
  const storage = fakeStorage();
  const fetch = async () => { throw new Error("offline"); };
  const r = await saveWorkspace({ fetch, storage, courseId: "c", lessonId: "l1", notes: "keep", chat: [] });
  assert.equal(r.ok, false);
  assert.equal(JSON.parse(storage.getItem("ws:c:l1")).notes, "keep");
});
