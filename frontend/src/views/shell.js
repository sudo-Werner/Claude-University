import { esc } from "../escape.js";

// The quick-feedback composer. Rendered into the shell's [data-fb-slot] both at
// shell paint (collapsed default — navigation deliberately collapses the bar) and
// on every state change via app.js's paintFeedbackBar. All text esc()'d; the
// note itself is never rendered back after sending.
export function feedbackBarHTML(fb) {
  const f = fb || {};
  if (!f.open) return "";
  if (f.notice === "sent") {
    return `<div class="feedback-bar"><span class="fb-done">Thanks — noted.</span></div>`;
  }
  const sendDisabled = f.sending || !(f.text || "").trim();
  return `
    <div class="feedback-bar">
      <input class="fb-input" data-field="fb-text" type="text"
        placeholder="Ideas, annoyances, requests — straight to the build loop."
        value="${esc(f.text || "")}" ${f.sending ? "disabled" : ""}>
      <button class="fb-send" data-action="feedback-send" ${sendDisabled ? "disabled" : ""}>${f.sending ? "Sending…" : "Send"}</button>
      ${f.notice === "error" ? `<span class="fb-err">Couldn't send — try again.</span>` : ""}
    </div>
  `;
}

// A toggle+slot pair is one feedback "entry point". Several can be on screen at
// once (the topbar's, always present, plus e.g. the lesson screen's second one
// below the workspace) — they share ui.feedback as their one source of truth
// (app.js paints every [data-fb-slot] found); `where` only distinguishes which
// pair a click/focus belongs to, it never forks the state itself.
export function feedbackEntryHTML(where, label) {
  return (
    `<button class="fb-toggle" data-action="feedback-toggle" data-fb-toggle="${esc(where)}">${esc(label)}</button>` +
    `<div data-fb-slot="${esc(where)}"></div>`
  );
}

// ---- in-course sidenav ----------------------------------------------------
// A persistent navigation rail for everything inside a course (desktop >=1100px);
// below that it renders as an off-canvas drawer opened by the topbar's menu
// button. Pure markup — app.js owns all behavior via [data-side-nav] /
// [data-action="sidenav-toggle"] delegation, so this survives shell repaints
// with zero rebinding.
const SN_ICONS = {
  today: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v4l2.5 1.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  curriculum: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5v-15z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M4 20.5A2.5 2.5 0 016.5 18H20" stroke="currentColor" stroke-width="1.8"/></svg>`,
  reviews: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="13" height="15" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 3h13v15" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`,
  arcade: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 4h12l2 5-8 11L4 9l2-5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M4 9h16M10 9l2 11 2-11" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`,
  library: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 4h4v16H5zM11 4h4v16h-4zM17.5 5l3.5 15-4 .8L13.6 6l3.9-1z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>`,
  mynotes: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 3h11l3 3v15H5V3z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M9 9h6M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  misconceptions: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 3l9 18H3l9-18z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4M12 17.5v.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
};
const SN_ITEMS = [
  ["today", "Today"],
  ["curriculum", "Curriculum"],
  ["reviews", "Reviews"],
  ["arcade", "Arcade"],
  ["library", "Library"],
  ["mynotes", "My notes"],
  ["misconceptions", "Misconceptions"],
];

export function sidenavHTML(nav) {
  const items = SN_ITEMS.map(([key, label]) => {
    const on = key === nav.active;
    const tail =
      key === "reviews" && nav.reviewsDue > 0
        ? `<span class="sn-badge">${nav.reviewsDue}</span>`
        : on
          ? `<span class="sn-dot"></span>`
          : "";
    return `<button class="sn-item${on ? " on" : ""}" data-side-nav="${key}"${on ? ' aria-current="page"' : ""}>${SN_ICONS[key]}<span class="sn-label">${label}</span>${tail}</button>`;
  }).join("");
  return `
    <aside class="sidenav">
      <button class="sn-close" data-action="sidenav-toggle" aria-label="Close menu">×</button>
      <div class="brand sn-brand"><span class="logo">U</span>Claude University</div>
      <nav class="sn-nav">${items}</nav>
      <div class="sn-foot">
        <span data-gen-chip></span>
        <div class="sn-course">
          <div class="sn-course-label">Course</div>
          <div class="sn-course-title">${esc(nav.courseTitle)}</div>
          <div class="sn-course-meta">${nav.lessonsDone} of ${nav.lessonsTotal} lessons</div>
        </div>
        ${feedbackEntryHTML("side", "Feedback")}
      </div>
    </aside>
    <div class="sn-scrim" data-action="sidenav-toggle"></div>
  `;
}

const SN_MENU_ICON = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none"><path d="M4 6.5h16M4 12h16M4 17.5h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;

// nav (optional) switches the shell into the two-pane in-course layout:
// sidenav rail/drawer + main column. Without it the classic centered
// topbar shell renders unchanged (home, add-course, records screens).
export function shellHTML({ back = null, nav = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${esc(back)}</button>`
    : "";
  const main = `
    <header class="topbar">
      ${nav ? `<button class="sn-open" data-action="sidenav-toggle" aria-label="Menu">${SN_MENU_ICON}</button>` : ""}
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <span data-gen-chip></span>
      <button class="fb-toggle" data-action="feedback-toggle" data-fb-toggle="top">Feedback</button>
    </header>
    <div data-fb-slot="top"></div>
    ${backBtn}
    <div id="view"></div>
  `;
  if (!nav) return main;
  return `<div class="shell">${sidenavHTML(nav)}<div class="shell-main">${main}</div></div>`;
}
