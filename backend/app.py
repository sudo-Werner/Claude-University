from pathlib import Path
import re as _re

from flask import Flask, jsonify, request, send_from_directory

from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats, exams, spine, remediation, transcript, capstone, review_items, feedback, quiz

_ID_RE = _re.compile(r"^[a-z0-9-]+$")
_IMAGE_FILENAME_RE = _re.compile(r"^[a-z0-9-]+-\d\.(jpg|png|webp)$")


def _lesson_concepts(course_id, lesson_id):
    """Response-only concept term list for the chip UI, read live from the spine at
    request time — never written into the cached lesson file. Defensive: a missing
    or corrupt spine.json, a missing entry for this lesson, or a malformed concepts
    list/item all degrade to [] rather than ever failing the lesson response."""
    entry = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"].get(lesson_id)
    if not isinstance(entry, dict):
        return []
    concepts = entry.get("concepts")
    if not isinstance(concepts, list):
        return []
    return [c["term"] for c in concepts
            if isinstance(c, dict) and isinstance(c.get("term"), str) and c["term"].strip()]


def _with_concepts(lesson, course_id, lesson_id):
    """Attach `concepts` (list of term strings) to a lesson response dict, read live
    from spine.json. Omitted entirely when there is no valid spine entry, so legacy
    lessons stay invisible to the chip UI. Returns a NEW dict — the cached lesson
    file on disk is never touched."""
    concepts = _lesson_concepts(course_id, lesson_id)
    return {**lesson, "concepts": concepts} if concepts else lesson


def _resolve_analogy_concept(course_id, lesson_id, concept):
    """Match a client-claimed concept term against this lesson's OWN spine entry
    (exact string match). Returns the server's own {"term", "definition", "summary"}
    dict, or None if `concept` is not a string, there is no spine entry for this
    lesson, or no concept in it has that exact term — the caller then falls back to
    the normal chat prompt, never a 4xx."""
    if not isinstance(concept, str):
        return None
    entry = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"].get(lesson_id)
    if not isinstance(entry, dict):
        return None
    concepts = entry.get("concepts")
    if not isinstance(concepts, list):
        return None
    for c in concepts:
        if isinstance(c, dict) and c.get("term") == concept:
            return {"term": c.get("term") or "", "definition": c.get("definition") or "",
                    "summary": entry.get("summary") or ""}
    return None


