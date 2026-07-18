const KEY = (courseId, lessonId) => `ws:${courseId}:${lessonId}`;
const EMPTY = { notes: "", chat: [], highlights: [], updatedAt: null };

function cacheGet(storage, courseId, lessonId) {
  try { return JSON.parse(storage.getItem(KEY(courseId, lessonId))); } catch (e) { return null; }
}
function cacheSet(storage, courseId, lessonId, ws) {
  try { storage.setItem(KEY(courseId, lessonId), JSON.stringify(ws)); } catch (e) {}
}

export async function loadWorkspace({ fetch, storage, courseId, lessonId }) {
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`);
    if (resp.ok) {
      const ws = await resp.json();
      cacheSet(storage, courseId, lessonId, ws);
      return ws;
    }
  } catch (e) {}
  return cacheGet(storage, courseId, lessonId) || { ...EMPTY };
}

export async function saveWorkspace({ fetch, storage, courseId, lessonId, notes, chat, highlights = [] }) {
  // Optimistic: write the local cache first so a failed/offline save never loses text
  // (or a just-created highlight -- see Task 6's addHighlightFromSelection).
  cacheSet(storage, courseId, lessonId, { notes, chat, highlights, updatedAt: new Date().toISOString() });
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/workspace`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, chat, highlights }),
    });
    if (!resp.ok) return { ok: false, error: `save failed (${resp.status})` };
    const body = await resp.json();
    return { ok: true, updatedAt: body.updatedAt };
  } catch (e) {
    return { ok: false, error: "offline" };
  }
}
