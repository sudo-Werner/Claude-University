"""Fresh retrieval items for review sessions (Claude-in-lessons deep dive item 2).

When a lesson comes up for review, the review serves 1-2 FRESH retrieval questions
generated from the lesson's objectives and knowledge-spine entry, instead of
re-serving the lesson's original checks — varied retrieval beats identical-item
re-testing (Butler 2010; Roediger & Karpicke). Answers are graded client-side in the
exact lesson-check shape (generation.valid_check) exactly like ordinary checks, and
land as lesson_check events tagged source="review" — mastery, stats, and SRS need
zero new code. Items are cached per lesson, stamped with the review count (number of
lesson_reviewed events) at generation time: re-serving within one review pass is
free, the next review session regenerates (the remediation attempt-stamp idiom).
"""

import json
import uuid
from pathlib import Path

from backend import exams, fsutil, generation

ITEMS_MIN = 1
ITEMS_MAX = 2


def _spine_block(title, spine_entry):
    if not isinstance(spine_entry, dict):
        return ""
    concepts = [c for c in (spine_entry.get("concepts") or []) if isinstance(c, dict)]
    term_lines = "\n".join(f"- {c.get('term', '')}: {c.get('definition', '')}" for c in concepts)
    summary = spine_entry.get("summary", "")
    if not (summary or term_lines):
        return ""
    return (
        f'\nWhat the lesson "{title}" taught: {summary}\n'
        + (term_lines + "\n" if term_lines else "")
    )


def review_items_prompt(lesson_meta, spine_entry, existing_check_prompts):
    title = lesson_meta.get("title", "")
    module_title = lesson_meta.get("moduleTitle", "")
    objectives = [o for o in (lesson_meta.get("objectives") or [])
                  if isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip()]
    if not objectives:
        objectives = [exams._fallback_objective(title)]
    obj_lines = "; ".join(
        f"{o.get('text', '')} (Bloom: {o.get('bloom', '')})" for o in objectives)

    spine_block = _spine_block(title, spine_entry)

    existing_block = ""
    if existing_check_prompts:
        joined = "\n".join(f"- {p}" for p in existing_check_prompts)
        existing_block = (
            "\nThis lesson's existing concept-check questions — do NOT repeat or lightly "
            f"reword these existing questions; write genuinely NEW retrieval items:\n{joined}\n"
        )

    return (
        "You are a tutor on a personal learning platform writing FRESH retrieval-practice "
        f'questions for a learner reviewing the lesson "{title}" (module: "{module_title}").\n'
        f"Learning objectives this lesson teaches to: {obj_lines}\n"
        + spine_block
        + existing_block +
        "\nWrite EXACTLY 2 NEW concept-check items testing these objectives, a mix of mcq and "
        "fill where the content allows. Each item is either "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,'
        '"explanation":"<specific, encouraging one-sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact word or short phrase>",'
        '"explanation":"<specific, encouraging one-sentence why>"}.\n'
        "Before emitting, re-answer each mcq question independently from the question text "
        "alone. Confirm the choice at answer is the answer you get, and that no distractor is "
        "also defensibly correct — if one is, rewrite it.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"items":[<check>, <check>]}'
    )


def valid_review_items(obj):
    if not isinstance(obj, dict):
        return False
    items = obj.get("items")
    if not (isinstance(items, list) and ITEMS_MIN <= len(items) <= ITEMS_MAX):
        return False
    return all(generation.valid_check(i) for i in items)


def highlight_item_prompt(highlight_text, lesson_meta, spine_entry):
    title = lesson_meta.get("title", "")
    module_title = lesson_meta.get("moduleTitle", "")
    return (
        "You are a tutor on a personal learning platform writing ONE retrieval-practice "
        f'question for a learner reviewing the lesson "{title}" (module: "{module_title}"). '
        "They highlighted this passage as worth remembering — write a question that tests "
        "recall of what it says, without the answer choices simply quoting it back.\n"
        f'Highlighted passage: "{highlight_text}"\n'
        + _spine_block(title, spine_entry) +
        "\nWrite EXACTLY ONE concept-check item, mcq or fill depending on what fits best. "
        '{"type":"mcq","prompt":"<question, may use <code>>","choices":["A","B","C"],'
        '"answer":<integer index of the correct choice>,'
        '"explanation":"<specific, encouraging one-sentence why>"} '
        'or {"type":"fill","prompt":"<question>","answer":"<the exact word or short phrase>",'
        '"explanation":"<specific, encouraging one-sentence why>"}.\n'
        "Before emitting, re-answer the question independently from the question text alone. "
        "Confirm the answer field is the answer you get, and if it's mcq, that no distractor "
        "is also defensibly correct — if one is, rewrite it.\n"
        'Reply with ONLY JSON, no prose, no fence: {"item": <check>}'
    )


