# Lesson text highlights — persistent, purely visual — design

**Date:** 2026-07-18. **Status:** approved direction (Werner 11:04 "a nice option to
highlight text in the lesson"; interview answers: persist across visits, purely visual
— no downstream feed into notes/review/mastery; free selection, not paragraph-tap; one
color, not several; approach A — text-search re-anchoring — chosen over offset or
fuzzy-DOM-diff anchoring at 11:22).

## Goal

Select any span of lesson prose (drag to select, exactly like a highlighter or any
native text-selection gesture — desktop click-drag or mobile long-press-drag, no new
interaction model) and mark it. The mark is saved and reappears every time you reopen
the lesson. Tapping an existing highlight removes it. Nothing else reads or reacts to
what's highlighted — it is reading furniture, not a data signal.

## Decisions

1. **Anchoring: store the highlighted text + which occurrence, re-find it by search on
   every render.** A highlight record is `{id, text, occurrence}` — `text` is the exact
   selected substring (as `Selection.toString()` returns it: browsers already flatten
   inline tags like `<strong>`/`<em>`/`<code>` to plain text across a selection, so no
   HTML ever needs to be captured or stored); `occurrence` is the 0-based index of
   *which* match of that exact text this highlight refers to, counted at creation time
   across the lesson's current prose. This resolves the one real ambiguity in a
   text-search approach — the same phrase appearing twice — deterministically: on
   render, find all occurrences of `text` in the container's flattened text content and
   apply the highlight to the one at index `occurrence`, if it exists.
   - **Cache hit (the overwhelming common case — reopening an already-generated
     lesson):** the prose is byte-identical, so every stored highlight's `(text,
     occurrence)` pair matches exactly, every time.
   - **After a regeneration (deepen / "Rusty on this?"):** prose can change completely.
     A highlight whose exact text (at that occurrence index) no longer exists simply
     does not reappear — no error, no misplaced mark, no partial match. This is a
     deliberate accepted trade-off given Werner's explicit "purely visual, low stakes"
     framing: some highlights may silently vanish across a regeneration; none will ever
     point at the wrong sentence. Offset-based anchoring was rejected specifically
     because it can't offer this guarantee (a stale offset lands on whatever text is
     now there, which can be actively misleading); full DOM-range/fuzzy-diff anchoring
     (how production annotation tools like Hypothesis do it) was rejected as
     disproportionate engineering for a feature explicitly scoped as a visual nicety.
   - `id` (a short client-generated token, same idiom as the app's existing `newId()`)
     is the sole key for removal — never derived from `(text, occurrence)` — so removal
     is unambiguous even in the rare case two highlights happen to share both.
2. **Scope: the lesson's own prose only** — specifically `frontend/src/views/lesson.js`'s
   `<div class="prompt">` (the container that already holds `expandFigureTokens`-expanded
   `promptHtml`: paragraphs, lists, tables, figure captions), NOT its parent
   `.lesson-body` wrapper which also contains the exercise/solution/checks sections. A
   selection that starts or ends outside `.prompt` is ignored (no highlight button
   appears); the side-chat/notes workspace panel (`.lesson-side`) is a separate DOM
   subtree entirely and is never reachable from this container.
3. **Storage: a third field on the existing per-lesson workspace file**
   (`content/courses/<course_id>/notes/<lesson_id>.json`, currently `{notes, chat,
   updatedAt}`) — adds `highlights: [{id, text, occurrence}]`. Reuses the file the
   Notes/Chat panel already persists to (one artifact per lesson for everything a
   learner does while reading, not a new precedent) and — critically — reuses that
   file's existing `_MAX_BYTES = 100_000` total-serialized-size cap, so highlights are
   bounded by the same guard with no new magic number. `backend/notes.py` gains
   `_valid_highlights(highlights)` (list; each item a dict with `id` a short safe-token
   string, `text` a non-empty string ≤2000 chars, `occurrence` a non-negative int —
   `bool` explicitly excluded, matching the codebase's existing int-validation idiom)
   mirroring `_valid_chat`'s shape and is-called-from-`save_workspace` pattern exactly.
   `load_workspace`/`save_workspace` gain the `highlights` parameter/field; the
   `GET`/`PUT /api/courses/<cid>/lessons/<lid>/workspace` routes and `frontend/src/
   notes.js`'s `loadWorkspace`/`saveWorkspace` (including its offline localStorage
   cache mirror, so an offline highlight is never silently lost) all thread it through
   alongside `notes`/`chat`.
4. **Save trigger: immediate, not debounced.** Highlighting or removing is a discrete
   action (unlike Notes' continuous typing, which debounces), so each add/remove PUTs
   the workspace immediately — same optimistic-local-cache-first pattern `saveWorkspace`
   already uses for Notes, so an offline highlight still shows instantly and syncs
   later.
5. **Capture + apply mechanics (client-side, no new dependency).**
   - **Capture:** on `selectionchange`/`mouseup` inside the prose container, if the
     current `Selection` is non-collapsed and fully contained within it, show a small
     "Highlight" button positioned near the selection (the standard pattern — Kindle,
     Medium, any e-reader). Tapping it reads `selection.toString()`, computes
     `occurrence` (count of that exact text appearing before the selection's start
     position in the container's flattened text), stores `{id: newId(), text,
     occurrence}`, PUTs the workspace, and applies the mark immediately.
   - **Apply (used both right after creation and on every lesson render):** walk the
     prose container's text nodes in document order, building a running offset into
     the concatenated text; for a target `(text, occurrence)`, find the `occurrence`-th
     match's `[start, end)` range in that concatenation; for every text node the range
     overlaps, split it (`Text.splitText`) so the overlapping portion is its own node,
     and wrap only that portion in a `<mark class="highlight" data-highlight-id="...">`
     — never `Range.surroundContents()`, which fails outright when a range crosses a
     partially-contained element boundary (e.g. a highlight starting mid-way through a
     `<strong>` and continuing past it), exactly the case free-form selection makes
     common. This correctly produces one `<mark>` per involved text node for a
     multi-node highlight — a highlight that visually spans a bold/italic boundary is
     several `<mark>` elements, not one, which is invisible to the reader and doesn't
     need to be a single DOM node.
   - **Remove:** tapping any `<mark>` deletes its `id` from the stored list, PUTs, and
     unwraps just that mark's text node back into its parent (no re-render needed).
6. **No new dependency; pure DOM APIs** (`Selection`, `Range`, `Text.splitText`) — same
   posture as the rest of the frontend (vanilla ES modules, no framework).

## Error handling

- Stored `text` not found in current prose (post-regeneration) → highlight silently
  skipped on render; nothing shown, no error, not deleted from storage (so it's still
  there to reapply if the lesson is ever regenerated back toward similar wording — pure
  bonus, not relied upon).
- `occurrence` out of range (fewer matches now than at creation) → same silent skip.
- Save failure (offline/network) → same optimistic-cache-then-background-sync pattern
  Notes already uses; the mark stays visually applied regardless of save outcome.
- Malformed/oversized PUT body → existing `400`/`413` shape, unchanged from today.

## Security

- Stored `text` is NEVER inserted into the DOM as HTML and never reaches a prompt —
  it's used exclusively as a plain-text search key against text nodes that are already
  part of the server-generated, already-sanitized lesson prose. A hostile stored value
  is inert: worst case it matches nothing (highlight silently doesn't apply) or
  coincidentally matches innocuous existing text (a highlight appears somewhere
  unexpected — cosmetic only, still just the lesson's own real, safe text). DOM
  insertion happens exclusively via `Text.splitText` + wrapping in a plain `<mark>`
  element — never `innerHTML`/`outerHTML` of untrusted content.
- Routes unchanged beyond the existing `_ID_RE` course/lesson-id validation already on
  the workspace endpoints.

## Testing

- **Backend:** `_valid_highlights` accept/reject cases (missing/empty `text`, `text`
  over 2000 chars, non-int/bool/negative `occurrence`, non-string/oversize `id`,
  non-list, list of non-dicts); `save_workspace`/`load_workspace` round-trip
  `highlights` unchanged; the existing `_MAX_BYTES` cap still triggers `WorkspaceTooLarge`
  when highlights push the file over the shared budget; route regression (`notes`/`chat`
  behavior byte-for-byte unchanged when `highlights` is absent from an old client body).
- **Frontend:** pure occurrence-counting helper (given a string and a target index,
  count/locate the Nth match — unit-testable without a DOM); the multi-node
  split-and-wrap apply logic exercised against a small real DOM tree (e.g. a paragraph
  containing a `<strong>` mid-sentence) via node's built-in test environment if it
  supports `Text.splitText`, otherwise flagged for live/Pi verification; selection
  capture guarded to the prose container only (a selection touching the exercise or
  chat area never shows the Highlight button); removal unwraps cleanly; `saveWorkspace`/
  `loadWorkspace` thread `highlights` through including the offline cache mirror; import
  check.
- **Live/Pi verification:** highlight a phrase, reload the lesson, confirm it reapplies;
  highlight a phrase that also appears elsewhere, confirm only the selected occurrence
  is marked; regenerate the lesson (deepen), confirm no error and no misplaced highlight
  (some/all may simply be gone); remove a highlight; offline-then-online save.

## Out of scope

- Multiple highlight colors or categories.
- Any downstream use of highlighted text (notes, spaced repetition, mastery, the
  misconception-profile idea, chat-question analysis) — this is intentionally inert.
- Highlighting inside the exercise, solution, checks, or workspace chat/notes areas.
- Fuzzy/best-effort re-anchoring across a regeneration (accepted: some highlights may
  be lost; none will ever be wrong).
- Exporting or listing all highlights outside the lesson body itself.
