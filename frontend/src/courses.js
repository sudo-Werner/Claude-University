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

export async function explainAnswer({ fetch, courseId, lessonId, explanation }) {
  const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ explanation }),
  });
  if (!resp.ok) {
    let message = "Couldn't read your explanation right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function loadLibrary({ fetch, courseId }) {
  const resp = await fetch(`/api/courses/${courseId}/library`);
  if (!resp.ok) {
    let message = "Couldn't compile the library right now.";
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

export async function loadReviewItems({ fetch, courseId, lessonId }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const resp = await fetch(`/api/courses/${courseId}/lessons/${lessonId}/review-items`, { signal: controller.signal });
    if (!resp.ok) {
      let message = "Couldn't prepare fresh review questions right now.";
      try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
      return { error: message };
    }
    return resp.json();
  } catch (e) {
    return { error: "Couldn't prepare fresh review questions right now." };
  } finally {
    clearTimeout(timer);
  }
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

export async function compileProgram({ fetch, learnerBrief }) {
  const resp = await fetch("/api/courses/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ learnerBrief }),
  });
  if (!resp.ok) {
    let message = "Couldn't build your program right now. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  const body = await resp.json();
  return body.course;
}

export async function reviseCourse({ fetch, courseId, messages }) {
  const resp = await fetch(`/api/courses/${courseId}/revise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!resp.ok) {
    let message = "Couldn't propose changes right now. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function applyRevision({ fetch, courseId, course }) {
  const resp = await fetch(`/api/courses/${courseId}/apply-revision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ course }),
  });
  if (!resp.ok) {
    let message = "Couldn't apply the revision right now. Please try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  const body = await resp.json();
  return body.course;
}

export async function startExam({ fetch, courseId, examKey }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}`, { method: "POST" });
  if (!resp.ok) {
    let message = "Couldn't prepare the exam right now.";
    let code;
    try {
      const body = await resp.json();
      if (body && body.error) message = body.error;
      if (body && body.code) code = body.code;
    } catch (e) {}
    return { error: message, code };
  }
  return resp.json();
}

export async function submitExam({ fetch, courseId, examKey, answers }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade the exam right now — your answers are still here, try again.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function startRemediation({ fetch, courseId, examKey }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/remediation`, { method: "POST" });
  if (!resp.ok) {
    let message = "Couldn't prepare the gap review right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function loadTranscript({ fetch }) {
  const resp = await fetch("/api/transcript");
  if (!resp.ok) return null;
  return resp.json();
}

export async function gradeRemediationApply({ fetch, courseId, examKey, gapIndex, answer }) {
  const resp = await fetch(`/api/courses/${courseId}/exams/${examKey}/remediation/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gapIndex, answer }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade this answer right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}

export async function submitCapstone({ fetch, courseId, scope, work }) {
  const resp = await fetch(`/api/courses/${courseId}/capstone/${scope}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ work }),
  });
  if (!resp.ok) {
    let message = "Couldn't grade your capstone right now.";
    try { const body = await resp.json(); if (body && body.error) message = body.error; } catch (e) {}
    return { error: message };
  }
  return resp.json();
}
