import { esc } from "../escape.js";

// #1 — real-world evidence capstone. The backend supplies example titles/details +
// a source NAME (never a URL, to avoid hallucinated/dead links); we build a live
// web-search link from title + source so "Explore" always lands on real results.
// title/source are HTML-escaped server-side for safe display; decode them back to
// plain text before encoding into a search query (otherwise "AT&T" -> "AT&amp;T").
function htmlDecode(s) {
  return s
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&#39;/g, "'");
}

function exploreUrl(item) {
  const q = [item.title, item.source].filter(Boolean).map(htmlDecode).join(" ");
  return "https://duckduckgo.com/?q=" + encodeURIComponent(q);
}

export function capstoneHTML(capstone) {
  // title/detail/source/intro arrive server-sanitized; capstone.title is raw -> esc().
  const items = (capstone.items || [])
    .map((it) => {
      const src = it.source ? `<span class="cap-src">${it.source}</span>` : "";
      return (
        `<div class="cap-item">` +
        `<div class="cap-ihead"><span class="cap-ititle">${it.title}</span>${src}</div>` +
        `<div class="cap-detail">${it.detail}</div>` +
        `<a class="cap-explore" href="${esc(exploreUrl(it))}" target="_blank" rel="noopener noreferrer">Explore →</a>` +
        `</div>`
      );
    })
    .join("");
  return (
    `<div class="capstone">` +
    `<div class="greeting"><h1>Real-world connections</h1><span>${esc(capstone.title || "")}</span></div>` +
    `<section class="card"><span class="eyebrow">IN THE REAL WORLD</span>` +
    `<div class="cap-intro">${capstone.intro || ""}</div>${items}</section>` +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div>` +
    `</div>`
  );
}
