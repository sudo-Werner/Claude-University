import { esc } from "../escape.js";

// #accredited-sources — the course "Library": real, web-retrieved accredited sources,
// grouped by type. title/note arrive server-sanitized; the URL is a genuinely retrieved
// search result, rendered as a real external link (href esc'd, opened safely).
const TYPE_ORDER = ["university", "preprint", "peer-reviewed", "textbook", "official-docs", "reference"];
const TYPE_LABEL = {
  university: "University",
  preprint: "Preprint / scholarly",
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
    body = `<div class="src-empty">No grounded sources were found for this subject yet.</div>`;
  } else {
    const groups = TYPE_ORDER.filter((t) => sources.some((s) => s.type === t)).map((t) => {
      const rows = sources.filter((s) => s.type === t).map(sourceRow).join("");
      return `<div class="src-group"><div class="src-group-label">${TYPE_LABEL[t]}</div>${rows}</div>`;
    }).join("");
    body = groups;
  }
  // Phase 2: the live roll-up of sources actually cited across the lessons you've done.
  const lessonSources = library.lessonSources || [];
  let usedSection = "";
  if (lessonSources.length) {
    const rows = lessonSources.map((s) =>
      `<li class="lsrc"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.title}</a>` +
      `<span class="src-badge src-${esc(s.type || "reference")}">${TYPE_LABEL[s.type] || "Reference"}</span></li>`,
    ).join("");
    usedSection =
      `<section class="card"><span class="eyebrow">USED IN YOUR LESSONS</span>` +
      `<div class="lib-intro">The grounded sources the lessons you've done were actually drawn from.</div>` +
      `<ul class="lsrc-list">${rows}</ul></section>`;
  }

  return (
    `<div class="library">` +
    `<div class="greeting"><h1>Library</h1><span>${esc(library.title || "")}</span></div>` +
    usedSection +
    `<section class="card">` +
    `<span class="eyebrow">RECOMMENDED READING</span>` +
    `<div class="lib-intro">Authoritative sources for this subject — retrieved from the web, ` +
    `not invented. Each link was a real search result.</div>${body}</section>` +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div>` +
    `</div>`
  );
}
