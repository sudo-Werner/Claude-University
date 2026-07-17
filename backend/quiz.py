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
