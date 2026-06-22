import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildEvent,
  readBuffer,
  appendEvent,
  clearEvents,
} from "../src/eventlog.js";

const fixedNow = () => new Date("2026-06-21T10:00:00.000Z");
let counter = 0;
const fakeId = () => `id-${counter++}`;

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, v),
  };
}

test("buildEvent produces the fields the API expects", () => {
  counter = 0;
  const ev = buildEvent({
    type: "lesson_view",
    topicId: "p1t1",
    payload: { section: "intro" },
    sessionId: "s1",
    now: fixedNow,
    newId: fakeId,
  });
  assert.equal(ev.event_type, "lesson_view");
  assert.equal(ev.session_id, "s1");
  assert.equal(ev.topic_id, "p1t1");
  assert.deepEqual(ev.payload, { section: "intro" });
  assert.equal(ev.occurred_at, "2026-06-21T10:00:00.000Z");
  assert.equal(ev.device, "web");
  assert.equal(ev.client_event_id, "id-0");
});

test("each event gets a distinct client_event_id", () => {
  counter = 0;
  const a = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  const b = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.notEqual(a.client_event_id, b.client_event_id);
});

test("buffer starts empty", () => {
  assert.deepEqual(readBuffer(fakeStorage()), []);
});

test("appended events accumulate", () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  assert.deepEqual(readBuffer(s).map((e) => e.client_event_id), ["a", "b"]);
});

test("clearEvents removes only the named ids", () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  appendEvent(s, { client_event_id: "c" });
  clearEvents(s, ["a", "c"]);
  assert.deepEqual(readBuffer(s).map((e) => e.client_event_id), ["b"]);
});

test("buildEvent includes course_id (null by default, set when given)", () => {
  counter = 0;
  const a = buildEvent({ type: "x", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.equal(a.course_id, null);
  const b = buildEvent({ type: "x", courseId: "machine-learning", sessionId: "s", now: fixedNow, newId: fakeId });
  assert.equal(b.course_id, "machine-learning");
});
