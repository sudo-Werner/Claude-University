# Video explainers + creative teaching style — design

**Date:** 2026-07-16. **Status:** approved (Werner-requested 2026-07-16 22:12: asked-for visual
references "helped a ton! (Amoeba Sisters)" — wants lessons to pre-emptively include such
sources, and the system to "find creative teaching approaches like they do in the videos").

## Goal

Every newly generated lesson (1) tries to include one high-quality video explainer — the
Amoeba Sisters / Crash Course / Khan Academy / 3Blue1Brown class of content — found via the
same web search that already grounds the lesson, surfaced in the existing Sources card and
Library with a distinct "Video" badge; and (2) teaches more like those channels teach: a hook
up front, one running concrete scenario, vivid visual metaphors in prose.

**Cost shape:** no new Claude calls. A modest fixed addition to the lesson-generation prompt
(one extra search behavior + one style block) on the already-expensive `run_sourced` path.
Cached lessons are untouched; new generations and deepens pick it up automatically.

## Decisions (routine, self-approved; direction Werner-given)

1. **Videos ride the EXISTING `sources` machinery — no new lesson field.** A video explainer
   is just a source whose URL is a video host. It flows through `_resolve_sources`' trust
   path unchanged (kept only if the URL was really captured from web search — the model
   cannot invent a YouTube link), lands in the lesson's `sources` array, the lesson Sources
   card, and the Library's "used in your lessons" roll-up with zero new plumbing. YAGNI on a
   `videos` field, a videos validator, and inline embeds (`sanitize_html` strips iframes by
   design; a link out is the honest, safe rendering).
2. **New `source_type` "video"**: `source_type(url)` gains host matches for `youtube.com`,
   `www.youtube.com`, `m.youtube.com`, `youtu.be` (whole-label host matching, the
   summit.org≠mit.edu rule) plus `vimeo.com` → returns `"video"`. `"video"` is appended LAST
   in `_SOURCE_TYPE_RANK` (a video is a complement, never the authority — accredited text
   sources keep sorting first). Because types are recomputed from the URL at read time
   (`course_lesson_sources`, `_with_refreshed_source_types`), any video URL already sitting
   in a cached lesson relabels itself automatically.
3. **Frontend labels**: add `video: "Video"` to BOTH duplicated maps (`library.js`
   `TYPE_LABEL` + `TYPE_ORDER` end; `lesson.js` `SRC_TYPE_LABEL`) and a `.src-badge.src-video`
   CSS rule (distinct tint, same badge idiom). Unknown-type fallback stays "Reference".
4. **Prompt: one new "video explainer" block in `lesson_prompt`** (additive — there is no
   byte-identity test on `lesson_prompt`; the substring-tested blocks are not modified):
   search for ONE genuinely good, topic-matched video explainer from a reputable education
   channel (name Amoeba Sisters, Crash Course, Khan Academy, 3Blue1Brown as the exemplar
   class); include it in `sources` with its REAL URL from the search results and a note
   saying what the video shows; if nothing genuinely good and specific turns up, include no
   video rather than a loose match. The existing grounding note's "list ONLY the specific
   sources you actually drew on" framing is loosened one notch for the video entry alone: the
   video is a recommended complement, not a claim of citation — its note must say what it is.
5. **Prompt: one new creative-teaching style block** (additive, same section as the existing
   readability block, which is not modified): open the lesson with a hook — a surprising
   fact, a question the learner cannot yet answer, or a tiny mystery the lesson resolves;
   carry ONE running concrete scenario/character through the explanation and the exercise
   instead of scattered disconnected examples; prefer a vivid visual metaphor in prose
   (something the learner can picture) for each abstract concept, in the spirit of the best
   explainer channels; never let style crowd out substance — the objectives still rule.
6. **Bibliography untouched.** The Library's curated "recommended reading" prompt stays
   text-source only; videos reach the Library via the lesson roll-up. (Revisit only if
   Werner asks for a videos shelf.)
7. **No backfill.** Existing cached lessons stay as they are (regenerating them costs real
   money and their content is fine); "Rusty on this?" deepens regenerate and thereby upgrade
   organically.

## Changes

- `backend/generation.py`: `source_type` video hosts; `_SOURCE_TYPE_RANK` + `"video"` (last);
  `lesson_prompt` two additive blocks (video explainer instruction beside the grounding note;
  creative-teaching block beside the readability block).
- `frontend/src/views/library.js`: `TYPE_LABEL.video = "Video"`, `TYPE_ORDER` + `"video"` (last).
- `frontend/src/views/lesson.js`: `SRC_TYPE_LABEL.video = "Video"`.
- `frontend/styles.css`: `.src-badge.src-video` rule.
- Tests: `source_type` video hosts (incl. `notyoutube.com` must NOT match — whole-label rule);
  rank/order includes video last; `lesson_prompt` substring tests for the video block
  (channel exemplars + "REAL URL" + skip-if-nothing-good) and the creative block (hook,
  running scenario, visual metaphor) WITHOUT touching existing substring assertions; frontend
  label-map tests (a video source renders the Video badge in lesson + library views).

## Security / integrity

- The trust path is unchanged: a video source survives only if its URL was captured from the
  actual search stream — no invented links. URLs render with the existing `esc()` +
  `target="_blank" rel="noopener noreferrer"` idiom. No embeds, no iframes.
- Honest labels (the standards-batch rule): "Video" is its own badge; a YouTube link can
  never masquerade as "peer-reviewed" because types derive from the URL host.

## Testing / deploy

`.venv/bin/pytest -q` (from repo root) and `node --test frontend/tests/*.test.js` + app.js
import check. Standard DEPLOY.md deploy; verification = deployed greps + suites (generation
is a paid path — never live-probed). The first real evidence arrives with Werner's next new
lesson.

## Out of scope

- Inline video embeds; a dedicated videos shelf in the Library; backfilling cached lessons;
  any new Claude call or route; per-course channel preferences (revisit if the generic
  exemplars pick badly).
