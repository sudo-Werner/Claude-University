"""Graded capstone (assessment-integrity Item A): rubric + submission grading.

The exploration capstone (generation.ensure_capstone) stays read-only; this module
adds the assessment half: a rubric stamped into the cached capstone JSON on first
need (read-time upgrade — legacy caches on the Pi are only extended, never
regenerated), a rubric-based grading call, and a server-recorded capstone_result
event. Capstone results are transcript-only credit: they feed neither the mastery
accuracy pool nor course_passed (courses on the Pi must not retroactively lock).
"""

import html as _html
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import events, fsutil, generation

CAPSTONE_PASS = 0.7

_MET_VALUES = ("met", "partial", "unmet")
_MET_POINTS = {"met": 1.0, "partial": 0.5, "unmet": 0.0}


def _capstone_path(content_dir, course_id, scope):
    return Path(content_dir) / course_id / "capstones" / f"{scope}.json"


def load_capstone(content_dir, course_id, scope):
    path = _capstone_path(content_dir, course_id, scope)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("items"), list) else None


def valid_rubric(items):
    if not (isinstance(items, list) and 4 <= len(items) <= 6):
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        if not (isinstance(it.get("criterion"), str) and it["criterion"].strip()):
            return False
    return True


def _scope_objective_texts(manifest, scope):
    """Objective texts for the rubric prompt: course outcomes for scope="course",
    module outcomes otherwise. Tolerates both objective dicts (schema v2) and the
    legacy plain-string module outcomes that exam_prompt already handles."""
    if scope == "course":
        objs = manifest.get("outcomes", []) or []
    else:
        module = next((m for m in manifest.get("modules", []) if m.get("id") == scope), None)
        objs = (module or {}).get("outcomes", []) or []
    out = []
    for o in objs:
        text = o.get("text") if isinstance(o, dict) else o
        if isinstance(text, str) and text.strip():
            out.append(text)
    return out


def rubric_prompt(*, capstone, objective_texts, scope_title):
    items = "; ".join(
        f'{it.get("title", "")}: {it.get("detail", "")}'
        for it in capstone.get("items", []) if isinstance(it, dict))
    objectives = "; ".join(objective_texts)
    return (
        f'You are writing the assessment RUBRIC for a capstone titled "{scope_title}" '
        "on a personal learning platform. The learner will submit a piece of their own "
        "work applying what they studied; the rubric is what that work is judged "
        "against.\n"
        f"The capstone's real-world connections: {items}\n"
        + (f"The objectives this scope taught: {objectives}\n" if objectives else "")
        + "Write 4 to 6 rubric criteria. Each criterion is ONE assessable sentence — a "
        "concrete, observable quality a grader can find evidence for in the submission "
        "(never 'understands' or 'appreciates'). Reply with ONLY a JSON object, no "
        'prose, no fence:\n{"rubric":[{"criterion":"<one assessable sentence>"}]}'
    )


def ensure_rubric(content_dir, course_id, scope, capstone, manifest, *, generate):
    """Stamp a rubric into the cached capstone JSON on first need (read-time upgrade,
    same pattern as generation._with_refreshed_source_types: legacy caches on the Pi
    are only extended, never regenerated). generate(prompt, validate) -> dict.
    Criteria are plain text: html.escape'd here, rendered raw client-side."""
    if valid_rubric(capstone.get("rubric")):
        return capstone
    prompt = rubric_prompt(
        capstone=capstone,
        objective_texts=_scope_objective_texts(manifest, scope),
        scope_title=capstone.get("title", ""),
    )
    obj = generate(prompt, lambda o: isinstance(o, dict) and valid_rubric(o.get("rubric")))
    capstone["rubric"] = [
        {"criterion": _html.escape(r["criterion"], quote=True)} for r in obj["rubric"]
    ]
    path = _capstone_path(content_dir, course_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(capstone, indent=2, ensure_ascii=False))
    return capstone


