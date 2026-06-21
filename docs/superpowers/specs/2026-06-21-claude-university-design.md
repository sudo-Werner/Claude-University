# Claude University — Personal Learning Platform

**Design spec** · 2026-06-21 · Owner: Werner van Ellewee · Instructor/analyst: Claude

## 1. What this is

A personal, self-owned learning platform — Werner's own "university" — built as a
**reusable, topic-agnostic learning engine** with **content packs** plugged in as data.
The first content pack is the **Machine Learning A-Z** curriculum. Future topics
(statistics, a language, anything) become new packs without rebuilding the engine.

Claude plays two roles: **author** of the content (to a defined quality bar) and
**analyst** of Werner's learning data between sessions.

The defining edge over off-the-shelf tools is not any single component (those exist and
are mature) but the **integration and ownership**: one honest event log that drives live
adaptation, a personal insight dashboard, and Claude-mineable raw data — all stored on
hardware Werner controls, forever.

## 2. Decisions locked during brainstorming

| Decision | Choice | Why |
|---|---|---|
| Core vision | Reusable engine; ML is pack #1 | Pays off on every future topic |
| Metrics purpose | All three: live adaptation + personal dashboard + raw mineable log | One event stream feeds all three; they reinforce, not compete |
| Data home | Pi service, offline-first browser buffer → sync → SQLite | Always-on, multi-device via Tailscale, Claude-readable between sessions |
| Storage format | SQLite (single `.db` file) | Real queries on learning patterns; scales for years |
| Spaced repetition | **FSRS** (not naive 1→3→7→21) | SOTA, evidence-based, learns personal forgetting curve; mature Python impl |
| Mastery model | BKT-style running mastery estimate | Routes depth + reveals recall-vs-recognition gap (better than one-off quiz score) |
| Content depth bar | Deep intuition/the why + applied SOTA practice | Matches how Werner learns; light math only where it sharpens intuition |
| Frontend | Static web app (HTML/CSS/JS, no build step, no framework) | Simplest that works; served by the Pi |
| Backend | Small Python service (Flask + SQLite) on the Pi | Matches existing Pi infra pattern (Involo, trading, HA) |
| Handover doc | Superseded; keep its raw material, drop its architecture | Old framing (ML-only, localStorage) fought the cleaner design |
| In-app "I'm stuck" tutor | Embedded ephemeral Claude Agent SDK session, briefed from the event log | Highest-value live moment; arrives knowing where you're stuck |
| Tutor auth | Subscription OAuth, behind a **swappable auth adapter** | No per-token cost now; one-line swap to an API key if the grey area bites |

## 3. System shape

Four cleanly separated parts so any can change without breaking the others:

1. **The Engine (frontend)** — static web app. Knows *how to teach*: run a pre-quiz,
   route lesson depth, run concept checks, schedule spaced reviews, run the session timer,
   show the dashboard. Knows nothing about ML specifically.
2. **Content packs (data)** — each topic is a folder of JSON/markdown: lessons, quizzes,
   exercises, Feynman prompts. ML A-Z is pack #1. New topics = new packs.
3. **The Pi service (backend)** — small Flask + SQLite service that (a) serves the web app
   and (b) receives and stores the event log. Always on; reachable from laptop/phone via
   Tailscale (`100.99.33.106`) or LAN (`192.168.2.69`); readable by Claude over SSH.
4. **The in-app tutor (live, on demand)** — an "I'm stuck" button spins up an ephemeral
   **Claude Agent SDK** session, streamed into a chat panel in the lesson screen, torn down
   when closed. The Pi service briefs it from the event log at spawn (current topic, the
   exact concept, the question just missed, the learner profile) so it arrives pre-oriented.
   The exchange logs back to the event stream. This is the one **runtime LLM dependency** —
   the rest of the app stays self-contained; only this feature needs to reach Claude.
   Auth goes through a **swappable adapter** (default: subscription OAuth; one-line swap to
   an API key). Model: `claude-sonnet-4-6` (interactive — favours responsiveness).

**Data flow:** open one URL (the Pi) on any device → it serves the engine → engine loads the
content pack → every event writes to a **localStorage buffer instantly**, then a background
sync flushes to the Pi. Pi down or offline? Learning continues; the buffer flushes on
reconnect. SQLite on the Pi is the single source of truth.

**Onboarding consequence:** the 6-question diagnostic becomes the app's **first-run screen**,
not a chat interview. The profile is captured, stored, and *versioned* in the same data layer,
so changed preferences are a new record — and we can later compare stated preferences against
actual behaviour.

## 4. The event log (measurement)

One append-only event stream in SQLite. Nothing computed-and-discarded, so new questions can
be asked of old data. Each event: time, device, session id, topic id, type, details blob, and
a client-side id for idempotent re-sync.

