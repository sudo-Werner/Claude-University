import { test } from "node:test";
import assert from "node:assert/strict";
import { loadStats, loadActivity } from "../src/stats.js";

const okFetch = (body) => async () => ({ ok: true, json: async () => body });
const badFetch = async () => ({ ok: false, json: async () => ({}) });

test("loadStats returns the body on success", async () => {
  const stats = await loadStats({ fetch: okFetch({ streakDays: 4 }) });
  assert.equal(stats.streakDays, 4);
});

test("loadStats falls back to zero streak on failure", async () => {
  const stats = await loadStats({ fetch: badFetch });
  assert.equal(stats.streakDays, 0);
});

test("loadActivity returns entries and passes limit", async () => {
  let url = null;
  const fetch = async (u) => { url = u; return { ok: true, json: async () => ({ activity: [{ type: "lesson_view" }] }) }; };
  const entries = await loadActivity({ fetch, limit: 25 });
  assert.equal(entries.length, 1);
  assert.equal(url, "/api/activity?limit=25");
});

test("loadActivity returns empty list on failure", async () => {
  assert.deepEqual(await loadActivity({ fetch: badFetch }), []);
});
