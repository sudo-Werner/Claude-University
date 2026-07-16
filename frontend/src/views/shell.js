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

export function shellHTML({ back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${esc(back)}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <button class="fb-toggle" data-action="feedback-toggle">Feedback</button>
    </header>
    <div data-fb-slot></div>
    ${backBtn}
    <div id="view"></div>
  `;
}
