export async function loadStats({ fetch }) {
  const resp = await fetch("/api/stats");
  if (!resp.ok) return { streakDays: 0 };
  return resp.json();
}

export async function loadActivity({ fetch, limit = 50 }) {
  const resp = await fetch(`/api/activity?limit=${limit}`);
  if (!resp.ok) return [];
  const body = await resp.json();
  return body.activity || [];
}