def capstone_grade_prompt(*, capstone, rubric, work, scope_label):
    criteria = "\n".join(f'{i}. {r["criterion"]}' for i, r in enumerate(rubric))
    return (
        "You are a fair, rigorous grader assessing a learner's capstone submission "
        f"for {scope_label} on a personal learning platform. Judge the submission "
        "against each rubric criterion — nothing else.\n"
        f"Capstone brief: {capstone.get('intro', '')}\n"
        f"Rubric criteria, by index:\n{criteria}\n\n"
        f"Learner's submission:\n{work}\n\n"
        "Grade EVERY criterion, in order. For each criterion include evidence: a "
        "short verbatim quote from the submission that your verdict rests on (empty "
        "string only if the submission contains nothing relevant to the criterion). "
        "Base each verdict only on what the evidence shows.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"perCriterion":[{"index":<criterion index>,"met":"met"|"partial"|"unmet",'
        '"note":"<one sentence addressed to \'you\': what the submission shows for '
        'this criterion and what would lift it>","evidence":"<verbatim quote from '
        'the submission, empty if none>"}],"summary":"<two or three sentences '
        "addressed to 'you': overall strengths, then the most important "
        'improvement>"}'
    )


def valid_capstone_grade(obj, rubric):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("summary"), str) and obj["summary"].strip()):
        return False
    per = obj.get("perCriterion")
    if not (isinstance(per, list) and len(per) == len(rubric)):
        return False
    seen = set()
    for g in per:
        if not isinstance(g, dict) or g.get("met") not in _MET_VALUES:
            return False
        if not (isinstance(g.get("note"), str) and g["note"].strip()):
            return False
        if not isinstance(g.get("evidence"), str):
            return False
        idx = g.get("index")
        if not (isinstance(idx, int) and not isinstance(idx, bool)) or idx in seen:
            return False
        seen.add(idx)
    return seen == set(range(len(rubric)))


def score_grade(per_criterion):
    points = sum(_MET_POINTS[g["met"]] for g in per_criterion)
    return round(points / len(per_criterion), 4)


def record_result(conn, course_id, scope, result):
    """Server-recorded capstone_result (mirror of exams.record_result). Stored
    perCriterion entries keep met/note but drop evidence — the quote is a grading
    reliability lever, not learner state (same rule as exam grading)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE event_type = 'capstone_result' AND course_id = ? AND topic_id = ?",
        (course_id, scope),
    ).fetchone()
    attempt = row["n"] + 1
    stored = [{"index": g["index"], "met": g["met"], "note": g["note"]}
              for g in result["perCriterion"]]
    events.insert_events(conn, [{
        "client_event_id": f"server-{uuid.uuid4()}",
        "session_id": "server",
        "device": "server",
        "topic_id": scope,
        "course_id": course_id,
        "event_type": "capstone_result",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"scope": scope, "score": result["score"], "passed": result["passed"],
                    "perCriterion": stored, "summary": result["summary"],
                    "attempt": attempt},
    }])
    return attempt


def submit_capstone(content_dir, conn, course_id, scope, work, *, manifest, generate):
    """Grade a capstone submission against its (ensured) rubric and record the
    result. Returns the graded result dict (with rubric and evidence, for the API
    response), or None when no capstone has been generated yet. Lets ClaudeError
    propagate — the route maps it to 502/503 exactly like the exam grader."""
    with generation._gen_lock(("capstone", course_id, scope)):
        capstone = load_capstone(content_dir, course_id, scope)
        if capstone is None:
            return None
        capstone = ensure_rubric(content_dir, course_id, scope, capstone, manifest,
                                 generate=generate)
    rubric = capstone["rubric"]
    scope_label = ("the whole course" if scope == "course"
                   else f'the module "{capstone.get("title", "")}"')
    graded = generate(
        capstone_grade_prompt(capstone=capstone, rubric=rubric, work=work,
                              scope_label=scope_label),
        lambda o: valid_capstone_grade(o, rubric),
    )
    per = sorted(graded["perCriterion"], key=lambda g: g["index"])
    per = [{"index": g["index"], "met": g["met"],
            "note": generation.sanitize_html(g["note"]),
            "evidence": g["evidence"]} for g in per]
    score = score_grade(per)
    result = {
        "scope": scope,
        "score": score,
        "passed": score >= CAPSTONE_PASS,
        "perCriterion": per,
        "summary": generation.sanitize_html(graded["summary"]),
    }
    result["attempt"] = record_result(conn, course_id, scope, result)
    result["rubric"] = rubric
    return result
