export function buildEvent({
  type,
  topicId = null,
  courseId = null,
  payload = null,
  sessionId,
  device = "web",
  now,
  newId,
}) {
  return {
    client_event_id: newId(),
    session_id: sessionId,
    event_type: type,
    occurred_at: now().toISOString(),
    device,
    topic_id: topicId,
    course_id: courseId,
    payload,
  };
}

const BUFFER_KEY = "cu_event_buffer";

export function readBuffer(storage) {
  const raw = storage.getItem(BUFFER_KEY);
  return raw ? JSON.parse(raw) : [];
}

export function appendEvent(storage, event) {
  const buffer = readBuffer(storage);
  buffer.push(event);
  storage.setItem(BUFFER_KEY, JSON.stringify(buffer));
}

export function clearEvents(storage, clientEventIds) {
  const drop = new Set(clientEventIds);
  const remaining = readBuffer(storage).filter(
    (e) => !drop.has(e.client_event_id),
  );
  storage.setItem(BUFFER_KEY, JSON.stringify(remaining));
}
