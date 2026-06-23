# Online Learning Platforms: Reference Brief

**Purpose:** Design reference for Claude University — a single-user, AI-generated, spaced-repetition learning platform.
**Scope:** Udemy (primary), Coursera, edX, Khan Academy (where they differ usefully).

---

## 1. Course Data Model / Content Structure

### Standard Hierarchy

All four platforms converge on a 4-level hierarchy:

```
Course
  └── Section / Module / Chapter       (groups topics)
        └── Lesson / Lecture / Item    (single deliverable)
              └── Content Elements     (within-lesson components)
```

| Platform | Level 1 | Level 2 | Level 3 | Level 4 |
|----------|---------|---------|---------|---------|
| Udemy | Course | Section | Lecture | — |
| Coursera | Course | Module | Lesson / Item | — |
| edX | Course | Chapter | Sequential → Vertical | Component |
| Khan Academy | Course | Unit | Exercise / Article / Video | Problem |

edX is the most granular: a Vertical (unit page) holds multiple Components (video, problem, html, discussion). Udemy is the flattest — sections contain lectures directly, with no intermediate layer.

### Lesson / Item Types

Udemy supports up to 1,400 curriculum items per course, across these types:
- **Lecture** — primary content unit; typically a video, but can be text/article
- **Quiz** — standalone assessment (multiple choice, fill-in-blank); auto-graded
- **Practice Test** — timed, longer quiz
- **Coding Exercise** — in-browser code execution
- **Assignment** — open-ended, instructor-graded

Coursera types:
- **Video** — pre-recorded lecture
- **Reading** — text/article page
- **Quiz** — auto-graded (MCQ, fill-in-blank)
- **Graded Assignment** — required for certificate
- **Practice Assignment** — ungraded
- **Peer Review** — submit artifact, graded by 3+ peers against a rubric
- **Programming Assignment** — code submission

edX component types (categories): `video`, `html`, `problem`, `discussion`.

### Quiz / Assessment Data Model (sketch)

```json
{
  "quiz": {
    "id": "q1",
    "title": "Section 3 Check",
    "pass_percent": 70,
    "questions": [
      {
        "id": "q1_1",
        "type": "multiple_choice",       // or fill_blank, true_false
        "prompt": "What does X mean?",
        "choices": [
          { "id": "a", "text": "...", "correct": true },
          { "id": "b", "text": "...", "correct": false }
        ],
        "explanation": "Because X is defined as..."
      }
    ]
  }
}
```

Coursera also supports numeric answer and match types. Khan Academy uses problem sets with procedurally-generated variants, not static answer banks.

### Progress & State Tracking

**Per-item state** (minimum needed):
- `completed: bool` — has the learner finished this item
- `completed_at: timestamp`
- `score: float | null` — for quizzes/exercises
- `attempts: int` — number of times attempted

**Per-course derived state:**
- `percent_complete` — completed items / total items
- `last_accessed_item_id` — "continue where you left off"
- `last_accessed_at`

Udemy tracks completion per lecture; course progress % is derived. Completion can be manually toggled (checkmark). Khan Academy tracks per-skill mastery state (see below).

### Course Metadata Fields

```json
{
  "id": "course_001",
  "title": "...",
  "description": "...",
  "difficulty": "beginner | intermediate | advanced",
  "estimated_duration_minutes": 180,
  "prerequisites": ["course_000"],
  "learning_objectives": ["Explain X", "Apply Y", "Analyse Z"],
  "tags": ["python", "algorithms"],
  "created_at": "...",
  "updated_at": "..."
}
```

Marketplace fields (not applicable here): ratings, review count, enrollment count, price, instructor, certificate.

### Spaced Repetition: Khan Academy vs SM-2

**Khan Academy mastery levels per skill:**

| Level | Points | How reached |
|-------|--------|-------------|
| Attempted | 0 | Started any exercise |
| Familiar | 50 | Score 70–85% on exercise, or any correct answer on quiz |
| Proficient | 80 | Score 100% from Familiar state |
| Mastered | 100 | Score 100% on Unit Test or Course Challenge |

Levels can regress: Mastered → Proficient if 70–99% on exercise; → Familiar if below 70%.

**Mastery Challenges** are triggered periodically — mixed-question sessions that re-test skills across units to maintain mastery levels over time. This is Khan Academy's spaced repetition mechanism.

