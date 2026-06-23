function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function bubble(m) {
  const who = m.role === "user" ? "me" : "claude";
  return `<div class="msg ${who}">${esc(m.content)}</div>`;
}

export function chatHTML(messages, { pending = false } = {}) {
  const thread = messages.map(bubble).join("");
  const dots = pending ? `<div class="msg claude pending">…</div>` : "";
  return `
    <div class="chat-col">
      <div class="greeting"><h1>Add a course</h1><span>Tell Claude what you want to learn</span></div>
      <div class="chat-thread">${thread}${dots}</div>
      <div class="chat-input">
        <textarea data-field="chat" placeholder="e.g. intermediate linear algebra for ML, ~3h/week"></textarea>
        <button class="btn-primary" data-action="send">Send</button>
      </div>
    </div>
  `;
}
