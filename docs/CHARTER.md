# Claude University — Build Charter

**Established:** 2026-06-23 (Werner's directive)
**Status:** Active

## The goal (Werner's words)

> "Build this university to our vision, use Udemy and other such like online universities for
> reference on style and data management, and finish building this system. If you really need
> my input I'm here, but try to get it done."

## Vision (one paragraph)

A personal, AI-driven university where Werner creates courses by conversing with Claude, and the
platform teaches with learning-science rigor — generated lessons, spaced repetition, adaptivity
to performance, and clear progress/mastery tracking — as a calm, focused, daily-use study app
running on his Pi. It should feel as polished and legible as a real online university (Udemy /
Coursera), built for one learner.

## Definition of done (the gaps to close)

Closing these is "finished." Ordered roughly by leverage; sequencing lives in [ROADMAP.md](ROADMAP.md).

1. **Spaced repetition / review engine** — schedule reviews (FSRS-style), drive "reviews due,"
   bring past material back. The biggest missing learning pillar.
2. **Adaptivity** — lessons and routing respond to how the learner performed (mastery routing),
   not just the static profile + brief.
3. **Answer checking + feedback** — grade/respond to the learner's answer, not pure self-assessment.
4. **Richer lesson structure** — pre-quiz → chunked concepts → concept check → exercise →
   explain-it-back, per the original design brief and real lesson-player UX.
5. **Course/data-model maturity** — sections/modules, lesson types, resources, notes, ratings,
   prerequisites — adopting what online universities do *where it earns its place* (YAGNI).
6. **Style polish** — catalog, curriculum outline, lesson player, and progress UI informed by
   Udemy/Coursera patterns, kept in the existing warm glass theme.
7. **Content-quality safeguards** — guard against subtly wrong generated lessons.
8. **Loose ends** — a real streak stat; resilient Claude-subscription login on the Pi.

## Operating principles

- **Autonomous execution.** Each item becomes one or more slices run brainstorm → spec → plan →
  subagent-driven build (per-task + whole-branch reviews) → deploy → verify. I self-approve routine
  design and taste decisions under this charter.
- **Deploy each slice** to the Pi (`claude-university`, port 8200, Tailscale-only) via the
  established rsync + `systemctl restart` pattern, and verify before moving on.
- **Escalate to Werner only for:** genuine product-direction forks; decisions with real cost/usage
  or irreversibility; taste calls he'd clearly want; or true blockers. Otherwise keep moving and
  report at slice boundaries.
- **Durable steering:** this charter, [ROADMAP.md](ROADMAP.md), and `.superpowers/sdd/progress.md`
  are the source of truth across sessions. Update the roadmap as slices complete.
- **Honesty:** report real status with evidence; verify on the Pi; never overclaim.

## Reference

Online-university data model + UX/style research: [research/online-universities-reference.md](research/online-universities-reference.md).