def create_app(db_path=None):
    app = Flask(__name__)
    path = db_path or db.DEFAULT_DB_PATH

    # Ensure the schema exists at startup.
    init_conn = db.get_connection(path)
    db.init_db(init_conn)
    init_conn.close()

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/events")
    def post_events():
        body = request.get_json(silent=True) or {}
        raw_events = body.get("events", [])
        conn = db.get_connection(path)
        try:
            result = events.insert_events(conn, raw_events)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()
        # Lesson-completion top-up (decision 6, fail-open, non-blocking): new
        # material unlocks fresh quiz-round grounding, so nudge each newly-
        # completed lesson's course to restock its Arcade bank. kick_restock's
        # own try-lock and floor check make a spurious nudge (duplicate
        # replay, bank already full) a no-op.
        generate = claude_client.structured_generate
        nudged = set()
        for ev in raw_events:
            if not isinstance(ev, dict) or ev.get("event_type") != "lesson_completed":
                continue
            cid = ev.get("course_id")
            if isinstance(cid, str) and _ID_RE.match(cid) and cid not in nudged:
                nudged.add(cid)
                try:
                    quiz.kick_restock(courses.CONTENT_DIR, path, cid, generate=generate)
                except Exception:
                    pass  # a restock nudge must never break event ingestion
        return jsonify(result)

    @app.get("/api/events")
    def get_events():
        conn = db.get_connection(path)
        try:
            result = queries.query_events(
                conn,
                since=request.args.get("since"),
                session_id=request.args.get("session_id"),
                event_type=request.args.get("type"),
                limit=int(request.args.get("limit", 1000)),
            )
        finally:
            conn.close()
        return jsonify({"events": result})

    @app.post("/api/feedback")
    def post_feedback():
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        conn = db.get_connection(path)
        try:
            feedback.insert_feedback(
                conn,
                text=body.get("text"),
                screen=body.get("screen"),
                course_id=body.get("courseId"),
                lesson_id=body.get("lessonId"),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()
        return jsonify({"ok": True})

    @app.get("/api/stats")
    def get_stats():
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            prof_data = (prof or {}).get("data")
            cadence = prof_data.get("streakCadence") if isinstance(prof_data, dict) else None
            if cadence != "weekly":
                cadence = "daily"  # default, and the fallback for any forged/unknown value
            streak = (stats.weekly_streak_weeks(conn) if cadence == "weekly"
                     else stats.streak_days(conn))
            heatmap = stats.heatmap(conn, courses.CONTENT_DIR)
        finally:
            conn.close()
        return jsonify({"streakDays": streak, "streakCadence": cadence, "heatmap": heatmap})

    @app.get("/api/activity")
    def get_activity():
        try:
            limit = int(request.args.get("limit", 50))
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 200))
        conn = db.get_connection(path)
        try:
            activity = stats.recent_activity(conn, courses.CONTENT_DIR, limit=limit)
        finally:
            conn.close()
        return jsonify({"activity": activity})

    @app.get("/api/transcript")
    def get_transcript():
        conn = db.get_connection(path)
        try:
            result = transcript.transcript(conn, courses.CONTENT_DIR)
        finally:
            conn.close()
        return jsonify({"courses": result})

    @app.post("/api/profile")
    def post_profile():
        body = request.get_json(silent=True) or {}
        conn = db.get_connection(path)
        try:
            result = profile.save_profile(conn, body)
        finally:
            conn.close()
        return jsonify(result)

    @app.get("/api/profile")
    def get_profile():
        conn = db.get_connection(path)
        try:
            result = profile.latest_profile(conn)
        finally:
            conn.close()
        return jsonify(result or {})

    @app.get("/api/courses")
    def get_courses():
        conn = db.get_connection(path)
        try:
            result = courses.list_courses(conn, courses.CONTENT_DIR)
        finally:
            conn.close()
        return jsonify({"courses": result})

    @app.post("/api/courses")
    def post_course():
        body = request.get_json(silent=True) or {}
        if not body.get("title") or not body.get("modules"):
            return jsonify({"error": "title and modules are required"}), 400
        manifest = courses.write_course(courses.CONTENT_DIR, body)
        return jsonify({"course": manifest}), 201

    @app.post("/api/courses/compile")
    def post_course_compile():
        body = request.get_json(silent=True) or {}
        brief = body.get("learnerBrief")
        if not isinstance(brief, dict) or not brief.get("goal"):
            return jsonify({"error": "learnerBrief with a goal is required"}), 400
        # Grounded stages web-search; structured stages don't — same wiring as lessons.
        generate_sourced = claude_client.sourced_generate
        verify = claude_client.structured_generate
        try:
            compiled = compiler.compile_course(brief, generate_sourced=generate_sourced, verify=verify)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "couldn't build your program, try again"}), 502
        if not generation.valid_compiled_course(compiled):
            return jsonify({"error": "couldn't build your program, try again"}), 502
        return jsonify({"course": compiled})

    @app.post("/api/courses/chat")
    def post_course_chat():
        body = request.get_json(silent=True) or {}
        messages = body.get("messages", [])
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        stream_fn = claude_client.stream
        sse = generation.chat_sse(messages, prof_data, stream_fn=stream_fn)
        return app.response_class(sse, mimetype="text/event-stream")

    @app.get("/api/courses/<course_id>")
    def get_course(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            m = mastery.lesson_mastery(conn, courses.CONTENT_DIR, course_id)
            ex = exams.exam_status(conn, course_id, manifest)
        finally:
            conn.close()
        return jsonify({**manifest, "mastery": m, "masteryCounts": mastery.mastery_counts(m),
                        "exams": ex, "coursePassed": exams.course_passed(ex, manifest)})

    @app.get("/api/courses/<course_id>/notes")
    def get_course_notes(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        summary = notes.course_notes_summary(courses.CONTENT_DIR, course_id, manifest)
        return jsonify({"lessons": summary})

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>")
    def get_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is not None:
            return jsonify(_with_concepts(lesson, course_id, lesson_id))
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            performance = mastery.performance_summary(conn, courses.CONTENT_DIR, course_id)
            prior_knowledge = queries.latest_prior_knowledge(conn, course_id, lesson_id)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        # Phase 2: generate lessons WITH web search so they're grounded in real accredited
        # sources (run_sourced returns (lesson, captured_sources)).
        generate = lambda prompt: claude_client.run_sourced(prompt, validate=generation.valid_lesson)
        # University-grade self-consistency: an audit-first, non-web pass reconciles terminology
        # and guarantees every end-question is answerable from the body (rewrites only on a defect).
        verify = claude_client.structured_generate
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance, verify_generate=verify,
                prior_knowledge=prior_knowledge,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(_with_concepts(lesson, course_id, lesson_id))

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/status")
    def lesson_status(course_id, lesson_id):
        # Prior-knowledge activation (design doc decision #1): the client cannot know
        # beforehand whether a lesson GET will be an instant cache hit or a ~110s
        # generation. This route answers that so the question card only appears when
        # generation is actually about to happen. No DB connection, no lock, no
        # generation call — this route can never trigger one.
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "lesson not found"}), 404
        if lesson_id not in {l["id"] for l in courses.flatten_lessons(manifest)}:
            return jsonify({"error": "lesson not found"}), 404
        generated = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id) is not None
        return jsonify({"generated": generated})

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/grade")
    def grade_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True) or {}
        answer = (body.get("answer") or "").strip()
        if not answer:
            return jsonify({"error": "answer is required"}), 400
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_grade)
        try:
            result = generation.grade_answer(
                courses.CONTENT_DIR, course_id, lesson_id, answer, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade this answer"}), 502
        if result is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(result)

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/explain")
    def explain_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True) or {}
        explanation = (body.get("explanation") or "").strip()
        if not explanation:
            return jsonify({"error": "explanation is required"}), 400
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_explain)
        try:
            result = generation.explain_answer(
                courses.CONTENT_DIR, course_id, lesson_id, explanation, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not read your explanation"}), 502
        if result is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(result)

    @app.post("/api/courses/<course_id>/exams/<exam_key>")
    def start_exam(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        slots = exams.blueprint(manifest, exam_key)
        if slots is None:
            return jsonify({"error": "exam not found"}), 404
        conn = db.get_connection(path)
        try:
            status = exams.exam_status(conn, course_id, manifest)
            if exam_key == "final" and not exams.final_unlocked(status, manifest):
                return jsonify({"error": "The final is locked — pass every module exam first."}), 409
            # Bloom's corrective-then-reassess: while an exam is not yet passed, a
            # retake after a fail is blocked until that fail's gap review is completed.
            # First attempts have no failed result and pass straight through.
            if not status.get(exam_key, {}).get("passed"):
                latest = remediation.latest_failed_result(conn, course_id, exam_key)
                if latest is not None and not remediation.session_completed(
                        conn, courses.CONTENT_DIR, course_id, exam_key,
                        latest.get("attempt")):
                    return jsonify({"error": "Complete the gap review before retaking — that's the corrective step.",
                                    "code": "gap-review"}), 409
        finally:
            conn.close()
        spine_lessons = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"]
        prompt = exams.exam_prompt(manifest=manifest, exam_key=exam_key,
                                   slots=slots, spine_lessons=spine_lessons)
        try:
            with generation._gen_lock(("exam", course_id, exam_key)):
                obj = claude_client.run_structured(
                    prompt, validate=lambda o: exams.valid_exam(o, slots))
                exam = exams.finalize_exam(obj, slots, exam_key, course_id)
                exams.save_pending(courses.CONTENT_DIR, course_id, exam)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this exam"}), 502
        return jsonify(exams.client_view(exam))

    @app.post("/api/courses/<course_id>/exams/<exam_key>/submit")
    def submit_exam_route(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        answers = body.get("answers")
        generate = claude_client.structured_generate
        conn = db.get_connection(path)
        try:
            with generation._gen_lock(("exam", course_id, exam_key)):
                result = exams.submit_exam(
                    courses.CONTENT_DIR, conn, course_id, exam_key, answers,
                    manifest=manifest, generate=generate,
                )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade this exam — your answers were not lost, try again"}), 502
        finally:
            conn.close()
        if result is None:
            return jsonify({"error": "no exam in progress — start it again"}), 404
        return jsonify(result)

    @app.post("/api/courses/<course_id>/exams/<exam_key>/remediation")
    def start_remediation(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        if exam_key != "final" and not any(
                m.get("id") == exam_key for m in manifest.get("modules", [])):
            return jsonify({"error": "exam not found"}), 404
        conn = db.get_connection(path)
        try:
            failed = remediation.latest_failed_result(conn, course_id, exam_key)
        finally:
            conn.close()
        if failed is None:
            return jsonify({"error": "nothing to review — no failed attempt on record for this exam"}), 404
        spine_lessons = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"]
        generate = claude_client.structured_generate
        try:
            with generation._gen_lock(("remediation", course_id, exam_key)):
                session = remediation.ensure_session(
                    courses.CONTENT_DIR, course_id, exam_key, failed,
                    manifest=manifest, spine_lessons=spine_lessons, generate=generate,
                )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare the gap review — try again"}), 502
        return jsonify(session)

    @app.post("/api/courses/<course_id>/exams/<exam_key>/remediation/grade")
    def grade_remediation_apply(course_id, exam_key):
        if not _ID_RE.match(course_id) or not (exam_key == "final" or _ID_RE.match(exam_key)):
            return jsonify({"error": "exam not found"}), 404
        session = remediation.load_session(courses.CONTENT_DIR, course_id, exam_key)
        if session is None:
            return jsonify({"error": "no gap review on record for this exam"}), 404
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        gap_index = body.get("gapIndex")
        gaps = session.get("gaps", [])
        if not (isinstance(gap_index, int) and not isinstance(gap_index, bool)
                and 0 <= gap_index < len(gaps)):
            return jsonify({"error": "gapIndex must identify a gap in the review"}), 400
        gap = gaps[gap_index] if isinstance(gaps[gap_index], dict) else {}
        apply_item = gap.get("apply")
        # Legacy sessions on the Pi predate apply items — nothing to grade there.
        if not (isinstance(apply_item, dict)
                and isinstance(apply_item.get("prompt"), str) and apply_item["prompt"].strip()
                and isinstance(apply_item.get("modelAnswer"), str) and apply_item["modelAnswer"].strip()):
            return jsonify({"error": "this gap has no apply task"}), 400
        answer = body.get("answer")
        answer = answer.strip() if isinstance(answer, str) else ""
        if not answer:
            return jsonify({"error": "answer is required"}), 400
        # Reuse the exercise grader verbatim (verdict trio + note) — no new prompt builder.
        prompt = generation.grade_prompt(
            prompt_html=apply_item.get("prompt", ""),
            solution_ans=apply_item.get("modelAnswer", ""),
            solution_note="",
            answer=answer,
        )
        try:
            result = claude_client.run_structured(prompt, validate=generation.valid_grade)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade this answer"}), 502
        # modelAnswer is revealed only after grading, like a solution reveal.
        return jsonify({"verdict": result["verdict"],
                        "note": generation.sanitize_html(result["note"]),
                        "modelAnswer": apply_item.get("modelAnswer", "")})

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/deepen")
    def deepen_lesson_route(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            performance = mastery.performance_summary(conn, courses.CONTENT_DIR, course_id)
            prior_knowledge = queries.latest_prior_knowledge(conn, course_id, lesson_id)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        # Phase 2: re-ground the deepened lesson in real accredited sources too.
        generate = lambda prompt: claude_client.run_sourced(prompt, validate=generation.valid_lesson)
        verify = claude_client.structured_generate
        try:
            lesson = generation.deepen_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance, verify_generate=verify,
                prior_knowledge=prior_knowledge,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not deepen this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(_with_concepts(lesson, course_id, lesson_id))

    @app.get("/api/courses/<course_id>/capstone/<scope>")
    def get_capstone(course_id, scope):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        if scope != "course" and not _ID_RE.match(scope):
            return jsonify({"error": "not found"}), 404
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_capstone)
        try:
            capstone = generation.ensure_capstone(
                courses.CONTENT_DIR, course_id, scope, prof_data, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare the real-world connections"}), 502
        if capstone is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(capstone)

    @app.post("/api/courses/<course_id>/capstone/<scope>/submit")
    def submit_capstone_route(course_id, scope):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        if scope != "course" and not _ID_RE.match(scope):
            return jsonify({"error": "not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        work = body.get("work")
        work = work.strip() if isinstance(work, str) else ""
        if not work:
            return jsonify({"error": "work is required"}), 400
        generate = claude_client.structured_generate
        conn = db.get_connection(path)
        try:
            result = capstone.submit_capstone(
                courses.CONTENT_DIR, conn, course_id, scope, work,
                manifest=manifest, generate=generate,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade your capstone — your work was not lost, try again"}), 502
        finally:
            conn.close()
        if result is None:
            return jsonify({"error": "no capstone to submit against — open the capstone first"}), 404
        return jsonify(result)

    @app.get("/api/courses/<course_id>/library")
    def get_library(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        generate_sourced = lambda prompt: claude_client.run_sourced(prompt, validate=generation.valid_bibliography)
        try:
            library = generation.ensure_bibliography(
                courses.CONTENT_DIR, course_id, generate_sourced=generate_sourced,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not compile the course library"}), 502
        if library is None:
            return jsonify({"error": "course not found"}), 404
        # Phase 2: also surface the live roll-up of sources cited across generated lessons.
        library = {**library, "lessonSources": generation.course_lesson_sources(courses.CONTENT_DIR, course_id)}
        return jsonify(library)

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def get_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        return jsonify(notes.load_workspace(courses.CONTENT_DIR, course_id, lesson_id))

    @app.put("/api/courses/<course_id>/lessons/<lesson_id>/workspace")
    def put_workspace(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            record = notes.save_workspace(
                courses.CONTENT_DIR, course_id, lesson_id,
                body.get("notes", ""), body.get("chat", []), body.get("highlights", []),
            )
        except notes.WorkspaceTooLarge:
            return jsonify({"error": "notes too large"}), 413
        except ValueError:
            return jsonify({"error": "invalid workspace"}), 400
        return jsonify({"updatedAt": record["updatedAt"]})

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/chat")
    def post_lesson_chat(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            messages = []
        messages = [m for m in messages if isinstance(m, dict)]
        socratic = body.get("mode") == "socratic"
        teach = body.get("mode") == "teach"
        # Analogy on tap: a chip tap sends mode: "analogy" + a concept term. The term
        # is validated against this lesson's OWN spine entry (exact match); only then
        # do we build the analogy prompt, and only from the server's own copy of the
        # term/definition/summary. Any failure to resolve (no spine, unknown term,
        # wrong type, missing concept) falls straight through to the normal chat
        # path below — never a 4xx, same fail-open idiom as a forged socratic flag.
        analogy = None
        if body.get("mode") == "analogy":
            match = _resolve_analogy_concept(course_id, lesson_id, body.get("concept"))
            if match is not None:
                # DB conn (profile) and manifest (learnerBrief) are read ONLY here —
                # normal and socratic chat stay byte-identical to before this change.
                conn = db.get_connection(path)
                try:
                    prof = profile.latest_profile(conn)
                finally:
                    conn.close()
                manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
                analogy = {
                    **match,
                    "learner_brief": (manifest or {}).get("learnerBrief"),
                    "profile": (prof or {}).get("data"),
                }
        if analogy is not None or socratic or teach:
            # No web tools: analogy re-represents material already in context, the
            # socratic exercise is self-contained with the solution in context, and the
            # teach persona is an in-context conversation, not research — all three are
            # faster without a search round-trip.
            stream_fn = lambda p: claude_client.stream(p)
        else:
            # The side-chat can web-search so it isn't limited to the model's training cutoff;
            # the model only searches when the question needs current/factual info.
            stream_fn = lambda p: claude_client.stream(p, tools=["WebSearch", "WebFetch"])
        sse = generation.lesson_chat_sse(
            lesson, messages, stream_fn=stream_fn,
            solution_revealed=bool(body.get("solutionRevealed")), socratic=socratic,
            analogy=analogy, teach=teach)
        return app.response_class(sse, mimetype="text/event-stream")

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/teach")
    def teach_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            messages = []
        messages = [m for m in messages if isinstance(m, dict)]
        has_teacher_turn = any(
            m.get("role") == "user" and isinstance(m.get("content"), str) and m["content"].strip()
            for m in messages
        )
        if not has_teacher_turn:
            return jsonify({"error": "teach something first"}), 400
        prompt = generation.teach_grade_prompt(
            prompt_html=lesson.get("promptHtml", ""),
            solution_ans=lesson.get("solutionAns", ""),
            solution_note=lesson.get("solutionNote", ""),
            messages=messages,
        )
        try:
            result = claude_client.run_structured(prompt, validate=generation.valid_grade)
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not grade your teaching"}), 502
        return jsonify({"verdict": result["verdict"], "note": generation.sanitize_html(result["note"])})

    @app.get("/api/courses/<course_id>/reviews")
    def get_reviews(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            due = srs.due_lesson_ids(conn, courses.CONTENT_DIR, course_id)
        finally:
            conn.close()
        return jsonify({"due": due})

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>/review-items")
    def get_review_items(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        lesson_meta = next(
            (l for l in courses.flatten_lessons(manifest) if l["id"] == lesson_id), None)
        if lesson_meta is None:
            return jsonify({"error": "lesson not found"}), 404
        conn = db.get_connection(path)
        try:
            review_count = len(srs.reviews_by_lesson(conn, course_id).get(lesson_id, []))
        finally:
            conn.close()
        spine_entry = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"].get(lesson_id)
        cached_lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        existing_checks = cached_lesson.get("checks", []) if isinstance(cached_lesson, dict) else []
        generate = claude_client.structured_generate
        try:
            with generation._gen_lock(("review-items", course_id, lesson_id)):
                result = review_items.ensure_review_items(
                    courses.CONTENT_DIR, course_id, lesson_id, review_count,
                    lesson_meta=lesson_meta, spine_entry=spine_entry,
                    existing_checks=existing_checks, generate=generate,
                )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare fresh review questions"}), 502
        # userItems (highlight-derived, persistent) ride along with the AI-fresh set —
        # the review screen treats the combined list as one flat array of check items.
        return jsonify({"items": result["items"] + result.get("userItems", [])})

    @app.post("/api/courses/<course_id>/lessons/<lesson_id>/highlight-review-item")
    def post_highlight_review_item(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        lesson_meta = next(
            (l for l in courses.flatten_lessons(manifest) if l["id"] == lesson_id), None)
        if lesson_meta is None:
            return jsonify({"error": "lesson not found"}), 404
        body = request.get_json(silent=True) or {}
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > notes._MAX_HIGHLIGHT_TEXT:
            return jsonify({"error": "invalid highlight text"}), 400
        spine_entry = spine.load_spine(courses.CONTENT_DIR, course_id)["lessons"].get(lesson_id)
        generate = claude_client.structured_generate
        try:
            with generation._gen_lock(("highlight-item", course_id, lesson_id)):
                item = review_items.make_highlight_item(
                    courses.CONTENT_DIR, course_id, lesson_id, text.strip(),
                    lesson_meta=lesson_meta, spine_entry=spine_entry, generate=generate,
                )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not create a review item from that highlight"}), 502
        return jsonify({"item": item})

    @app.post("/api/courses/<course_id>/revise")
    def post_course_revise(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        generate_sourced = claude_client.sourced_generate
        verify = claude_client.structured_generate
        try:
            proposed = compiler.revise_course(
                manifest, body.get("messages", []),
                generate_sourced=generate_sourced, verify=verify,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "couldn't revise your course, try again"}), 502
        if not generation.valid_compiled_course(proposed):
            return jsonify({"error": "couldn't revise your course, try again"}), 502
        proposed_lesson_ids = {l["id"] for m in proposed.get("modules", []) for l in m.get("lessons", [])}
        existing_lessons = {l["id"]: l for m in manifest.get("modules", []) for l in m.get("lessons", [])}
        conn = db.get_connection(path)
        try:
            completed = courses.completed_lesson_ids(conn, course_id)
        finally:
            conn.close()
        progress_at_risk = [
            {"id": lid, "title": lesson["title"]}
            for lid, lesson in existing_lessons.items()
            if lid not in proposed_lesson_ids and lid in completed
        ]
        return jsonify({"course": proposed, "changeSummary": proposed.get("changeSummary", []), "progressAtRisk": progress_at_risk})

    @app.post("/api/courses/<course_id>/apply-revision")
    def post_apply_revision(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        revised = body.get("course")
        written = courses.apply_revision(courses.CONTENT_DIR, course_id, revised)
        if written is None:
            return jsonify({"error": "invalid revision"}), 400
        return jsonify({"course": written})

    @app.get("/api/courses/<course_id>/images/<filename>")
    def course_image(course_id, filename):
        if not _ID_RE.match(course_id) or not _IMAGE_FILENAME_RE.match(filename):
            return jsonify({"error": "image not found"}), 404
        return send_from_directory(str(courses.CONTENT_DIR / course_id / "images"), filename)

    @app.get("/api/courses/<course_id>/quiz/round")
    def get_quiz_round(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            pool = quiz.question_pool(courses.CONTENT_DIR, conn, course_id, manifest)
        finally:
            conn.close()
        if not pool:
            return jsonify({"status": "locked"})
        generate = claude_client.structured_generate
        round_ = quiz.serve_round(courses.CONTENT_DIR, course_id)
        # kick_restock is idempotent-safe (try-lock + its own floor check), so it
        # is always safe to call here — whether the bank was empty (generating)
        # or just below floor after serving.
        try:
            quiz.kick_restock(courses.CONTENT_DIR, path, course_id, generate=generate)
        except Exception:
            pass  # a spawn failure must not fail a successful round serve
        if round_ is None:
            return jsonify({"status": "generating"})
        return jsonify({"status": "ready", "round": round_})

    @app.post("/api/courses/<course_id>/quiz/results")
    def post_quiz_results(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        conn = db.get_connection(path)
        try:
            result = quiz.submit_results(courses.CONTENT_DIR, conn, course_id, body)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()
        generate = claude_client.structured_generate
        try:
            quiz.kick_restock(courses.CONTENT_DIR, path, course_id, generate=generate)
        except Exception:
            pass  # a spawn failure must not fail a successful result submission
        return jsonify(result)

    @app.get("/api/courses/<course_id>/quiz/stats")
    def get_quiz_stats(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        conn = db.get_connection(path)
        try:
            result = quiz.quiz_stats(conn, course_id)
        finally:
            conn.close()
        return jsonify(result)

    @app.post("/api/courses/<course_id>/quiz/question-chat")
    def post_quiz_question_chat(course_id):
        # Post-answer, ephemeral, stateless chat about one already-answered quiz
        # question (design doc decision 3) — no DB write, no events, mirrors the
        # lesson chat route's shape but takes lesson_id from the body, not the URL.
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "invalid request"}), 400
        lesson_id = body.get("lesson_id")
        if not (isinstance(lesson_id, str)
                and lesson_id in {l["id"] for l in courses.flatten_lessons(manifest)}):
            return jsonify({"error": "lesson not found"}), 404
        messages = body.get("messages")
        if not quiz.valid_question_chat_messages(messages):
            return jsonify({"error": "invalid messages"}), 400
        payload_error = quiz.valid_question_chat_payload(body.get("question"), body.get("answerGiven"))
        if payload_error:
            return jsonify({"error": payload_error}), 400
        # Fail-open grounding: a lesson not yet generated (None) still gets a chat,
        # just without lesson content in the prompt (quiz_question_chat_prompt handles it).
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        prompt = quiz.quiz_question_chat_prompt(lesson, body.get("question"), body.get("answerGiven"), messages)
        # No web tools (decision 4): this re-explains material already in the question +
        # lesson context, it doesn't need fresh facts.
        sse = quiz.quiz_question_chat_sse(prompt, stream_fn=lambda p: claude_client.stream(p))
        return app.response_class(sse, mimetype="text/event-stream")

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "platform.html")

    @app.get("/src/<path:filename>")
    def src_files(filename):
        return send_from_directory(frontend_dir / "src", filename)

    @app.get("/vendor/<path:filename>")
    def vendor_files(filename):
        return send_from_directory(frontend_dir / "vendor", filename)

    @app.get("/styles.css")
    def styles():
        return send_from_directory(frontend_dir, "styles.css")

    @app.get("/manifest.json")
    def manifest():
        return send_from_directory(frontend_dir, "manifest.json")

    @app.get("/sw.js")
    def service_worker():
        # Served from the root (not /src/) so its default scope covers the whole
        # app — a service worker can only control paths at or below its own URL.
        return send_from_directory(frontend_dir, "sw.js")

    @app.get("/icons/<filename>")
    def icon_files(filename):
        if filename not in ("icon-192.png", "icon-512.png"):
            return jsonify({"error": "not found"}), 404
        return send_from_directory(frontend_dir / "icons", filename)

    return app