**Captured:**
- **Session shape** — start/end, time of day, device, position in 90-min arc (warm-up/peak/cool-down)
- **Pre-quiz** — each answer, correct?, latency, routed depth
- **Lesson** — sections viewed, depth, time spent
- **Concept checks** — answer, correct?, latency, hints used
- **Exercises** — attempted, solution revealed?, time
- **Feynman** — the explanation text + self-rating
- **Spaced reviews** — card, recall quality (1–5), latency
- **Metacognition** — "get it vs recognise it" checkpoints
- **Struggle signals** — stuck past threshold, chose review-prereq, skipped
- **Tutor sessions** — "I'm stuck" opened (topic + concept + missed question it was briefed with),
  duration, and the transcript, so struggle → resolution becomes data

**Derived (not stored separately):**
- Personal **forgetting curve** per topic (times reviews to Werner via FSRS)
- **Accuracy by time of day** and by position in session
- **Recall-vs-recognition gap** (right MCQ but weak Feynman = fragile knowledge, flagged)
- **Struggle hotspots** (costliest concepts)
- **Profile-vs-behaviour drift** (stated strategy vs actual behaviour)

The dashboard and live adaptation are just two readers of this one stream.

## 5. Adaptation + learning-science mapping

Two separable engines plus the profile, each answering a different question:

- **Engine A — FSRS (when to review).** Learns Werner's forgetting curve from review ratings;
  schedules each card for the moment before forgetting. Python impl in the Pi service.
- **Engine B — Mastery estimate, BKT-style (does he actually know it?).** Running probability of
  mastery per concept, updated by every answer. Routes lesson depth and decides when a topic is
  truly done. Surfaces the recall-vs-recognition gap.
- **The profile (style knobs).** From the diagnostic: content order (theory/examples-first),
  wrong-answer feedback (immediate/hint/self), stuck strategy, lesson structure (top-down/bottom-up),
  analogies on/off, session style (deep block/sprints).

| Principle | Mechanism |
|---|---|
| Active recall | Quiz *before* each lesson; free-recall before reveal |
| Spaced repetition | FSRS (personalised) |
| Desirable difficulty | Struggle-before-reveal; no free answers; hints gated by profile |
| Interleaving | Review sessions mix concepts across a lightweight concept graph (prereq links) |
| Cognitive load | Max 2–3 new concepts/session; enforced by pack chunking |
| Feynman (g≈0.55) | "Explain it back" captured as text + self-rating; feeds mastery |
| Flow / session arc | 90-min timer with warm-up → peak → cool-down events |
| Metacognition | "Get it vs recognise it" checkpoints compared against actual mastery |
| Fatigue (from OpenTutor) | Derived from latency drift + error clustering + session length → suggest a break |
| VARK learning styles | **Not implemented** (debunked) |

**MVP vs later (YAGNI line — log everything from day one, act only on validated signals):**
- **MVP:** FSRS, profile-driven style, a simple mastery estimate, full event log, fatigue *signal logging*.
- **Later:** richer concept-graph review (LECTOR/LOOM-style), automatic fatigue *intervention*,
  profile-vs-behaviour drift reports.

### Claude's role in the running system

The app's in-the-moment adaptation is deterministic (FSRS + mastery + profile) — no LLM at
runtime except the on-demand tutor. Claude's ongoing roles are otherwise **asynchronous**,
via Claude Code with SSH access to the Pi:
- **Author** — write content packs ahead of Werner (research → draft → verify → provenance).
- **Analyst / coach** — read the event log between sessions and report what it shows
  (retention, fragile knowledge, struggle hotspots, peak time of day, profile-vs-behaviour drift),
  each with a recommendation.
- **Tuner / maintainer** — act on the analysis; refresh stale (provenance-flagged) lessons; keep
  the Pi service healthy.
- **On-call tutor (live, in-app)** — the "I'm stuck" Agent SDK session (see §3, component 4).

## 6. Content authoring standard

