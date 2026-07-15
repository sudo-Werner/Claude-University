import { esc } from "../escape.js";

function bannerHTML(courses) {
  const withDue = courses.filter((c) => c.reviewsDue > 0);
  const total = withDue.reduce((n, c) => n + c.reviewsDue, 0);
  if (!total) return "";
  const where = withDue.length === 1 ? esc(withDue[0].title) : `${withDue.length} courses`;
  return `<div class="review-banner"><b>${total} review${total === 1 ? "" : "s"} due</b> in ${where} — a quick review now keeps it stuck.</div>`;
}

function courseCard(c) {
  return `
    <button class="course-card" data-course="${c.id}">
      <div class="course-title">${esc(c.title)}</div>
      <div class="course-sub">${esc(c.subtitle)}</div>
      <div class="bar"><i style="width:${c.progress.pct}%"></i></div>
      <div class="course-meta">${c.progress.done} of ${c.progress.total} lessons · ${c.reviewsDue} reviews due</div>
      <span class="course-continue">Continue →</span>
    </button>`;
}

export function homeHTML(courses) {
  const cards = courses.map(courseCard).join("");
  const count = courses.length;
  return `
    <div class="home">
    <div class="greeting"><h1>Your university</h1><span>${count} course${count === 1 ? "" : "s"}</span></div>
    ${bannerHTML(courses)}
    <div class="course-grid">
      ${cards}
      <button class="course-card add-course" data-action="add-course">
        <span class="add-plus">+</span>
        <div class="course-title">Add a course</div>
        <div class="course-sub">Tell Claude what you want to learn</div>
      </button>
    </div>
    </div>
  `;
}
