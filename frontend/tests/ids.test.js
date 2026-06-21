import { test } from "node:test";
import assert from "node:assert/strict";
import { newId, getSessionId } from "../src/ids.js";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, v),
  };
}

test("newId returns a valid v4 uuid with the prefix", () => {
  const id = newId("sess-");
  assert.ok(id.startsWith("sess-"));
  assert.match(id.slice("sess-".length), UUID_RE);
});

test("newId is unique across calls", () => {
  assert.notEqual(newId(), newId());
});

test("newId works without crypto.randomUUID (insecure-context fallback)", () => {
  const original = crypto.randomUUID;
  // Simulate plain-HTTP context where randomUUID is unavailable.
  crypto.randomUUID = undefined;
  try {
    const id = newId();
    assert.match(id, UUID_RE);
  } finally {
    crypto.randomUUID = original;
  }
});

test("getSessionId creates once and persists", () => {
  const s = fakeStorage();
  const first = getSessionId(s);
  const second = getSessionId(s);
  assert.equal(first, second);
  assert.ok(first.startsWith("sess-"));
});
