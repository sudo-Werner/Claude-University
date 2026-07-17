"""Quiz Arcade: random-format retrieval-practice rounds over completed lessons.

Owns the whole feature end to end — round validation, format weighting, the
prompt builder, the per-course round bank + restock, results handling, and the
stats queries — so app.py's routes stay thin (mirrors feedback.py/images.py).
"""

import json
import random
import re
import sys
import threading
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import claude_client, courses, db, events, fsutil, spine

FORMATS = ("rapid_fire", "true_false", "odd_one_out", "spot_the_lie", "match_up")

BANK_FLOOR = 3
RESTOCK_CAP = 3

TITLE_MAX = 80
HOST_INTRO_MAX = 200
TEXT_MAX = 300   # prompt / statement / reveal
SHORT_MAX = 120  # choice / item / pair side

_QUESTION_COUNTS = {
    "rapid_fire": (8, 12),
    "true_false": (10, 14),
    "odd_one_out": (6, 8),
    "spot_the_lie": (6, 8),
    "match_up": (2, 3),
}

ROUND_ID_RE = re.compile(r"^round-[a-f0-9]{12}$")
ROUND_FILENAME_RE = re.compile(r"^round-[a-f0-9]{12}\.json$")


# ---- round validation ----

def _nonempty_str(v, max_len):
    return isinstance(v, str) and bool(v.strip()) and len(v) <= max_len


def _valid_index(v, n):
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n


def _valid_question_rapid_fire(q, pool):
    if not (isinstance(q, dict) and q.get("lesson_id") in pool):
        return False
    if not _nonempty_str(q.get("prompt"), TEXT_MAX):
        return False
    choices = q.get("choices")
    if not (isinstance(choices, list) and 3 <= len(choices) <= 5
            and all(_nonempty_str(c, SHORT_MAX) for c in choices)):
        return False
    if not _valid_index(q.get("answer"), len(choices)):
        return False
    return _nonempty_str(q.get("reveal"), TEXT_MAX)


def _valid_question_true_false(q, pool):
    if not (isinstance(q, dict) and q.get("lesson_id") in pool):
        return False
    if not _nonempty_str(q.get("statement"), TEXT_MAX):
        return False
    if not isinstance(q.get("answer"), bool):
        return False
    return _nonempty_str(q.get("reveal"), TEXT_MAX)


def _valid_question_odd_one_out(q, pool):
    if not (isinstance(q, dict) and q.get("lesson_id") in pool):
        return False
    items = q.get("items")
    if not (isinstance(items, list) and len(items) == 4
            and all(_nonempty_str(i, SHORT_MAX) for i in items)):
        return False
    if not _valid_index(q.get("answer"), 4):
        return False
    return _nonempty_str(q.get("reveal"), TEXT_MAX)


def _valid_question_spot_the_lie(q, pool):
    if not (isinstance(q, dict) and q.get("lesson_id") in pool):
        return False
    statements = q.get("statements")
    if not (isinstance(statements, list) and len(statements) == 3
            and all(_nonempty_str(s, TEXT_MAX) for s in statements)):
        return False
    if not _valid_index(q.get("answer"), 3):
        return False
    return _nonempty_str(q.get("reveal"), TEXT_MAX)


def _valid_pair(p):
    return (isinstance(p, dict) and _nonempty_str(p.get("left"), SHORT_MAX)
            and _nonempty_str(p.get("right"), SHORT_MAX))


def _valid_question_match_up(q, pool):
    if not (isinstance(q, dict) and q.get("lesson_id") in pool):
        return False
    pairs = q.get("pairs")
    if not (isinstance(pairs, list) and len(pairs) == 5 and all(_valid_pair(p) for p in pairs)):
        return False
    return _nonempty_str(q.get("reveal"), TEXT_MAX)


_QUESTION_VALIDATORS = {
    "rapid_fire": _valid_question_rapid_fire,
    "true_false": _valid_question_true_false,
    "odd_one_out": _valid_question_odd_one_out,
    "spot_the_lie": _valid_question_spot_the_lie,
    "match_up": _valid_question_match_up,
}


def valid_round(obj, *, pool):
    """Default-deny validator for one generated round. `pool` is the set of
    lesson_ids this round is allowed to reference (courses.completed_lesson_ids
    intersected with cached lesson files) — any question naming a lesson_id
    outside it is rejected, which keeps a hallucinated id out of the SRS signal."""
    if not isinstance(obj, dict):
        return False
    fmt = obj.get("format")
    if fmt not in FORMATS:
        return False
    if not _nonempty_str(obj.get("title"), TITLE_MAX):
        return False
    if not _nonempty_str(obj.get("host_intro"), HOST_INTRO_MAX):
        return False
    questions = obj.get("questions")
    lo, hi = _QUESTION_COUNTS[fmt]
    if not (isinstance(questions, list) and lo <= len(questions) <= hi):
        return False
    validator = _QUESTION_VALIDATORS[fmt]
    return all(validator(q, pool) for q in questions)


