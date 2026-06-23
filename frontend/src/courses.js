export async function listCourses({ fetch, endpoint = "/api/courses" }) {
  const resp = await fetch(endpoint);
  if (!resp.ok) return [];
  const body = await resp.json();
  return body.courses || [];
}

export async function loadCourse({ fetch, courseId }) {
  const resp = await fetch(`/api/courses/${courseId}`);
  if (!resp.ok) return null;
  return resp.json();
}

export async function loadLesson({ fetch, courseId, lessonId }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}`);
  if (!resp.ok) return null;
  return resp.json();
}

export async function createCourse({ fetch, proposal }) {
  const resp = await fetch("/api/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(proposal),
  });
  if (!resp.ok) return null;
  const body = await resp.json();
  return body.course;
}
