# Claude University — Design Tokens

Warm, **frosted-glass** ("Apple / Big Sur") study theme, optimized for reading and sustained
focus. Soft warm cream base with blurred colored light behind translucent panels.
Single-column, mobile-first (max content width **448px**), works on phone and laptop.
UI font **system-ui** (SF on Apple); reading font **Georgia** (system serif).
No external CSS frameworks.

---

## The glass system (read first)

Three layers create the effect:
1. **Base** — warm cream gradient `linear-gradient(180deg,#f4ecdd,#efe3cf)` on `body` / page.
2. **Ambient light** — a `position:fixed; inset:0; z-index:0` layer of soft colored blobs
   (peach, purple, blue, pink) that the glass refracts. Content sits above at `z-index:1`.
   ```css
   background:
     radial-gradient(46% 40% at 10% 6%,  rgba(255,178,116,.48), transparent 70%),
     radial-gradient(44% 42% at 90% 4%,  rgba(150,130,255,.36), transparent 70%),
     radial-gradient(52% 44% at 82% 94%, rgba(110,194,240,.34), transparent 72%),
     radial-gradient(40% 34% at 16% 98%, rgba(255,158,182,.24), transparent 72%);
   ```
3. **Glass panels** — translucent white + blur + 1px light border + inset top highlight:
   ```css
   background: rgba(255,253,249,0.60);
   backdrop-filter: blur(26px) saturate(1.6);
   -webkit-backdrop-filter: blur(26px) saturate(1.6);
   border: 1px solid rgba(255,255,255,0.65);
   box-shadow: 0 1px 0 rgba(255,255,255,0.75) inset, 0 18px 48px -24px rgba(90,65,40,0.40);
   ```
   Blur radius scales with surface size: cards 22–26px, chips/tabs 12–16px, inner blocks 0 (just translucent fill).

> Note: `backdrop-filter` is the effect — keep a real blurred backdrop behind every glass panel.
> Fallback (no blur support): the rgba fills are opaque enough to stay legible on their own.

---

## Color

### Surfaces
| Token | Value | Use |
|---|---|---|
| `--base` | `linear-gradient(180deg,#f4ecdd,#efe3cf)` | Page base (warm cream) |
| `--glass-card` | `rgba(255,253,249,0.60)` + blur 26 | Primary cards |
| `--glass-stat` | `rgba(255,253,249,0.55)` + blur 22 | Stat cards |
| `--glass-soft` | `rgba(255,250,242,0.50)` + blur 18 | Streak strip |
| `--glass-inner` | `rgba(255,255,255,0.42)` (no blur) | Concept blocks, completion tiles |
| `--glass-field` | `rgba(255,255,255,0.50)` | Inputs, option rows |
| `--tab-track` | `rgba(150,122,90,0.13)` + blur 16 | Segmented-control track |
| `--tab-pill` | `rgba(255,255,255,0.85)` + blur 10 | Active tab pill |

### Lines (translucent)
| Token | Value |
|---|---|
| `--border-glass` | `rgba(255,255,255,0.65)` (cards) / `0.60` (small) |
| `--border-field` | `rgba(255,255,255,0.60)` |
| `--border-dashed` | `rgba(150,120,80,0.40)` (gated hint) |

### Text (warm, on glass)
| Token | Hex | Use |
|---|---|---|
| `--text` | `#241f1a` | Headings / primary |
| `--text-2` | `#544e44` | Body, option labels |
| `--read` | `#403a31` | Long-form reading prose (serif) |
| `--text-dim` | `#837a6c` | Secondary, meta |
| `--text-mut` | `#8f8676` | Captions, labels |
| `--text-faint` | `#b3a994` | Tertiary (units, counters) |