**SM-2 algorithm** (used by Anki, widely implemented) — better fit for our use case:

Per-item review state:
```json
{
  "item_id": "lesson_abc",
  "repetitions": 3,
  "interval_days": 12,
  "ease_factor": 2.3,
  "next_review_date": "2026-07-05"
}
```

After each review, learner rates recall quality 0–5:
- ≥ 3: success — interval × ease_factor, EF adjusted up
- < 3: reset — interval = 1 day, repetitions = 0

`EF = EF + (0.1 − (5 − q) × (0.08 + (5 − q) × 0.02))`, minimum EF = 1.3.

---

## 2. Style / UX Patterns

### Course Catalog / Home ("Continue Learning")

Standard Udemy/Coursera home pattern:
- **"Continue Learning" strip** — 2–4 cards across, each showing: course title, instructor, progress bar, "Resume" CTA. Most recently accessed first.
- **"My Courses" grid** — card per course: thumbnail, title, progress %, last accessed date.
- Cards are typically 280–320px wide, with a thumbnail image taking ~60% of card height.

Key insight: The home page is primarily a resume surface, not a discovery surface. For a single-user platform, the entire home is "my courses."

### Course Landing / Overview Page

Two-column layout (main + sidebar):
- **Left / main**: hero title + description; "What you'll learn" (checkmark list = learning objectives); curriculum accordion; prerequisites.
- **Right / sidebar**: thumbnail, CTA button, stats (duration, lesson count, level).

**Curriculum accordion:**
- Each section is a collapsible row showing: section title, item count, total duration.
- Expanded: each lesson item shows title, type icon, duration, completion checkmark.
- Items with preview enabled show a "Preview" link.
- Progress bar appears at the section header level when in-progress.

### Lesson Player Layout

Udemy's player is the clearest model:

```
┌─────────────────────────────────────────┬──────────────────────┐
│                                         │  COURSE CONTENT      │
│         CONTENT AREA                    │  ─────────────────   │
│         (video / text / quiz)           │  ▼ Section 1         │
│                                         │    ✓ Lesson 1        │
│                                         │    → Lesson 2 (now)  │
│                                         │    ○ Lesson 3        │
│                                         │  ▶ Section 2         │
├─────────────────────────────────────────┴──────────────────────┤
│  ← Previous   [Mark Complete ✓]   Next →     Progress: 4/12   │
└────────────────────────────────────────────────────────────────┘
```

Key elements:
- **Sidebar** (right, ~280px): scrollable curriculum list — section headers, lesson items with type icon + duration + completion state. Currently-playing item highlighted.
- **Bottom bar**: Prev/Next navigation, "Mark as Complete" button, lesson count progress (X of Y).
- Sidebar can be collapsed to give content area full width.
- Notes panel (Udemy): timestamped text notes per lecture, hidden by default.

### Progress Visualization

- **Course card**: linear progress bar (0–100%), shows % complete label.
- **Section header in player sidebar**: optional mini-bar or "X/Y complete" count.
- **Bottom bar**: "X of Y lessons" counter.
- **Streaks**: Duolingo-style daily streaks are common on gamified platforms; Udemy does not use them. Khan Academy uses a streak mechanic.
- **Mastery score**: Khan Academy shows mastery points per unit as a colored progress ring.

What makes progress feel motivating vs noisy: single canonical number per course (%), shown consistently in one place (card + player bottom). Avoid showing three different percentage numbers simultaneously.

### Legibility vs Clutter

**Polished:**
- One content type dominates each screen — don't mix catalog, player, and settings.
- Whitespace between sections; consistent 8px grid spacing.
- Type icons (video/quiz/article) are small, monochrome — information, not decoration.
- Checkmarks on completed items are instant, visually distinct (filled vs empty).
- Sidebar items are compact (~40px tall), not padded cards.

**Cluttered:**
- Multiple CTAs competing on the same screen.
- Progress shown in too many places simultaneously.
- Long lesson titles truncated without hover reveal.
- Dense walls of text in lesson descriptions with no visual hierarchy.

---

## Applicability to Claude University

### Adopt directly

