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

const MET_LABEL = { met: "Met", partial: "Partially met", unmet: "Not met" };

// criterion/note/summary arrive server-sanitized -> render raw; evidence is a
// verbatim quote of the learner's own submission -> esc() client-side.
function capResultHTML(result) {
  if (!result) return "";
  if (result.error) return `<div class="grade grade-soft">${esc(result.error)}</div>`;
  const rubric = result.rubric || [];
  const rows = (result.perCriterion || [])
    .map((g) => {
      const crit = rubric[g.index] ? rubric[g.index].criterion : "";
      const evidence = g.evidence ? `<div class="cap-evidence">"${esc(g.evidence)}"</div>` : "";
      return (
        `<div class="cap-crit">` +
        `<div class="cap-chead"><span class="cap-cname">${crit}</span>` +
        `<span class="cap-badge cap-badge-${esc(g.met)}">${MET_LABEL[g.met] || esc(g.met)}</span></div>` +
        `<div class="cap-note">${g.note || ""}</div>${evidence}</div>`
      );
    })
    .join("");
  const pct = Math.round((result.score || 0) * 100);
  const banner = result.passed
    ? `<div class="exam-banner pass">Passed — ${pct}%</div>`
    : `<div class="exam-banner fail">Not passed — ${pct}% (70% needed)</div>`;
  return `${banner}${rows}<div class="cap-summary">${result.summary || ""}</div>`;
}

function submitCardHTML(state) {
  const canSend = !!(state.work || "").trim() && !state.busy;
  const graded = !!(state.result && !state.result.error);
  const body = state.busy
    ? `<div class="grade grade-loading" aria-live="polite"><span class="grade-spin"></span><span>Grading against the rubric…</span></div>`
    : capResultHTML(state.result);
  return (
    `<section class="card cap-submit"><div class="checks-title">Submit your work</div>` +
    `<div class="pq-lead">Apply what you studied: write or paste a piece of your own work for this capstone. It is graded against a rubric — 70% passes, unlimited attempts.</div>` +
    `<textarea data-field="cap-work" placeholder="Your work…">${esc(state.work || "")}</textarea>` +
    `<button class="btn-primary" data-action="cap-submit"${canSend ? "" : " disabled"}>` +
    `${state.busy ? "Grading…" : graded ? "Submit again" : "Submit for grading"}</button>` +
    `${body}</section>`
  );
}

export function capstoneHTML(capstone, state = {}) {
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
    submitCardHTML(state) +
    `<div class="nav"><button class="btn-back" data-action="back">Back</button></div>` +
    `</div>`
  );
}
