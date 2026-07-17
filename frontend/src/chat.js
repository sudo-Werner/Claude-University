export function parseSSELines(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop(); // last item is an incomplete frame (or "")
  for (const frame of parts) {
    let event = null;
    const dataLines = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      // Per the SSE spec, a frame may carry multiple data: lines (the backend
      // emits one per newline of a multi-line chat delta). Join them with "\n"
      // and strip only the single framing space after "data:" — not all
      // whitespace — so payload whitespace and newlines survive intact.
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (event) events.push({ event, data: dataLines.join("\n") });
  }
  return { events, rest };
}

export async function streamChat({ fetch, messages, endpoint = "/api/courses/chat", extra = {}, onDelta, onBrief, onDone, onError }) {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, ...extra }),
  });
  // A non-200 response has no SSE body to read — reading it as one finds nothing and
  // exits without ever calling onDone/onError, leaving the caller's pending/streaming
  // flag stuck forever (a permanently hung "typing" bubble + disabled input). Route it
  // through the error callback instead, same shape as an in-stream "error" event.
  if (!resp.ok) {
    let message = null;
    try {
      const body = await resp.json();
      message = body && body.error;
    } catch (e) {}
    if (onError) onError({ message: message || "Request failed. Please try again." });
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSSELines(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "delta") onDelta(data);
      else if (event === "brief") { if (onBrief) onBrief(JSON.parse(data)); }
      else if (event === "done") onDone();
      else if (event === "error") { if (onError) onError(JSON.parse(data)); }
    }
  }
}