- **4-level hierarchy**: Course → Section → Lesson → Exercise. We already have Course and Lesson; add Section as the intermediate grouping.
- **Lesson player layout**: two-panel (content left, curriculum sidebar right) with bottom bar Prev/Next + Mark Complete. Matches our current single-lesson view's natural extension.
- **Curriculum accordion on course overview**: sections expand to show lessons with completion checkmarks. Straightforward to derive from event log.
- **"Continue Learning" card on home**: single resume card per active course — course title, section title, progress bar, "Resume" button. This is the main interaction surface.
- **SM-2 spaced repetition fields per lesson**: store `repetitions`, `interval_days`, `ease_factor`, `next_review_date` in progress data alongside event log. These are four integers/floats per lesson — trivially cheap.
- **Khan Academy mastery levels**: adopt the 4-state model (Attempted → Familiar → Proficient → Mastered) for lesson-level state rather than binary complete/incomplete. Derived from quiz scores in event log.
- **Learning objectives / outcomes** on course metadata — already meaningful since AI generates them.
- **Difficulty + estimated duration** on course metadata.

### Adapt

- **Quiz model**: we currently have hint + solution as gating. Extend to explicit quiz items (MCQ) within or at end of a lesson — simple question array in JSON, same structure as the sketch above.
- **Section-level progress**: derive from event log aggregation — no extra storage needed.
- **"Mark as Complete" button**: already present but currently the only completion gate. With quiz items, completion should require quiz pass threshold, not just a button press.

### Don't adopt (YAGNI for single-user AI-taught platform)

- **Video hosting** — irrelevant; our content is text-based AI-generated exercises.
- **Instructor profiles, bios, ratings-by-others** — no marketplace, no other users.
- **Enrollment, payments, certificates** — single user, no commerce.
- **Peer review / peer assessment** — no other learners.
- **Course reviews and star ratings** — there is one learner.
- **"Free preview" / locked lectures** — all content is accessible to the one user.
- **Streaks / XP / leaderboards** — potentially motivating but high YAGNI risk; add only if Werner asks for gamification explicitly.
- **Discussion forums, Q&A tabs** — no community.
- **Notes panel** (Udemy-style timestamped notes) — low value for text lessons vs video; skip until requested.
- **Prerequisite gates** (hard-block enrollment) — advisory metadata is fine; enforcement adds friction with no benefit for a self-directed learner.
- **Estimated duration on catalog** — AI-generated, hard to estimate meaningfully; skip or leave as rough "N exercises".

---

## Sources

- [edX Course Content Data — Research Guide](https://edx.readthedocs.io/projects/devdata/en/latest/internal_data_formats/course_structure.html)
- [How Khan Academy uses ML to assess mastery — David Hu, 2011](http://david-hu.com/2011/11/02/how-khan-academy-is-using-machine-learning-to-assess-student-mastery.html)
- [Khan Academy mastery levels — Help Center](https://support.khanacademy.org/hc/en-us/articles/5548760867853--How-do-Khan-Academy-s-Mastery-levels-work)
- [Understanding Curriculum Items — Udemy Support](https://support.udemy.com/hc/en-us/articles/229606188-Understanding-Curriculum-Items-for-Your-Course)
- [How to Use the Course Player — Udemy Support](https://support.udemy.com/hc/en-us/articles/229603648-How-to-Use-The-Course-Player-and-Start-Your-Course)
- [Course Items and Assessment Types — Coursera Support](https://www.coursera.support/s/article/learner-000002244?language=en_US)
- [SM-2 Algorithm Explained — Dev.to](https://dev.to/umangsinha12/how-spaced-repetition-actually-works-the-sm-2-algorithm-1ge3)
- [SM-2 Spaced Repetition in an LMS — Upscend](https://www.upscend.com/blogs/sm-2-spaced-repetition-algorithms-inside-an-lms-guide)
- [UX of eLearning Platforms — Medium / Tarane Yarahmadi](https://medium.com/@taraneyarahmadi/the-ux-of-elearning-platforms-designing-for-engagement-clarity-and-outcomes-b33c5353b79b)
- [Best eLearning Interface Design Examples — Eleken](https://www.eleken.co/blog-posts/elearning-interface-design-examples)
- [How to Design an eLearning Platform — JustInMind](https://www.justinmind.com/ui-design/how-to-design-e-learning-platform)
- [Udemy-Style Moodle Course Landing Page Guide — eLearning Themes](https://elearning.3rdwavemedia.com/blog/step-by-step-guide-create-a-udemy-style-moodle-course-landing-page/6218/)
