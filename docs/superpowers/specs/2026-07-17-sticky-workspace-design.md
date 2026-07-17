# Sticky lesson workspace — notes/chat that follow the scroll — design

**Date:** 2026-07-17. **Status:** approved (Werner feedback id 3, triaged 21:25: "As I
scroll down the lesson, keep the notes/chat pane following so I don't need to scroll up
to make notes or ask questions"; "please do both" 21:26).

## Goal

The lesson workspace (Notes | Chat panel, today rendered below the lesson body) stays
reachable while reading anywhere in a long lesson — no scrolling back up.

## Decisions

1. **Wide screens (>= 1100px): two-column lesson layout.** Lesson content in the main
   column; the existing workspace panel moves to a right column wrapped in a
   `position: sticky` container (top offset below the topbar) so it follows the scroll.
   Pure CSS + a layout wrapper in the lesson view; the workspace markup, state, tabs,
   debounced note saving, and chat streaming are UNTOUCHED — same DOM ids/classes, same
   `workspaceHTML`, only its position in the layout changes at this breakpoint.
2. **Narrow screens: floating toggle + bottom drawer.** A small fixed-position
   "Notes & Chat" button (bottom-right, lesson screen only) toggles the existing panel
   as a bottom drawer (`position: fixed; bottom: 0; max-height: 60vh; overflow-y: auto`).
   Same DOM node re-styled via a CSS class, not duplicated — one workspace instance,
   one source of state. Button label is plain text, no emojis.
3. **No behavior changes.** Open/tab preferences, seedWorkspace, stale-screen guards,
   socratic/teaching modes, and chat streaming all work exactly as before — the panel
   only *sits* somewhere else. If the workspace is mid-stream when toggled, the stream
   continues (the node is re-styled, never re-created).
4. **Sticky container height** is capped (`max-height: calc(100vh - <topbar+gap>)`) with
   internal scroll, so a long chat never pushes the panel off-screen.

## Error handling / testing

- Pure presentation; no new API surface, no events, no backend change.
- Frontend tests: lesson view renders the layout wrapper + drawer-toggle button; toggle
  class logic (pure helper) tested in node; import-resolution check.
- Manual/Pi verification: desktop width (two columns, panel follows scroll), phone width
  (drawer opens/closes, chat still streams), mid-stream toggle.

## Out of scope

- Any workspace feature change; resizable/collapsible columns; sticky on non-lesson
  screens.