### Accent (vibrant on glass)
| Token | Hex | Use |
|---|---|---|
| `--purple` | `#7c6aff` | Primary accent, peak phase, selection — brand purple, kept vivid |
| `--purple-deep` | `#5a4bd0` | Purple text needing contrast |
| `--purple-soft` | `rgba(124,106,255,0.14)` (border `0.50`) | Selected-option / badge fill |
| `--blue` | `#4fa3e8` / `#2f8fd0` | Secondary accent / phase / reviews |
| `--blue-text` | `#1f78b4` | Blue text, inline code |
| `--grad-primary` | `linear-gradient(135deg,#7c6aff,#4fa3e8)` | Primary CTA |
| logo mark | `linear-gradient(135deg,#7c6aff,#4fc3f7)` | Brand mark only |

### Semantic (translucent glass fills)
| Token | Value | Use |
|---|---|---|
| `--success` | `#21a06a` (text `#1c7a52`) on `rgba(37,180,120,0.15)` | Correct, cool-down, completion |
| `--error` | `#d6557e` (text `#b04068`) on `rgba(214,85,126,0.13)` | Wrong selection (gentle) |
| `--streak` | `#e0892f` (text `#b5670f`) on `rgba(255,232,196,0.66)` | Streak flame / chip |
| `--hint` | text `#8a5613` on `rgba(255,184,100,0.18)`, border `rgba(224,160,80,0.42)` | Hint callout |

---

## Type scale
**UI:** system-ui. **Reading:** `Georgia,'Iowan Old Style','Times New Roman',serif`.

| Step | Size / line-height | Weight | Font | Use |
|---|---|---|---|---|
| Display | 26px / 1.1 | 700 | UI | Big stat numbers |
| H1 | 23px / 1.2 | 650 | UI | Session topic, completion title |
| H2 | 18–20px / 1.3 | 600 | UI | Greeting, step question |
| H3 | 15px / 1.3 | 600 | UI | Concept titles, option labels |
| Read | 16px / 1.7 | 400 | **serif** | Lesson prose, exercise prompts |
| Read-sm | 14–15px / 1.6 | 400 | **serif** | Concept bodies, solution gloss |
| Body | 13–14px / 1.5 | 400 | UI | Meta, descriptions |
| Label | 11px / 1.4 | 700 | UI | Eyebrows — `letter-spacing:0.09em`, UPPERCASE |
| Caption | 10–12px | 400–600 | UI | Units, counters, durations |

Tabular numerals on timer / counters. Monospace (`ui-monospace`) for formulas; inline code `--blue-text`.

---

## Spacing  (4px base)
`4 · 8 · 10 · 12 · 14 · 16 · 18 · 20 · 22 · 24 · 32`
- Card padding **22–24px** · Card gap **16px** · Option-row gap **9px**
- Page padding **26px** vertical, **18px** horizontal

## Radius (generous, Apple-soft)
| Token | px | Use |
|---|---|---|
| `--r-sm` | 11–12 | Buttons in controls, badges, chips |
| `--r-md` | 13–15 | Inputs, option rows, primary/secondary buttons |
| `--r-lg` | 20 | Stat cards |
| `--r-xl` | 24 | Primary cards |
| `--r-full` | 999 | Pills, bars, dots, streak chip |

## Elevation
- Card: `0 1px 0 rgba(255,255,255,.75) inset, 0 18px 48px -24px rgba(90,65,40,.40)`
- Stat card: `0 1px 0 rgba(255,255,255,.70) inset, 0 14px 36px -22px rgba(90,65,40,.36)`
- Active tab pill: `0 1px 0 rgba(255,255,255,.9) inset, 0 2px 8px -2px rgba(90,65,40,.25)`
- Primary CTA: `0 1px 0 rgba(255,255,255,.35) inset, 0 12px 26px -10px rgba(124,106,255,.6)`
- Transitions: `all .15–.18s`.

---

## Components & states

