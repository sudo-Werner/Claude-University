import { getSessionId, newId } from "./ids.js";
import { buildEvent, appendEvent } from "./eventlog.js";
import { flush } from "./sync.js";
import { loadProfile } from "./profile.js";

const EVENTS_ENDPOINT = "/api/events";
const PROFILE_ENDPOINT = "/api/profile";
const FLUSH_INTERVAL_MS = 15000;

export async function init({ window, fetch }) {
  const storage = window.localStorage;
  const sessionId = getSessionId(storage);

  const log = (type, opts = {}) =>
    appendEvent(
      storage,
      buildEvent({ type, sessionId, now: () => new Date(), newId, ...opts }),
    );

  log("session_start");

  const doFlush = () => flush({ storage, fetch, endpoint: EVENTS_ENDPOINT });
  await doFlush();
  window.setInterval(doFlush, FLUSH_INTERVAL_MS);

  const app = window.document.getElementById("app");
  const profile = await loadProfile({ fetch, endpoint: PROFILE_ENDPOINT });
  // Placeholder rendering — real screens arrive with the design (Plan 3).
  app.textContent = profile
    ? "Profile loaded — ready. (Styled screens come next.)"
    : "First run — diagnostic goes here. (Styled screens come next.)";
}
