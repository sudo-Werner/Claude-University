// Lesson prose highlights — persistent, purely visual (design doc Decision 1-6).
// Anchoring: a highlight is {id, text, occurrence} where `occurrence` is the 0-based
// index of WHICH match of `text` this highlight refers to, counted across the
// container's flattened text content. This resolves the one real ambiguity in a
// text-search approach (the same phrase appearing twice) deterministically, and means
// a highlight either lands on the exact right sentence or doesn't show at all — never
// on the wrong one (unlike a stale character offset, which always lands on SOMETHING).

// Returns the [start, end) character range of the `occurrence`-th (0-based)
// non-overlapping match of `needle` in `haystack`, or null if there is no such match
// (fewer than occurrence+1 occurrences exist, or needle is empty).
export function findNthOccurrence(haystack, needle, occurrence) {
  if (!needle || occurrence < 0) return null;
  let from = 0;
  for (let i = 0; i <= occurrence; i++) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1) return null;
    if (i === occurrence) return [idx, idx + needle.length];
    from = idx + needle.length;
  }
  return null;
}

// Counts how many non-overlapping matches of `needle` occur in `haystack` strictly
// before `beforeIndex` -- used at highlight-creation time to compute the `occurrence`
// index for a freshly-selected span, given its start offset in the flattened text.
export function countOccurrencesBefore(haystack, needle, beforeIndex) {
  if (!needle) return 0;
  let count = 0;
  let from = 0;
  for (;;) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1 || idx >= beforeIndex) return count;
    count++;
    from = idx + needle.length;
  }
}

// Walks `container`'s text nodes in document order, returning the concatenated text
// plus a parallel list of {node, start, end} offset ranges (each node's slice of that
// concatenation). This is the "flattened text with an offset map" that apply/capture
// search and split against. DOM-dependent: needs a real Document (TreeWalker).
export function flattenTextNodes(container) {
  const walker = container.ownerDocument.createTreeWalker(container, 4 /* NodeFilter.SHOW_TEXT */);
  const nodes = [];
  let text = "";
  let node;
  while ((node = walker.nextNode())) {
    const start = text.length;
    text += node.nodeValue;
    nodes.push({ node, start, end: text.length });
  }
  return { text, nodes };
}

// Applies one highlight -- {id, text, occurrence} -- to `container` by finding the
// occurrence-th match of `text` in the container's flattened text content and wrapping
// the matching text-node portions in `<mark class="highlight"
// data-highlight-id="...">`. Splits any text node the match only partially covers
// (Text.splitText) so ONLY the matched substring is wrapped -- never
// Range.surroundContents(), which throws when a range partially contains an element
// (routine for a free-form selection that starts or ends mid-tag). Silently does
// nothing if the text/occurrence isn't found (the accepted trade-off: never show a
// highlight in the wrong place). Returns true if applied, false if skipped.
export function applyHighlight(container, highlight) {
  const { text, nodes } = flattenTextNodes(container);
  const range = findNthOccurrence(text, highlight.text, highlight.occurrence);
  if (!range) return false;
  const [start, end] = range;
  const doc = container.ownerDocument;
  for (const entry of nodes) {
    if (entry.end <= start || entry.start >= end) continue; // no overlap with [start, end)
    let node = entry.node;
    const localStart = Math.max(0, start - entry.start);
    const localEnd = Math.min(node.nodeValue.length, end - entry.start);
    if (localEnd < node.nodeValue.length) node.splitText(localEnd); // keep only the overlap
    if (localStart > 0) node = node.splitText(localStart);
    const mark = doc.createElement("mark");
    mark.className = "highlight";
    mark.setAttribute("data-highlight-id", highlight.id);
    node.parentNode.insertBefore(mark, node);
    mark.appendChild(node);
  }
  return true;
}

// Applies every highlight in `highlights` to `container` -- used both right after
// creating a new highlight and on every lesson render. Order doesn't matter: each
// call re-flattens the CURRENT text nodes, so an earlier highlight's inserted <mark>
// just becomes part of the next flattening pass (its wrapped text still contributes
// its own characters at its own offset, so later occurrence-counting is unaffected).
export function applyHighlights(container, highlights) {
  for (const h of highlights || []) applyHighlight(container, h);
}

// Removes one highlight's <mark> elements (there can be more than one per highlight --
// see applyHighlight's per-text-node wrapping) by unwrapping each back into its
// parent, given the highlight's id. Filters by dataset in JS rather than interpolating
// highlightId into a querySelectorAll selector string, so a highlight id can never be
// treated as selector syntax.
export function removeHighlightMarks(container, highlightId) {
  container.querySelectorAll("mark.highlight[data-highlight-id]").forEach((mark) => {
    if (mark.dataset.highlightId !== highlightId) return;
    const parent = mark.parentNode;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
  });
}
