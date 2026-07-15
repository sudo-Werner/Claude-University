"""Corrective sessions (sub-project D): Bloom's mastery-learning correctives.

A failed exam's weak spots become ONE generated corrective session — each gap
re-explained from a DIFFERENT angle than the lesson took, plus fresh practice
items in the lesson-check shape. Practice grading happens client-side exactly
like lesson checks; answers land as lesson_check events (source="remediation")
so mastery sees them with no new mastery code. The session is persisted per
exam key and stamped with the attempt it remediates: a repeat request re-serves
it free, a newer failed attempt regenerates it.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend import exams, fsutil, generation

PRACTICE_MIN = 2
PRACTICE_MAX = 3


def latest_failed_result(conn, course_id, exam_key):
    """The newest exam_result for this key, if it is a fail with weak spots.
    Returns the payload dict, or None (nothing to remediate)."""
    row = conn.execute(
        "SELECT payload FROM events "
        "WHERE event_type = 'exam_result' AND course_id = ? AND topic_id = ? "
        "ORDER BY occurred_at DESC, id DESC LIMIT 1",
        (course_id, exam_key),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"]) if row["payload"] else {}
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("passed"):
        return None
    weak = [w for w in payload.get("weakSpots") or []
            if isinstance(w, dict) and w.get("lessonId")]
    if not weak:
        return None
    return {**payload, "weakSpots": weak}


def remediation_prompt(*, manifest, exam_key, weak_spots, spine_lessons):
    if exam_key == "final":
        scope = "the course final exam"
    else:
        module = next((m for m in manifest.get("modules", []) if m.get("id") == exam_key), None)
        scope = f'the exam for the module "{(module or {}).get("title", "")}"'
    gap_lines = []
    for i, w in enumerate(weak_spots, start=1):
        objectives = "; ".join(o for o in w.get("objectives", []) if isinstance(o, str))
        gap_lines.append(f'{i}. lessonId={w["lessonId"]} lesson: "{w.get("lessonTitle", "")}" '
                         f"missed objectives: {objectives or w.get('lessonTitle', '')}")
    vocab = exams._spine_vocab([{"lessonId": w["lessonId"]} for w in weak_spots], spine_lessons)
    vocab_block = ("Use EXACTLY this course vocabulary:\n" + "\n".join(vocab) + "\n\n") if vocab else ""
    return (
        f'You are a tutor on a personal learning platform. A learner just failed {scope} '
        f'of the course "{manifest.get("title", "")}" and needs a corrective review of the '
        "gaps below before retaking it.\n"
        f"Course context: {manifest.get('brief', '')}\n"
        + vocab_block +
        "Write EXACTLY one gap review per item below, in the SAME ORDER.\n"
        + "\n".join(gap_lines) + "\n\n"
        "For each gap:\n"
        "- explanationHtml: re-explain the missed objectives from a DIFFERENT angle than a "
        "textbook lesson would — use an analogy, a worked example, or a contrast with a "
        "common misconception. Do NOT summarize the lesson. 2-4 short paragraphs of simple "
        "HTML (p, em, strong, code, ul/ol/li only).\n"
        f"- practice: {PRACTICE_MIN}-{PRACTICE_MAX} NEW retrieval questions on those "
        "objectives (do not reuse exam wording). Each is either "
        '{"type":"mcq","prompt":"...","choices":["..."],"answer":0,"explanation":"..."} '
        "with 3-4 plausible choices and the 0-based correct answer, or "
        '{"type":"fill","prompt":"...","answer":"<the exact word or short phrase>",'
        '"explanation":"..."}. The explanation says why the answer is right. Where a missed '
        "objective's Bloom level is apply or higher, make its practice question require the "
        "learner to APPLY the objective — a scenario-based stem — not recall a definition, "
        "within the mcq/fill format above.\n"
        "Before emitting, re-answer each mcq question independently from the question text "
        "alone. Confirm the choice at answer is the answer you get, and that no distractor is "
        "also defensibly correct — if one is, rewrite it.\n"
        "Echo each gap's lessonId verbatim.\n"
        "Reply with ONLY a JSON object, no prose, no fence:\n"
        '{"gaps":[{"lessonId":"<from gap>","explanationHtml":"<html>","practice":[...]}]}'
    )


def valid_remediation(obj, weak_spots):
    if not isinstance(obj, dict):
        return False
    gaps = obj.get("gaps")
    if not isinstance(gaps, list) or len(gaps) != len(weak_spots):
        return False
    for g, w in zip(gaps, weak_spots):
        if not isinstance(g, dict) or g.get("lessonId") != w["lessonId"]:
            return False
        if not (isinstance(g.get("explanationHtml"), str) and g["explanationHtml"].strip()):
            return False
        practice = g.get("practice")
        if not (isinstance(practice, list) and PRACTICE_MIN <= len(practice) <= PRACTICE_MAX):
            return False
        if not all(generation.valid_check(p) for p in practice):
            return False
    return True


def finalize_session(obj, weak_spots, exam_key, course_id, attempt):
    """Sanitize learner-visible HTML and stamp gap metadata server-side (titles and
    objectives come from the recorded result, never from the model)."""
    gaps = []
    for g, w in zip(obj["gaps"], weak_spots):
        practice = []
        for p in g["practice"]:
            # Explicit fields only — never carry unknown model keys into stored content.
            item = {"type": p["type"],
                    "prompt": generation.sanitize_html(p["prompt"]),
                    "answer": p["answer"],  # verbatim: fill answers compare to learner typing
                    "explanation": generation.sanitize_html(p["explanation"])}
            if p["type"] == "mcq":
                item["choices"] = [generation.sanitize_html(c) for c in p["choices"]]
            practice.append(item)
        gaps.append({
            "lessonId": w["lessonId"],
            "lessonTitle": w.get("lessonTitle", ""),
            "objectives": [o for o in w.get("objectives", []) if isinstance(o, str)],
            "explanationHtml": generation.sanitize_html(g["explanationHtml"]),
            "practice": practice,
        })
    return {
        "examKey": exam_key,
        "courseId": course_id,
        "attempt": attempt,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gaps": gaps,
    }


def _path(content_dir, course_id, exam_key):
    return Path(content_dir) / course_id / "remediation" / f"{exam_key}.json"


def save_session(content_dir, course_id, session):
    path = _path(content_dir, course_id, session["examKey"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text_atomic(path, json.dumps(session, indent=2, ensure_ascii=False))


def load_session(content_dir, course_id, exam_key):
    path = _path(content_dir, course_id, exam_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("gaps"), list) else None


def prune(content_dir, course_id, keep_keys):
    rem_dir = Path(content_dir) / course_id / "remediation"
    if not rem_dir.is_dir():
        return
    for f in rem_dir.glob("*.json"):
        if f.stem not in keep_keys:
            f.unlink(missing_ok=True)


def ensure_session(content_dir, course_id, exam_key, failed_payload, *,
                   manifest, spine_lessons, generate):
    """Serve the stored session when it remediates the latest failed attempt;
    otherwise generate, persist, and return a fresh one."""
    attempt = failed_payload.get("attempt")
    existing = load_session(content_dir, course_id, exam_key)
    if existing is not None and existing.get("attempt") == attempt:
        return existing
    weak_spots = failed_payload["weakSpots"]
    prompt = remediation_prompt(manifest=manifest, exam_key=exam_key,
                                weak_spots=weak_spots, spine_lessons=spine_lessons)
    obj = generate(prompt, lambda o: valid_remediation(o, weak_spots))
    session = finalize_session(obj, weak_spots, exam_key, course_id, attempt)
    save_session(content_dir, course_id, session)
    return session
