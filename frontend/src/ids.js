// Generate a UUID v4. crypto.randomUUID() only exists in a secure context
// (HTTPS or localhost); the app is served over plain HTTP via Tailscale, which
// is NOT a secure context, so we fall back to crypto.getRandomValues (which is
// available over plain HTTP) and finally to Math.random. The id is only an
// idempotency key, so a non-cryptographic source is acceptable.
function uuidV4() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; // version 4
    b[8] = (b[8] & 0x3f) | 0x80; // variant
    const h = [...b].map((x) => x.toString(16).padStart(2, "0"));
    return (
      `${h[0]}${h[1]}${h[2]}${h[3]}-${h[4]}${h[5]}-${h[6]}${h[7]}-` +
      `${h[8]}${h[9]}-${h[10]}${h[11]}${h[12]}${h[13]}${h[14]}${h[15]}`
    );
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function newId(prefix = "") {
  return prefix + uuidV4();
}

export function getSessionId(storage) {
  let id = storage.getItem("cu_session_id");
  if (!id) {
    id = newId("sess-");
    storage.setItem("cu_session_id", id);
  }
  return id;
}
