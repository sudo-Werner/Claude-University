import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSSELines, streamChat } from "../src/chat.js";
import { chatHTML } from "../src/views/chat.js";

function bodyFrom(str) {
  const bytes = new TextEncoder().encode(str);
  let sent = false;
  return { getReader: () => ({ read: async () => (sent ? { done: true } : (sent = true, { value: bytes, done: false })) }) };
}

test("streamChat posts to a custom endpoint and tolerates a missing onBrief", async () => {
  let url;
  const fetch = async (u) => { url = u; return { body: bodyFrom("event: delta\ndata: hi\n\nevent: done\ndata: {}\n\n") }; };
  let text = "", done = false;
  await streamChat({
    fetch, endpoint: "/api/courses/c/lessons/l1/chat", messages: [],
    onDelta: (d) => { text += d; }, onDone: () => { done = true; },
  });
  assert.equal(url, "/api/courses/c/lessons/l1/chat");
  assert.equal(text, "hi");
  assert.equal(done, true);
});

test("streamChat merges extra fields into the POST body", async () => {
  let sent;
  const fetch = async (u, opts) => {
    sent = JSON.parse(opts.body);
    return { body: bodyFrom("event: done\ndata: {}\n\n") };
  };
  await streamChat({
    fetch, messages: [{ role: "user", content: "hi" }], endpoint: "/x",
    extra: { solutionRevealed: true }, onDelta: () => {}, onDone: () => {},
  });
  assert.equal(sent.solutionRevealed, true);
  assert.equal(sent.messages.length, 1);
});

test("parseSSELines extracts complete events and keeps the partial tail", () => {
  const buffer =
    "event: delta\ndata: Hi\n\n" +
    "event: proposal\ndata: {\"title\":\"X\"}\n\n" +
    "event: done\ndata: {}";  // no trailing blank line yet
  const { events, rest } = parseSSELines(buffer);
  assert.deepEqual(events[0], { event: "delta", data: "Hi" });
  assert.deepEqual(events[1], { event: "proposal", data: '{"title":"X"}' });
  assert.equal(events.length, 2);          // "done" is incomplete
  assert.match(rest, /event: done/);       // retained for the next chunk
});

test("parseSSELines returns no events for an empty buffer", () => {
  assert.deepEqual(parseSSELines(""), { events: [], rest: "" });
});

test("parseSSELines joins multiple data lines in one frame (multi-line delta)", () => {
  const { events } = parseSSELines("event: delta\ndata: Line one.\ndata: Line two.\n\n");
  assert.deepEqual(events[0], { event: "delta", data: "Line one.\nLine two." });
});

test("chatHTML renders the composer with input + send hooks", () => {
  const html = chatHTML([], {});
  assert.match(html, /data-field="chat"/);
  assert.match(html, /data-action="send"/);
  assert.match(html, /Add a course/);
});

test("chatHTML escapes message content", () => {
  const html = chatHTML([{ role: "user", content: "<b>hi</b>" }], {});
  assert.doesNotMatch(html, /<b>hi<\/b>/);
  assert.match(html, /&lt;b&gt;hi/);
});

function fakeFetchSSE(frames) {
  const body = frames.map((f) => `event: ${f.event}\ndata: ${f.data}\n\n`).join("");
  const bytes = new TextEncoder().encode(body);
  return async () => ({
    body: { getReader: () => { let done = false;
      return { read: async () => done ? { done: true } : (done = true, { value: bytes, done: false }) }; } },
  });
}

test("streamChat dispatches brief event to onBrief", async () => {
  let brief = null;
  await streamChat({
    fetch: fakeFetchSSE([{ event: "brief", data: JSON.stringify({ goal: "build models" }) }, { event: "done", data: "{}" }]),
    messages: [], onDelta() {}, onBrief: (b) => { brief = b; }, onDone() {}, onError() {},
  });
  assert.equal(brief.goal, "build models");
});

test("chatHTML escapes message content", () => {
  const html = chatHTML([{ role: "assistant", content: "<script>x</script>" }]);
  assert.ok(!html.includes("<script>x</script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("chatHTML accepts a custom placeholder", () => {
  const html = chatHTML([], { placeholder: "describe your change" });
  assert.ok(html.includes('placeholder="describe your change"'));
  const dflt = chatHTML([]);
  assert.ok(dflt.includes("intermediate linear algebra"));
});