def valid_highlight_item(obj):
    if not isinstance(obj, dict):
        return False
    return generation.valid_check(obj.get("item"))


def _finalize_one(it):
    """Explicit-fields-only copy (never persist unknown model keys, remediation.py's
    finalize_session idiom): prompt/explanation/choices through generation.sanitize_html,
    mcq answer int kept, fill answer kept verbatim (client-side grading compares learner
    typing)."""
    item = {
        "type": it["type"],
        "prompt": generation.sanitize_html(it["prompt"]),
        "answer": it["answer"],
        "explanation": generation.sanitize_html(it["explanation"]),
    }
    if it["type"] == "mcq":
        item["choices"] = [generation.sanitize_html(c) for c in it["choices"]]
    return item


def finalize_items(obj, lesson_id, review_count):
    items = [_finalize_one(it) for it in obj["items"]]
    return {"lessonId": lesson_id, "reviewCount": review_count, "items": items}


def _path(content_dir, course_id, lesson_id):
    return Path(content_dir) / course_id / "review-items" / f"{lesson_id}.json"


def save_items(content_dir, course_id, items):
    path = _path(content_dir, course_id, items["lessonId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(items, indent=2, ensure_ascii=False))


def load_items(content_dir, course_id, lesson_id):
    path = _path(content_dir, course_id, lesson_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    if not (isinstance(data, dict) and isinstance(data.get("items"), list)):
        return None
    if not isinstance(data.get("userItems"), list):
        data["userItems"] = []  # back-compat: files written before highlight-items existed
    return data


def prune(content_dir, course_id, keep_lesson_ids):
    items_dir = Path(content_dir) / course_id / "review-items"
    if not items_dir.is_dir():
        return
    for f in items_dir.glob("*.json"):
        if f.stem not in keep_lesson_ids:
            f.unlink(missing_ok=True)


def ensure_review_items(content_dir, course_id, lesson_id, review_count, *,
                        lesson_meta, spine_entry, existing_checks, generate):
    """Serve the stored items when they were stamped with the current review count;
    otherwise generate, persist, and return fresh ones (remediation.ensure_session
    shape — the caller holds generation._gen_lock for the whole call, so this single
    check IS the cache re-check inside the lock). userItems (highlight-derived, see
    make_highlight_item) are never regenerated — carried forward across a stamp
    change so they survive as long as the lesson itself does."""
    existing = load_items(content_dir, course_id, lesson_id)
    if existing is not None and existing.get("reviewCount") == review_count:
        return existing
    user_items = existing.get("userItems", []) if existing is not None else []
    existing_check_prompts = [c.get("prompt", "") for c in (existing_checks or [])
                              if isinstance(c, dict) and isinstance(c.get("prompt"), str)]
    prompt = review_items_prompt(lesson_meta, spine_entry, existing_check_prompts)
    obj = generate(prompt, valid_review_items)
    items = finalize_items(obj, lesson_id, review_count)
    items["userItems"] = user_items
    save_items(content_dir, course_id, items)
    return items


def make_highlight_item(content_dir, course_id, lesson_id, highlight_text, *,
                        lesson_meta, spine_entry, generate):
    """Generates ONE retrieval item from a highlighted passage and appends it to the
    per-lesson review-items file as a persistent userItem — unlike `items` (the
    AI-fresh set, regenerated every review pass via ensure_review_items), userItems
    survive regeneration AND the source highlight's later removal (the workspace's
    highlights list and this file are independent stores — see notes.py)."""
    prompt = highlight_item_prompt(highlight_text, lesson_meta, spine_entry)
    obj = generate(prompt, valid_highlight_item)
    item = _finalize_one(obj["item"])
    item["id"] = f"hi-{uuid.uuid4().hex[:12]}"
    item["source"] = "highlight"
    # reviewCount -1 is not a real review count (len() is never negative) — it can
    # never match ensure_review_items' cache-hit check, so a highlight created
    # before the lesson's first AI-fresh generation still forces one on next fetch
    # instead of silently serving an empty `items` list forever.
    existing = load_items(content_dir, course_id, lesson_id) or {
        "lessonId": lesson_id, "reviewCount": -1, "items": [], "userItems": []}
    existing["userItems"] = [*existing.get("userItems", []), item]
    save_items(content_dir, course_id, existing)
    return item
