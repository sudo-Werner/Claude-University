export function newId(prefix = "") {
  return prefix + crypto.randomUUID();
}

export function getSessionId(storage) {
  let id = storage.getItem("cu_session_id");
  if (!id) {
    id = newId("sess-");
    storage.setItem("cu_session_id", id);
  }
  return id;
}
