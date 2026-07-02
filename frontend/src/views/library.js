import { esc } from "../escape.js";

// #accredited-sources — the course "Library": real, web-retrieved accredited sources,
// grouped by type. title/note arrive server-sanitized; the URL is a genuinely retrieved
// search result, rendered as a real external link (href esc'd, opened safely).
const TYPE_ORDER = ["university", "peer-reviewed", "textbook", "official-docs", "reference"];
const TYPE_LABEL = {
  university: "University",
  "peer-reviewed": "Peer-reviewed",
  textbook: "Textbook",
  "official-docs": "Official docs",
  reference: "Reference",
};

function sourceRow(s) {
  const badge = `<span class="src-badge src-${esc(s.type || "reference")}">${TYPE_LABEL[s.type] || "Reference"}</span>`;
  return (
    `<div class="src-item">` +
    `<div class="src-head"><a class="src-title" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.title}</a>${badge}</div>` +
    `<div class="src-note">${s.note || ""}</div>` +
    `<div class="src-url">${esc(s.url)}</div>` +
    `</div>`
  );
}

export function libraryHTML(library) {
  const sources = library.sources || [];
  let body;
  if (!sources.length) {
    body = `<div class="src-empty">No accredited sources were found for this subject yet.</div>`;
  } else {
    const groups = TYPE_ORDER.filter((t) => sources.some((s) => s.type === t)).map((t) => {
      const rows = sources.filter((s) => s.type === t).map(sourceRow).join("");
      return `<div class="src-group"><div class="src-group-label">${TYPE_LABEL[t]}</div>${rows}</div>`;
    }).join("");
    body = groups;
  }
  return (
    `<div class="library">` +
    `<div class="greeting"><h1>Library</h1><span>${esc(library.title || "")}</span></div>` +
    `<section class="card">` +
    `<span class="eyebrow">ACCREDITED SOURCES</span>` +
    `<div class="lib-intro">Authoritative sources this course draws on — retrieved from the web, ` +
    `not invented. Each link was a real search result.</div>${body}</section>` +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div>` +
    `</div>`
  );
}
