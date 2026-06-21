import { test } from "node:test";
import assert from "node:assert/strict";
import { appendEvent, readBuffer } from "../src/eventlog.js";
import { flush } from "../src/sync.js";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, v),
  };
}

test("empty buffer flushes nothing and skips the network", async () => {
  const s = fakeStorage();
  let called = false;
  const fetch = async () => {
    called = true;
  };
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.deepEqual(res, { flushed: 0 });
  assert.equal(called, false);
});

test("successful flush empties the buffer", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  appendEvent(s, { client_event_id: "b" });
  const fetch = async () => ({ ok: true, json: async () => ({ accepted: 2 }) });
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 2);
  assert.deepEqual(readBuffer(s), []);
});

test("failed flush keeps the buffer for retry", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  const fetch = async () => {
    throw new Error("network down");
  };
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 0);
  assert.ok(res.error);
  assert.equal(readBuffer(s).length, 1);
});

test("non-2xx response keeps the buffer", async () => {
  const s = fakeStorage();
  appendEvent(s, { client_event_id: "a" });
  const fetch = async () => ({ ok: false, status: 500 });
  const res = await flush({ storage: s, fetch, endpoint: "/api/events" });
  assert.equal(res.flushed, 0);
  assert.equal(readBuffer(s).length, 1);
});
