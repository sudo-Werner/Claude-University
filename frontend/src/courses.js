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
  if (!resp.ok) {
    let message = "Couldn't load this lesson. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function gradeAnswer({ fetch, courseId, lessonId, answer }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  if (!resp.ok) {
    let message = "Couldn't check your answer right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function loadCapstone({ fetch, courseId, scope }) {
  const resp = await fetch(`/api/courses/${courseId}/capstone/${scope}`);
  if (!resp.ok) {
    let message = "Couldn't load the real-world connections right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function deepenLesson({ fetch, courseId, lessonId }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/deepen`, { method: "POST" });
  if (!resp.ok) {
    let message = "Couldn't rewrite this lesson right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function loadReviews({ fetch, courseId }) {
  const resp = await fetch(`/api/courses/${courseId}/reviews`);
  if (!resp.ok) return [];
  const body = await resp.json();
  return body.due || [];
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