# ---- format weighting + round prompt builder ----

def format_weights(history):
    """history: an iterable of format strings (the course's last 10 quiz_round
    events). weight = 1 / (1 + times that format appears) — recently played
    formats get rarer, every format stays possible."""
    counts = Counter(f for f in history if f in FORMATS)
    return {f: 1.0 / (1 + counts.get(f, 0)) for f in FORMATS}


def choose_format(history, *, rand=None):
    """Weighted-random format pick. `rand` is a float in [0, 1); defaults to
    random.random() but tests inject a fixed value for determinism. FORMATS'
    fixed iteration order makes the mapping from `rand` to a format
    deterministic given a fixed `rand`."""
    if rand is None:
        rand = random.random()
    weights = format_weights(history)
    total = sum(weights.values())
    target = rand * total
    upto = 0.0
    for f in FORMATS:
        upto += weights[f]
        if target < upto:
            return f
    return FORMATS[-1]


_FORMAT_INSTRUCTIONS = {
    "rapid_fire": (
        'rapid_fire: write 8 to 12 questions. Each question is exactly '
        '{"lesson_id":"<id from the pool below>","prompt":"<question, plain text, max 300 chars>",'
        '"choices":["<3 to 5 short plain-text options, max 120 chars each>"],'
        '"answer":<0-based index of the correct choice>,'
        '"reveal":"<one plain-text sentence, max 300 chars, shown after answering>"}'
    ),
    "true_false": (
        'true_false: write 10 to 14 questions. Each question is exactly '
        '{"lesson_id":"<id from the pool below>","statement":"<plain-text claim, max 300 chars>",'
        '"answer":<true or false>,"reveal":"<one plain-text sentence, max 300 chars>"}'
    ),
    "odd_one_out": (
        'odd_one_out: write 6 to 8 questions. Each question is exactly '
        '{"lesson_id":"<id from the pool below>","items":["<exactly 4 short plain-text items, max 120 chars each>"],'
        '"answer":<0-based index of the item that does not belong>,'
        '"reveal":"<one plain-text sentence, max 300 chars, explaining why>"}'
    ),
    "spot_the_lie": (
        'spot_the_lie: write 6 to 8 questions. Each question is exactly '
        '{"lesson_id":"<id from the pool below>","statements":["<exactly 3 short plain-text statements, max 300 chars each>"],'
        '"answer":<0-based index of the false statement>,'
        '"reveal":"<one plain-text sentence, max 300 chars, explaining why>"}'
    ),
    "match_up": (
        'match_up: write 2 or 3 boards. Each board is exactly '
        '{"lesson_id":"<id from the pool below>","pairs":[{"left":"<short plain-text term, max 120 chars>",'
        '"right":"<short plain-text matching definition or example, max 120 chars>"}] '
        '(exactly 5 pairs),"reveal":"<one plain-text sentence, max 300 chars>"}'
    ),
}


def round_prompt(*, format, course_title, pool_lessons):
    """`pool_lessons`: the list of dicts question_pool() returns — the ONLY
    grounding material for the round (decision 11: no learner free text ever
    enters this prompt, just cached lesson content, spine entries, and the
    manifest title)."""
    lines = []
    for l in pool_lessons:
        concepts = "; ".join(
            f"{c.get('term', '')} = {c.get('definition', '')}"
            for c in l.get("concepts", []) if isinstance(c, dict)
        )
        lines.append(f'- id={l["lesson_id"]} "{l["title"]}": {l.get("summary", "")}'
                     + (f" (concepts: {concepts})" if concepts else ""))
    lessons_block = "\n".join(lines)
    return (
        f'You are writing one round of a playful pop-quiz game called the Arcade for a '
        f'learner studying the course "{course_title}" on a personal learning platform. This '
        f'round tests ONLY material from the lessons listed below — never invent facts '
        f'outside them, and never reference material the learner has not yet studied.\n\n'
        f'Lessons available for this round (use ONLY these lesson_id values):\n{lessons_block}\n\n'
        f'Write a "{format}" round: {_FORMAT_INSTRUCTIONS[format]}\n\n'
        'Every prompt/statement/item/pair/reveal is PLAIN TEXT — no HTML, no markdown, no '
        'fenced code. Spread questions across DIFFERENT lessons from the list where possible '
        'rather than repeating one lesson. Keep the tone playful and encouraging, like a fun '
        'game show host, never like a test.\n'
        'Reply with ONLY a JSON object, no prose, no fence:\n'
        '{"title":"<a short playful round title, max 80 chars>",'
        '"host_intro":"<one or two upbeat sentences introducing this round, max 200 chars>",'
        f'"format":"{format}","questions":[<question>, ...]}}'
    )
