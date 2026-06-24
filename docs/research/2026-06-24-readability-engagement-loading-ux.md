# Research — Readability/Engagement + Loading-State UX (2026-06-24)

For review items #3 (make content easier to read / more entertaining) and #3b
(better loading states). Source: background research agent, web-sourced. Feeds the
proposal in [docs/superpowers/specs] and the engagement/loading slices.

## AREA 1 — Readability & Engagement (ranked: leverage / effort)

1. **Conversational tone (personalization principle) — GENERATION PROMPT.**
   Mayer: learners score higher on transfer when text uses conversational, 2nd-person
   "you" style vs formal. Best-evidenced, lowest-cost, non-gamified. Prompt change.
   refs: researchgate A_Personalization_Effect_in_Multimedia_Learning; eric EJ944963
2. **Chunking + scannable structure — GENERATION PROMPT (+ minor CSS).**
   NN/g: 79% of users scan. Short labelled chunks, bullets, bolded key terms. Critical
   at 448px. refs: nngroup progressive-disclosure; yoast scannable-content
3. **Worked example → faded practice — GENERATION PROMPT.**
   Novices learn better studying a full structured solution (steps + reasoning), then
   fading scaffolds. Solution should be a worked example, not just an answer.
   refs: wikipedia desirable_difficulty; structural-learning desirable-difficulties
4. **Progressive disclosure of hints/solution — UI/CSS.**
   Keep initial view minimal (prompt + answer). Don't exceed ~2 disclosure levels.
   App already does this. ref: nngroup progressive-disclosure
5. **Learn-by-doing / attempt-before-teaching (Brilliant) — GENERATION PROMPT.**
   Pose problem before teaching; instant specific feedback. App's answer-gate already
   embodies it; lean in. refs: screensdesign Brilliant; buffalo active-learning
6. **Varied / interleaved question formats — GENERATION PROMPT.**
   Interleave formats (recall/apply/spot-error/compare) for retention. Caveat:
   overwhelms novices — keep early lessons blocked. refs: ncbi PMC8476370; wiley 12659
7. **Warm, empathetic feedback microcopy (Duolingo, minus gimmicks) — UI text + PROMPT.**
   "Almost there!" not "Wrong." Empathetic, specific, never punitive — adopt the
   writing without streaks/mascots/points. refs: 925studios duolingo; userguiding duolingo
   (weak/mixed evidence, deprioritized: concrete-before-abstract.)

## AREA 2 — Loading-State UX for AI generation (multi-second waits)

1. **Skeleton screen of the lesson layout — UI/CSS (cheap).** ~30–50% perceived-perf
   gain, lower bounce; render greyed placeholder blocks + CSS shimmer. No backend.
   refs: logrocket skeleton-loading-screen; onething skeleton-vs-spinners
2. **Staged status narration ("Reading topic… Writing exercise… Preparing hints…") —
   UI/CSS+JS (cheap).** NN/g: past ~10s show progress/explanatory text; users tolerate
   ~3× longer waits. setInterval swapping honest messages. ref: nngroup progress-indicators
3. **Stream / typewriter (optimize TTFT) — BACKEND STREAMING.** Perceived wait driven by
   time-to-first-token; streaming cuts perceived wait up to ~70%, reduces abandonment,
   reads as "thinking." Highest impact, highest cost (SSE + incremental DOM). Worth it
   if generation routinely >5–10s. refs: pockit streaming-llm; redis streaming-llm
4. **Progress-bar psychology (if used) — UI/CSS.** Start slow, accelerate to completion;
   only if mappable to real stages, else prefer #2. ref: nngroup progress-indicators

**Effort summary:** skeleton (#1) + staged messages (#2) are pure HTML/CSS/JS and give
most of the perceived-speed benefit — do first. Streaming (#3) is the ceiling but needs
backend work. Avoid a lone indeterminate spinner for >10s waits.

Note: app runs plain HTTP over Tailscale (no secure-context APIs) — but skeletons,
staged text, shimmer, and SSE all work fine over plain HTTP. Nothing here is blocked.
