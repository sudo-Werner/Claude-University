const FLAME = `<svg class="flame" viewBox="0 0 24 24" fill="none"><path d="M12 2c1 3-1 4-1 6a3 3 0 006 0c0-1.5-1-2.5-1-4 2 1.5 4 4 4 8a8 8 0 11-16 0c0-4 3-6 4-8 .5 1 1 1.5 2 2 1-1 1.5-2 1-4z" fill="#e0892f"/></svg>`;

export function shellHTML({ streakDays, back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${back}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <div class="streak">${FLAME}${streakDays}</div>
    </header>
    ${backBtn}
    <div id="view"></div>
  `;
}
