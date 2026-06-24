# Claude University — Content-Quality Safeguards & Resilience (Slice 8)

**Date:** 2026-06-24
**Status:** Design — self-approved under the build charter (see [CHARTER.md](../../CHARTER.md))
**Builds on:** Slices 1–7. Closes roadmap done-items 7 + 8 — the **last planned slice**.

## For Werner (plain-language summary)

Two robustness fixes plus tidy-up, to make the platform hold up unattended:
1. **"Re-authenticate" instead of silent failure.** The Pi generates lessons through your Claude
   Max login (`claude -p`). If that login ever expires, today you'd get a vague "couldn't prepare
   this lesson". This slice **detects the auth failure specifically** and tells you clearly that the
   Pi needs you to log in again (`claude` on the Pi) — on the lesson screen and in the course-creation
   chat — so a stale login is obvious, not mysterious.
2. **Reject obviously-empty lessons.** Generation already checks the lesson's shape; now it also
   rejects a lesson whose learner-facing text came back empty, and regenerates — catching a bad
   generation before you ever see it. (No extra AI call — that would double the Pi's work for little
   gain; just a stricter check on what's already produced.)
3. **Loose ends:** remove the leftover "12-day streak" placeholder (streak was dropped as
   not-useful for one learner), and let lessons use a horizontal rule (`<hr>`) the generator already
   writes (it currently shows as literal text).

## Decisions made (self-approved under charter)

- **Auth detection keys on the CLI's `api_error_status` (401/403) + text markers.** Verified against
  a real failed call: `claude -p --output-format json` on bad auth exits non-zero with stdout JSON
  containing `"api_error_status":401` and `"result":"Invalid API key · Fix external API key"` (the
  401 is in **stdout**, which the current error path ignores — it only kept stderr). A new
  `ClaudeAuthError(ClaudeError)` carries a clear message; callers surface it distinctly.
- **No LLM self-review pass.** The roadmap's "self-review/regenerate-on-obvious-failure" is done with
  a cheap **heuristic** (reject empty/whitespace learner-facing fields) feeding the *existing*
  `run_structured` retry — not a second Claude call per lesson. A real self-review would roughly
  double per-lesson generation cost on a constrained Pi: rejected as Pi-heavy / YAGNI.
- **Streak is removed, not wired to data.** Research already flagged it as zero-value for a single
  AI-taught learner; the placeholder is deleted (top-bar pill + dashboard strip + the constant).
- **`<hr>` joins the sanitizer allowlist** as a void tag (like `<br>`) — attribute-less, not an XSS
  vector — so the divider the generator emits renders instead of showing as literal `<hr>`.

## Architecture

1. **Auth detection (`backend/claude_client.py`).**
   - `class ClaudeAuthError(ClaudeError)`.
   - `_auth_failure_reason(stdout, stderr) -> str | None`: parse `stdout` as JSON; if
     `api_error_status` in `{401, 403}` return its `result` (or a default); else scan
     `stdout`+`stderr` (lowercased) for markers (`invalid api key`, `unauthorized`, `401`,
     `please run /login`, `/login`, `log in`, `oauth`, `authentication_error`, `expired`,
     `not logged in`). Return `None` if no auth signal.
   - `_run_cli`: on **non-zero exit** raise `ClaudeAuthError(reason)` when
     `_auth_failure_reason(stdout, stderr)` is set, else the existing `ClaudeError`; also on exit 0,
     defensively raise `ClaudeAuthError` if the stdout envelope still signals auth failure (covers an
     `is_error` envelope returned with exit 0).
   - Streaming (`_spawn_cli`/`stream`): best-effort — `stream()` raises `ClaudeAuthError` if any
     stream line's JSON carries `api_error_status` in `{401,403}`; `_spawn_cli` raises
     `ClaudeAuthError` on non-zero exit when stderr matches markers. (Noted best-effort: the stored
     login is currently valid, so the streaming-expiry path can't be reproduced now.)

2. **Content-quality tightening (`backend/generation.py`).**
   - `valid_check`: in addition to the current checks, require `prompt` and `explanation` to be
     non-empty after `.strip()`; for `mcq` every choice non-empty; for `fill` `answer` non-empty.
   - `valid_lesson`: additionally require the learner-facing prose fields `promptHtml`, `hintHtml`,
     `solutionAns`, `solutionNote` to be non-empty after `.strip()`. (Structure/keys/checks as
     today.) This feeds the existing `run_structured` single retry — regenerate-on-empty.
   - Sanitizer: add `hr` to the void-tag set so `<hr>`, `<hr/>`, `<hr />` restore to `<hr>`.

3. **Surfacing (`backend/app.py`, `backend/generation.py`).**
   - Lesson route `get_lesson`: catch `ClaudeAuthError` **before** the generic `ClaudeError` →
     `503` with `{"error": "Claude needs re-authentication on the Pi — run `claude` there to log in
     again.", "code": "reauth"}`.
   - `chat_sse`: catch `ClaudeAuthError` separately and emit the same re-auth message in the
     `event: error` payload (the generic catch stays for other failures).

4. **Frontend.**
   - **Remove streak:** `shellHTML` drops the `streakDays` param + `.streak` pill; `dashboardHTML`
     drops the `.streak-strip`; `app.js` removes the `STREAK_DAYS` constant and all `streakDays`
     args.
   - **Surface lesson-load failure (`courses.js` + `app.js`):** `loadLesson` returns `{ error }`
     (from the response body, falling back to a generic message) instead of `null` on a failed
     response. `openLesson` renders an inline error card (the message + a Back button) on the lesson
     screen instead of silently returning to the course; `startReviewSession`/`advanceAfterLesson`
     treat the error like a load failure. A real lesson object never has an `error` key, so it is a
     safe discriminator.

## Data flow (auth failure)

```
claude -p (expired login) ─▶ exit≠0, stdout {api_error_status:401, result:"Invalid API key…"}
   _run_cli detects 401 ─▶ raise ClaudeAuthError
      lesson route ─▶ 503 {error:"…re-authenticate…", code:"reauth"} ─▶ loadLesson {error} ─▶ inline message
      chat_sse ─────▶ event: error {message:"…re-authenticate…"} ─▶ chat shows it
```

## Testing

- **claude_client:** `_auth_failure_reason` detects the real 401 envelope (the captured
  `{"api_error_status":401,"result":"Invalid API key · Fix external API key"}`) and the text
  markers; returns `None` for a normal success envelope. `_run_cli` (with a fake runner/`subprocess`
  double) raises `ClaudeAuthError` on a 401 envelope (non-zero exit and exit-0 is_error) and plain
  `ClaudeError` on a non-auth non-zero exit. `stream` raises `ClaudeAuthError` on a 401 stream line.
- **generation:** `valid_check`/`valid_lesson` reject empty/whitespace learner-facing fields and
  still accept good ones; `sanitize_html` keeps `<hr>`/`<hr/>` and still blocks dangerous markup;
  `chat_sse` emits the re-auth message on `ClaudeAuthError`.
- **app:** the lesson route returns `503` + `code:"reauth"` when generation raises
  `ClaudeAuthError` (inject a generate that raises).
- **Frontend (pure):** `shellHTML`/`dashboardHTML` no longer render streak markup; (lesson-load
  error surfacing is app.js wiring — browser-verified).
- **Real-browser + Pi:** normal generation still works (login valid); a created course's lesson
  renders an `<hr>` divider correctly; the streak pill/strip are gone. (The live 401 path can't be
  triggered without breaking the Pi login, so it is covered by unit tests against the captured real
  output, not e2e.)

## Out of scope (deferred)

- A genuine LLM self-review/grader pass (Pi-heavy; heuristic chosen instead).
- Auto-recovery of the Pi login (re-auth is interactive by design); we only *detect + surface* it.
- A real streak/stats engine (dropped — YAGNI for one learner).
- Generated course metadata (objectives/difficulty), desktop layout — still deferred from Slice 7.

## Self-review notes

- **Grounded detection** — the 401 signal and message text come from a real failed `claude -p` call,
  not a guess; the lesson path (the main generation path) is unit-tested against that exact output.
- **Pi-light** — no extra LLM calls; the quality check is pure string logic, the retry already
  existed.
- **No silent failure** — auth + load failures now surface clearly on both the lesson screen and the
  chat, the explicit goal of this slice.
- **Closes the roadmap** — after this, all planned slices are shipped; the hourly loop shifts to a
  quality/maintenance pass.
