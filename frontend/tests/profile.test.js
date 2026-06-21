import { test } from "node:test";
import assert from "node:assert/strict";
import { DIAGNOSTIC, buildProfile, saveProfile, loadProfile } from "../src/profile.js";

test("diagnostic covers exactly the six profile settings", () => {
  const keys = DIAGNOSTIC.map((q) => q.key).sort();
  assert.deepEqual(keys, [
    "analogies",
    "contentOrder",
    "lessonStructure",
    "sessionStyle",
    "stuckStrategy",
    "wrongAnswerFeedback",
  ]);
  for (const q of DIAGNOSTIC) {
    assert.ok(q.question.length > 0);
    assert.ok(q.options.length >= 2);
  }
});

test("buildProfile maps answers to the config object", () => {
  const answers = {
    contentOrder: "theory_first",
    stuckStrategy: "push",
    wrongAnswerFeedback: "hint",
    sessionStyle: "deep_block",
    lessonStructure: "top_down",
    analogies: true,
  };
  assert.deepEqual(buildProfile(answers), answers);
});

test("saveProfile posts to the endpoint", async () => {
  let sent;
  const fetch = async (url, opts) => {
    sent = { url, body: JSON.parse(opts.body) };
    return { ok: true, json: async () => ({ id: 1 }) };
  };
  await saveProfile({ fetch, endpoint: "/api/profile", profile: { analogies: true } });
  assert.equal(sent.url, "/api/profile");
  assert.deepEqual(sent.body, { analogies: true });
});

test("loadProfile returns the saved data or null", async () => {
  const withData = async () => ({ ok: true, json: async () => ({ data: { analogies: false } }) });
  assert.deepEqual(await loadProfile({ fetch: withData, endpoint: "/api/profile" }), {
    analogies: false,
  });
  const empty = async () => ({ ok: true, json: async () => ({}) });
  assert.equal(await loadProfile({ fetch: empty, endpoint: "/api/profile" }), null);
});
