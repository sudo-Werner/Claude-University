import { DIAGNOSTIC } from "../profile.js";

const DOT = `<span class="dot"><i></i></span>`;

export function diagnosticHTML(answers) {
  const cards = DIAGNOSTIC.map((q) => {
    const opts = q.options
      .map((o) => {
        const selected = answers[q.key] === o.value ? " selected" : "";
        return `<button class="opt${selected}" data-q="${q.key}" data-value="${o.value}">${DOT}<span style="flex:1">${o.label}</span></button>`;
      })
      .join("");
    return `<section class="card"><div class="diag-q">${q.question}</div>${opts}</section>`;
  }).join("");

  const answered = DIAGNOSTIC.every((q) => answers[q.key] !== undefined);
  const disabled = answered ? "" : "disabled";

  return `
    <div class="diag-col">
    <div class="greeting"><h1>Let's tune how this teaches you</h1></div>
    ${cards}
    <button class="btn-primary" data-action="finish-diagnostic" ${disabled}>Start learning</button>
    </div>
  `;
}
