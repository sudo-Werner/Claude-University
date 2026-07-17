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

from backend import courses, db, events, fsutil, spine

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


# ---- question pool ----

def question_pool(content_dir, conn, course_id, manifest):
    """Completed lessons (courses.completed_lesson_ids) intersected with lessons
    that have a cached lesson file (the grounding source) — decision 3. Returns a
    list of {"lesson_id","title","summary","concepts"} in manifest order; empty
    when nothing is groundable yet."""
    completed = courses.completed_lesson_ids(conn, course_id)
    spine_data = spine.load_spine(content_dir, course_id)
    spine_lessons = spine_data.get("lessons", {}) if isinstance(spine_data, dict) else {}
    pool = []
    for lesson_meta in courses.flatten_lessons(manifest):
        lid = lesson_meta["id"]
        if lid not in completed:
            continue
        if courses.load_lesson(content_dir, course_id, lid) is None:
            continue
        entry = spine_lessons.get(lid) if isinstance(spine_lessons, dict) else None
        summary = entry.get("summary", "") if isinstance(entry, dict) else ""
        concepts = entry.get("concepts") if isinstance(entry, dict) else None
        pool.append({
            "lesson_id": lid, "title": lesson_meta["title"], "summary": summary,
            "concepts": concepts if isinstance(concepts, list) else [],
        })
    return pool


# ---- bank: file-per-round under content/courses/<id>/quiz-rounds/ ----

def _quiz_dir(content_dir, course_id):
    return Path(content_dir) / course_id / "quiz-rounds"


def _round_path(content_dir, course_id, round_id):
    return _quiz_dir(content_dir, course_id) / f"{round_id}.json"