### Button — Primary (gradient CTA)
- **Default:** `--grad-primary`, white text, weight 600, radius 15, top-highlight + purple glow.
- **Hover:** brightness +3%. **Active:** translateY(1px).
- **Disabled:** `rgba(140,118,84,0.16)`, text `#a99f8f`, no shadow, `cursor:not-allowed`.
- One primary action per screen.

### Button — Secondary
- Review: `1px rgba(79,163,232,0.4)`, `rgba(79,163,232,0.14)` fill, `#1f78b4` text.
- Back: glass — `rgba(255,255,255,0.5)` + blur, `1px rgba(255,255,255,0.6)`, `#665f53` text.

### Segmented control (Dashboard / Lesson)
- Track `--tab-track` (blur 16) + `1px rgba(255,255,255,0.5)`, radius 15, 4px padding.
- **Active:** `--tab-pill`, `--text`, pill shadow. **Inactive:** transparent, `#7d7568`.

### Card
- `--glass-card`, `1px --border-glass`, radius `--r-xl`, padding 22–24, glass shadow.

### Progress bar
- Track `rgba(120,100,70,0.14)`, radius full, height 7–9.
- Fill `--grad-primary` (course) or per-phase color (timer); width `.2s linear`.

### Session timer (90 min, 3 phases)
- Warm-up 15m `#3aa0e0` · Peak 60m `#7c6aff` · Cool-down 15m `#25b478`.
- Active phase label brightens to its color; others `--text-mut`.
- States: **idle** ("Start session") · **running** ("Pause", fills advance) · **paused** ("Resume") · **complete**.

### Quiz option row
- **Default:** `--glass-field`, `1px --border-field`, `#48423a`, leading 20px circle.
- **Selected:** `rgba(124,106,255,0.14)`, `rgba(124,106,255,0.5)` border, `--text`, filled purple dot.
- **Correct (after check):** `rgba(37,180,120,0.16)`, `rgba(37,180,120,0.5)` border, ✓.
- **Wrong selected:** `rgba(214,85,126,0.14)`, `rgba(214,85,126,0.48)` border, ✕.
- **Unselected after check:** `rgba(255,255,255,0.3)`, faint border, `--text-mut`, `opacity .72`, locked.

### Hint disclosure (gated)
- **Default:** translucent + dashed `--border-dashed`, `--text-dim`, amber lightbulb → "Show hint".
- **Revealed:** `--hint` warm-glass callout. Toggle → "Hide hint".

### Solution reveal (gated)
- **Locked (no attempt):** `rgba(255,255,255,0.36)`, faint border, `#a59b89`, lock — "Attempt first to unlock the solution".
- **Unlocked (attempt made):** `rgba(124,106,255,0.14)`, purple border, `#5a4bd0` → "Reveal solution".
- **Shown:** `rgba(37,180,120,0.15)` panel with "SOLUTION" eyebrow + monospace answer + serif gloss; button → "Solution shown".
- Gate rule: unreachable until the answer field is non-empty.

### Text input / textarea
- **Default:** `--glass-field`, `1px --border-field`, radius 13–14, `--text`.
- **Focus:** border → `--purple`.
- Exercise answer = monospace; "explain it back" = serif + live word counter.

### Streak chip
- Pill, `rgba(255,232,196,0.66)` + blur, `1px rgba(255,255,255,0.6)`, amber flame + count `#b5670f`.

### Step progress (lesson)
- 5 segments, height 4. Completed `--purple`; current `--grad-primary`; upcoming `rgba(140,118,84,0.3)`.

---

## Layout principles (cognitive-load rules baked into the system)
1. **One primary action per screen** — exactly one gradient CTA visible.
2. **Progressive reveal** — answer before any solution; hints/solutions gated, never default.
3. **Chunking** — 2–3 new concepts max, one step at a time (5-step stepper).
4. **Read-first, low-glare surface** — serif prose, generous line-height, warm frosted glass
   so long sessions stay comfortable; accent vivid but used sparingly; depth from blur + soft
   shadow, never harsh contrast.
