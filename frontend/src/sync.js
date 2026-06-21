import { readBuffer, clearEvents } from "./eventlog.js";

export async function flush({ storage, fetch, endpoint }) {
  const events = readBuffer(storage);
  if (events.length === 0) return { flushed: 0 };

  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!resp.ok) return { flushed: 0, error: `HTTP ${resp.status}` };
    clearEvents(storage, events.map((e) => e.client_event_id));
    return { flushed: events.length };
  } catch (err) {
    return { flushed: 0, error: String(err) };
  }
}