def save_round(content_dir, course_id, round_):
    path = _round_path(content_dir, course_id, round_["round_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(round_, indent=2, ensure_ascii=False))


def _load_round_file(path):
    if not ROUND_FILENAME_RE.match(path.name):
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("round_id"), str) else None


def list_bank(content_dir, course_id):
    """Every banked (unplayed) round for this course, oldest first by
    created_at. A corrupt or hand-deleted file is silently skipped."""
    quiz_dir = _quiz_dir(content_dir, course_id)
    if not quiz_dir.is_dir():
        return []
    rounds = []
    for f in sorted(quiz_dir.glob("round-*.json")):
        data = _load_round_file(f)
        if data is not None:
            rounds.append(data)
    rounds.sort(key=lambda r: r.get("created_at", ""))
    return rounds


def bank_count(content_dir, course_id):
    return len(list_bank(content_dir, course_id))


def serve_round(content_dir, course_id):
    """The oldest banked round, or None when the bank is empty. Does NOT delete
    the file — the round stays banked until results are submitted
    (consume_round), so a dropped connection mid-round can resume the same
    round on the next GET."""
    rounds = list_bank(content_dir, course_id)
    return rounds[0] if rounds else None


def consume_round(content_dir, course_id, round_id):
    """Delete a round file. A missing file (already consumed, hand-deleted, or
    a malformed round_id) is a silent no-op — the quiz_round event is the
    durable record, per decision 7."""
    if not (isinstance(round_id, str) and ROUND_ID_RE.match(round_id)):
        return
    _round_path(content_dir, course_id, round_id).unlink(missing_ok=True)


def _finalize_question(fmt, q):
    if fmt == "rapid_fire":
        return {"lesson_id": q["lesson_id"], "prompt": q["prompt"],
                "choices": list(q["choices"]), "answer": q["answer"], "reveal": q["reveal"]}
    if fmt == "true_false":
        return {"lesson_id": q["lesson_id"], "statement": q["statement"],
                "answer": bool(q["answer"]), "reveal": q["reveal"]}
    if fmt == "odd_one_out":
        return {"lesson_id": q["lesson_id"], "items": list(q["items"]),
                "answer": q["answer"], "reveal": q["reveal"]}
    if fmt == "spot_the_lie":
        return {"lesson_id": q["lesson_id"], "statements": list(q["statements"]),
                "answer": q["answer"], "reveal": q["reveal"]}
    return {"lesson_id": q["lesson_id"],
            "pairs": [{"left": p["left"], "right": p["right"]} for p in q["pairs"]],
            "reveal": q["reveal"]}


def finalize_round(obj, course_id):
    """Explicit-fields-only copy of a validated generator object into the
    stored round shape (the review_items.finalize_items / exams.finalize_exam
    idiom — never persist an unknown model key). No sanitizer runs here on
    purpose: decision 2 is plain-text-only content, esc()'d at render, with no
    sanitize/markup surface in the Arcade at all — valid_round already
    enforced every string's type and length before this is ever called."""
    fmt = obj["format"]
    return {
        "round_id": f"round-{uuid.uuid4().hex[:12]}",
        "course_id": course_id,
        "format": fmt,
        "title": obj["title"],
        "host_intro": obj["host_intro"],
        "questions": [_finalize_question(fmt, q) for q in obj["questions"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---- format-history query (drives choose_format's recency weighting) ----

def _quiz_round_events(conn, course_id):
    """Every quiz_round event for this course, oldest first, tolerant of a
    malformed payload (skipped rather than raised — the events ledger is
    client-writable elsewhere, so a forged/corrupt row must never crash a
    read)."""
    rows = conn.execute(
        "SELECT occurred_at, payload FROM events "
        "WHERE event_type = 'quiz_round' AND course_id = ? "
        "ORDER BY occurred_at ASC, id ASC",
        (course_id,),
    ).fetchall()
    out = []
    for row in rows:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        fmt, score, total = payload.get("format"), payload.get("score"), payload.get("total")
        if fmt not in FORMATS:
            continue
        if isinstance(score, bool) or not isinstance(score, int):
            continue
        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            continue
        out.append({"occurred_at": row["occurred_at"], "format": fmt, "score": score, "total": total})
    return out


def recent_formats(conn, course_id, limit=10):
    """Formats of this course's last `limit` quiz_round events, most-recent-
    first — the history parameter choose_format's recency weighting
    consumes."""
    evs = _quiz_round_events(conn, course_id)
    return [e["format"] for e in evs[-limit:]][::-1]


# ---- restock: single-flight per course, capped generation ----

_RESTOCK_LOCKS = {}
_RESTOCK_LOCKS_GUARD = threading.Lock()


def _restock_lock(course_id):
    with _RESTOCK_LOCKS_GUARD:
        lock = _RESTOCK_LOCKS.get(course_id)
        if lock is None:
            lock = _RESTOCK_LOCKS[course_id] = threading.Lock()
        return lock


def _restock_once(content_dir, conn, course_id, *, generate):
    """Generate rounds until the bank reaches BANK_FLOOR, capped at
    RESTOCK_CAP new rounds this run. Runs INSIDE the caller's already-acquired
    restock lock — safe to call directly (no thread) in tests. A
    generation/validation failure, an empty pool, or a missing course stops
    the run silently with the bank left as-is (play never errors because a
    restock failed silently)."""
    manifest = courses.load_manifest(content_dir, course_id)
    if manifest is None:
        return
    made = 0
    while bank_count(content_dir, course_id) < BANK_FLOOR and made < RESTOCK_CAP:
        pool = question_pool(content_dir, conn, course_id, manifest)
        if not pool:
            return
        pool_ids = {l["lesson_id"] for l in pool}
        history = recent_formats(conn, course_id)
        fmt = choose_format(history)
        prompt = round_prompt(format=fmt, course_title=manifest.get("title", ""), pool_lessons=pool)
        try:
            obj = generate(prompt, lambda o: valid_round(o, pool=pool_ids))
        except Exception as exc:
            print(f"quiz restock failed for course {course_id}: {exc}", file=sys.stderr)
            return
        save_round(content_dir, course_id, finalize_round(obj, course_id))
        made += 1


def kick_restock(content_dir, db_path, course_id, *, generate, spawn=None):
    """Fire-and-forget: single-flight per course (a non-blocking try-lock — a
    second kick while one is already running for this course is a no-op, the
    caller never waits, per decision 6). `spawn` defaults to a real daemon
    thread; tests inject a synchronous stand-in so the restock's effect is
    observable immediately without touching real threads."""
    lock = _restock_lock(course_id)
    if not lock.acquire(blocking=False):
        return

    def run():
        conn = db.get_connection(db_path)
        try:
            _restock_once(content_dir, conn, course_id, generate=generate)
        finally:
            conn.close()
            lock.release()

    spawner = spawn or (lambda target: threading.Thread(target=target, daemon=True).start())
    spawner(run)


# ---- results ----

def _clean_missed(missed):
    """Best-effort clamp, never a 400: keep only string keys with a non-
    negative int value. Miss counts only ever influence review scheduling,
    never content (decision: security) — a malformed entry is dropped, not
    rejected."""
    out = {}
    if not isinstance(missed, dict):
        return out
    for lid, count in missed.items():
        if not (isinstance(lid, str) and lid):
            continue
        if isinstance(count, bool) or not isinstance(count, int):
            continue
        out[lid] = max(0, count)
    return out


def submit_results(content_dir, conn, course_id, body):
    """Insert one quiz_round event (idempotent on client_event_id via
    events.insert_events' INSERT OR IGNORE — a replay is a safe no-op) and
    delete the round file (consume_round is itself a no-op if it's already
    gone). Raises ValueError on a malformed body; the route maps that to 400
    without touching the DB or the bank."""
    if not isinstance(body, dict):
        raise ValueError("results body must be a JSON object")
    client_event_id = body.get("client_event_id")
    session_id = body.get("session_id")
    round_id = body.get("round_id")
    fmt = body.get("format")
    score = body.get("score")
    total = body.get("total")
    if not (isinstance(client_event_id, str) and client_event_id):
        raise ValueError("client_event_id is required")
    if not (isinstance(session_id, str) and session_id):
        raise ValueError("session_id is required")
    if not (isinstance(round_id, str) and ROUND_ID_RE.match(round_id)):
        raise ValueError("round_id is invalid")
    if fmt not in FORMATS:
        raise ValueError("format is invalid")
    if isinstance(score, bool) or not isinstance(score, int) or score < 0:
        raise ValueError("score must be a non-negative integer")
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        raise ValueError("total must be a positive integer")
    score = min(score, total)
    missed = _clean_missed(body.get("missed"))
    events.insert_events(conn, [{
        "client_event_id": client_event_id,
        "session_id": session_id,
        "event_type": "quiz_round",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "course_id": course_id,
        "topic_id": round_id,
        "payload": {"format": fmt, "score": score, "total": total, "missed": missed},
    }])
    consume_round(content_dir, course_id, round_id)
    return {"ok": True}


# ---- stats: computed live from quiz_round events, no stored aggregates ----

def _pct(score, total):
    return min(100, round(score / total * 100)) if total else 0


def _quiz_streak_days(conn, course_id, today=None):
    """Consecutive UTC days with >=1 played round in this course, anchored at
    today or yesterday — same rule as stats.streak_days, scoped to one course
    and to quiz_round events only."""
    today = today or datetime.now(timezone.utc).date()
    rows = conn.execute(
        "SELECT DISTINCT substr(occurred_at, 1, 10) AS day FROM events "
        "WHERE event_type = 'quiz_round' AND course_id = ? ORDER BY day DESC",
        (course_id,),
    ).fetchall()
    days = []
    for r in rows:
        try:
            days.append(date.fromisoformat(r["day"]))
        except ValueError:
            continue
    if not days or days[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for prev, cur in zip(days, days[1:]):
        if prev - cur != timedelta(days=1):
            break
        streak += 1
    return streak


def quiz_stats(conn, course_id, *, today=None):
    """Computed entirely from quiz_round events — no stored aggregates
    (decision 8): rounds played, best score as a %, per-format plays + best %,
    last-10 history (newest first), and the course's quiz play streak."""
    evs = _quiz_round_events(conn, course_id)
    per_format = {}
    for fmt in FORMATS:
        fmt_evs = [e for e in evs if e["format"] == fmt]
        if not fmt_evs:
            continue
        per_format[fmt] = {
            "plays": len(fmt_evs),
            "bestPct": max(_pct(e["score"], e["total"]) for e in fmt_evs),
        }
    history = [
        {"date": e["occurred_at"][:10], "format": e["format"], "score": e["score"], "total": e["total"]}
        for e in evs[-10:]
    ][::-1]
    return {
        "roundsPlayed": len(evs),
        "bestPct": max((_pct(e["score"], e["total"]) for e in evs), default=0),
        "perFormat": per_format,
        "history": history,
        "streakDays": _quiz_streak_days(conn, course_id, today=today),
    }
