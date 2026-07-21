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

export function shellHTML({ back = null }) {
  const backBtn = back
    ? `<button class="nav-back-top" data-action="nav-back">← ${esc(back)}</button>`
    : "";
  return `
    <header class="topbar">
      <div class="brand"><span class="logo">U</span>Claude University</div>
      <span data-gen-chip></span>
      <button class="fb-toggle" data-action="feedback-toggle" data-fb-toggle="top">Feedback</button>
    </header>
    <div data-fb-slot="top"></div>
    ${backBtn}
    <div id="view"></div>
  `;
}
