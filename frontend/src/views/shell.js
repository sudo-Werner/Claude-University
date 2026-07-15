import { esc } from "../escape.js";

export function shellHTML({ back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${esc(back)}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
    </header>
    ${backBtn}
    <div id="view"></div>
  `;
}