Every topic produced by the same pipeline so quality is consistent:
1. **Research** — web-verify current best practice for currency-sensitive areas (libraries, APIs,
   the AWS track); draft timeless theory directly. (Claude's knowledge cutoff is Jan 2026.)
2. **Draft to the depth bar** — deep plain-language intuition + the *why* + trade-offs, paired with
   applied 2026 practice and real gotchas. Math only where it sharpens intuition.
3. **Verify** — accuracy pass before embedding.
4. **Stamp provenance** — each lesson records date authored, sources, library versions, so a single
   stale lesson can be refreshed without rewriting the pack.

**Per-topic file contains:** pre-quiz; adaptive depth (routed by mastery, not raw score); Python
code (copy-paste for MVP; in-browser Pyodide playground is a *later* enhancement); concept checks;
an exercise with a gated solution; a Feynman prompt; dig-deeper links. Content lives as data files
in the pack folder, fully separate from the engine.

"Comprehensive" = coverage + accuracy, **not** delivery speed; learning-science pacing still governs
how content arrives.

## 7. UI/UX

**Principles:**
- Dark theme; accent purple `#7c6aff` + blue `#4fc3f7`; `system-ui` font; no external CSS frameworks.
- The UI must *reduce* cognitive load: one primary action per screen; progressive reveal (answer
  before any solution; hints gated).
- Session arc visible (timer; warm-up/peak/cool-down).
- Mobile-friendly (phone use via Tailscale).
- Friction-free daily entry: open URL → "Today's session" is immediately actionable.

**Screen inventory:**
- **Dashboard** (daily) — today's session, overall progress, streak, 90-min timer, reviews-due count.
- **Lesson flow** (daily) — pre-quiz → adaptive lesson body → inline concept check → exercise with
  gated solution → "explain it back" box.
- **Review session** — FSRS cards.
- **Onboarding diagnostic** (one-time) — the 6 questions → profile.
- **Insight dashboard** (reflective) — learning-pattern analytics.

First design pass targets the two daily screens (Dashboard + Lesson flow); onboarding and analytics
follow.

**Design → build handoff (Claude design in browser ↔ Claude Code in VS Code):**
The two tools share no memory; the **project folder is the bridge**. Loop:
1. Werner designs in the browser → exports into the project: a **design-tokens spec** (source of
   truth), **screenshots** per screen (visual target, saved to `content/design/`), and **raw HTML/CSS**
   (value reference only — rebuilt cleanly, not shipped as-is).
2. Claude implements against spec + screenshots using the frontend-design skill.
3. Claude uses Playwright to open the running platform, screenshot each screen, and self-compare
   against the reference shots before Werner looks.
4. Werner reviews in browser; feedback returns as notes or a fresh screenshot in the folder.

A paste-ready brief for the design tool lives at `docs/design-brief.md`.

## 8. Build phasing

This spec covers the **engine + first content pack (Slice 1)** — one complete working vertical slice.
Remaining ML phases are follow-on content cycles, each its own spec→plan→build.

- **Slice 0 — Foundation:** Pi service (Flask + SQLite + sync API), engine shell, onboarding
  diagnostic, end-to-end event logging — proven with one real lesson.
- **Slice 1 — First real learning:** Phase 1 ML content (Python/data refresher, NumPy/Pandas,
  Data Preprocessing) to standard + FSRS reviews + mastery routing + dashboard v1. **First usable
  product — Werner starts studying here.**
- **Slice 1b — In-app tutor:** the "I'm stuck" Agent SDK tutor (briefed from the event log,
  swappable auth). Last piece of the first usable phase; the deterministic core works without it,
  so it can ship just after Slice 1 rather than blocking it.
- **Slice 2+ — Expand:** remaining ML phases as content; deeper dashboard; later adaptation features
  switched on once real data justifies them.

## 9. Tech summary

| Layer | Choice |
|---|---|
| Frontend | Static HTML/CSS/JS, no framework, no build step |
| Backend | Flask + SQLite on WernerPi (systemd service) |
| Spaced repetition | FSRS (Python implementation) |
| Mastery | BKT-style estimate |
| In-app tutor | Claude Agent SDK (ephemeral sessions), spawned by the Pi service; model `claude-sonnet-4-6` |
| Tutor auth | Swappable adapter — subscription OAuth (default) or API key |
| Storage | Single SQLite `.db` (append-only event log + derived state) |
| Access | LAN `192.168.2.69`; Tailscale `100.99.33.106`; Claude via `mcp__pi-ssh__exec` / SSH |
| Sync | Offline-first localStorage buffer → background flush, idempotent by client event id |

## 10. Out of scope (for this spec)

- ML phases 2–7 content (follow-on cycles)
- In-browser Python playground (Pyodide) — later enhancement
- Automatic fatigue intervention, concept-graph review, drift reports — later
- **Scheduled "learning review" automation** — a recurring Claude job that reads the Pi log and
  writes a report. Later; subscription-auth Agent SDK is fine for a personal scheduled job, API
  key if it ever scales to an always-on service.
- Multi-user / sharing — single user (Werner) only

## Appendix — preserved from the handover

- **Learner profile config:** `contentOrder`, `stuckStrategy`, `wrongAnswerFeedback`,
  `sessionStyle`, `lessonStructure`, `analogies` (captured via the 6-question diagnostic).
- **Curriculum:** 7 phases / 36 weeks / ~5 hrs/week, 15 ML A-Z topics + AWS track (see handover).
- **Lesson JSON shape:** id, title, prereqs, preQuiz[], content{beginner,intermediate},
  codeExample, exercise{prompt,starterCode,solution}, feynmanPrompt, digDeeperLinks[].
