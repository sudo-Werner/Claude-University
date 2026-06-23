# Claude University — Empty Start & Add-Course Composer (Slice 3)

**Date:** 2026-06-23
**Status:** Design — awaiting review
**Builds on:** Slice 1 (multi-course foundation) and Slice 2 (course creation + JIT lessons).

## For Werner (plain-language summary)

Two focused changes, no new features:
1. **Start empty.** Remove the seeded Machine Learning course so your university opens
   with no courses — you build everything yourself through the "Add a course" chat.
2. **Fix the "Add a course" page.** The message box is broken (collapsed to a sliver while
   the Send button swallows the whole row) and the page looks sparse. Replace it with a
   proper composer: a roomy multi-line text box in a centered column with a normal-sized
   Send button beneath it, right-aligned.

## Goal

Ship an empty default university and a usable, intentional "Add a course" composer, without
changing any backend course-creation/generation logic.

## Decisions made during brainstorming

- **Remove the seeded ML course** (repo + Pi). The home then shows only the "Add a course"
  card. No course content ships by default.
- **Composer layout:** roomy multi-line textarea in a bounded, centered column; **Send below
  it, right-aligned, normal-sized.** Chat replies render above the composer once a
  conversation starts.

## Root cause of the broken composer

`styles.css` defines the base button as `.btn-primary{ width:100% }`. The composer row
(`.chat-input{ display:flex }`) reuses `.btn-primary` for Send, so the button claims 100% of
the row and collapses the `flex:1` textarea. The lesson nav already works around this with
`.nav .btn-primary{ width:auto }`; the chat input never got an equivalent override. The fix
is a scoped `.chat-input .btn-primary{ width:auto }` plus a column layout — not a change to
the shared button.

## Scope

**In scope**
- Delete `content/courses/machine-learning/` (repo) and remove it from the Pi.
- Rework `tests/test_courses_api.py` so its GET/list/lesson/illegal-id tests build their own
  temporary fixture course (monkeypatch `courses.CONTENT_DIR`, write via `courses.write_course`)
  instead of depending on the seeded course.
- Redesign the composer in `frontend/src/views/chat.js` and `frontend/styles.css`:
  - Bound `.chat-col` to a centered, readable max-width on desktop (consistent with the lesson
    column); full width on phone.
  - `.chat-input` becomes a vertical stack: a full-width multi-line textarea (comfortable
    min-height, glass-field styling matching the theme tokens) above a right-aligned Send row.
  - `.chat-input .btn-primary{ width:auto; … }` so Send is normal-sized (the actual bug fix).
  - Keep the `data-field="chat"` and `data-action="send"` hooks so `app.js` wiring is unchanged.

**Out of scope (unchanged)**
- All backend course-creation, chat-relay, and lesson-generation logic.
- The chat message bubbles, SSE handling, proposal card, JIT loading state.
- Auto-growing the textarea (a fixed comfortable height with native resize is enough — YAGNI).
- The home view (it already renders a clean 0-course state: greeting + count + the add-course
  card; no change needed).
- Streak, FSRS/reviews, login-longevity — all still as-is.

## Components

- **Content:** the `machine-learning` course directory is removed; nothing replaces it. The
  lesson schema still lives in code/tests, so no structural knowledge is lost.
- **`tests/test_courses_api.py`:** a small helper writes a fixture course into a tmp content
  dir (monkeypatched) and the existing assertions target that course's id/lesson instead of
  `machine-learning`. This makes the API tests self-contained rather than seed-dependent.
- **`frontend/src/views/chat.js`:** `chatHTML` keeps its structure (greeting, thread,
  composer) but the composer markup becomes a textarea + a Send row; same data hooks.
- **`frontend/styles.css`:** `.chat-col` bounded/centered; `.chat-input` restyled to a column
  composer; scoped Send override.

## Testing

- **Backend:** `tests/test_courses_api.py` reworked tests pass against a self-created fixture
  course; the full backend suite stays green with the ML course gone.
- **Frontend:** existing `node --test` suites stay green (none depend on the ML course *file*;
  `chat.test.js` tests `parseSSELines`, unaffected).
- **Real-browser (Playwright):** open from the Pi → home shows an empty university (just the
  add-course card) → open "Add a course" → the composer renders correctly (roomy textarea,
  right-sized Send) at phone and desktop widths → typing + Send still streams a reply.
- **Deploy:** rsync to the Pi, remove the ML course dir there, restart, verify the empty home
  and working composer over Tailscale.

## Self-review notes

- **Bug fix is scoped, not global:** the Send override is `.chat-input`-scoped, mirroring the
  existing `.nav .btn-primary` precedent — the shared button is untouched.
- **No backend logic change:** only content removal + a test-fixture rework + CSS/markup.
- **Tests made self-contained:** removing seed-dependence from the API tests is a genuine
  improvement, not just accommodation.
- **YAGNI:** no auto-grow, no home empty-state redesign, no new dependencies.
