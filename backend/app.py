from pathlib import Path
import re as _re

from flask import Flask, jsonify, request, send_from_directory

from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery, notes, compiler, stats, exams, spine, remediation, transcript, capstone

_ID_RE = _re.compile(r"^[a-z0-9-]+$")


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
        conn = db.get_connection(path)
        try:
            result = events.insert_events(conn, body.get("events", []))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()
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

    @app.get("/api/stats")
    def get_stats():
        conn = db.get_connection(path)
        try:
            streak = stats.streak_days(conn)
        finally:
            conn.close()
        return jsonify({"streakDays": streak})

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
        generate_sourced = lambda prompt, validate: claude_client.run_sourced(prompt, validate=validate)
        verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
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

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>")
    def get_lesson(course_id, lesson_id):
        if not _ID_RE.match(course_id) or not _ID_RE.match(lesson_id):
            return jsonify({"error": "lesson not found"}), 404
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is not None:
            return jsonify(lesson)
        conn = db.get_connection(path)
        try:
            prof = profile.latest_profile(conn)
            performance = mastery.performance_summary(conn, courses.CONTENT_DIR, course_id)
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        # Phase 2: generate lessons WITH web search so they're grounded in real accredited
        # sources (run_sourced returns (lesson, captured_sources)).
        generate = lambda prompt: claude_client.run_sourced(prompt, validate=generation.valid_lesson)
        # University-grade self-consistency: an audit-first, non-web pass reconciles terminology
        # and guarantees every end-question is answerable from the body (rewrites only on a defect).
        verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance, verify_generate=verify,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not prepare this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)

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
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
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
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
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
        finally:
            conn.close()
        prof_data = (prof or {}).get("data")
        # Phase 2: re-ground the deepened lesson in real accredited sources too.
        generate = lambda prompt: claude_client.run_sourced(prompt, validate=generation.valid_lesson)
        verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
        try:
            lesson = generation.deepen_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance, verify_generate=verify,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not deepen this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)

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
        generate = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
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
                body.get("notes", ""), body.get("chat", []),
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
        body = request.get_json(silent=True) or {}
        # The side-chat can web-search so it isn't limited to the model's training cutoff;
        # the model only searches when the question needs current/factual info.
        stream_fn = lambda p: claude_client.stream(p, tools=["WebSearch", "WebFetch"])
        sse = generation.lesson_chat_sse(
            lesson, body.get("messages", []), stream_fn=stream_fn,
            solution_revealed=bool(body.get("solutionRevealed")))
        return app.response_class(sse, mimetype="text/event-stream")

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

    @app.post("/api/courses/<course_id>/revise")
    def post_course_revise(course_id):
        if not _ID_RE.match(course_id):
            return jsonify({"error": "course not found"}), 404
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        body = request.get_json(silent=True) or {}
        generate_sourced = lambda prompt, validate: claude_client.run_sourced(prompt, validate=validate)
        verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
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

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "platform.html")

    @app.get("/src/<path:filename>")
    def src_files(filename):
        return send_from_directory(frontend_dir / "src", filename)

    @app.get("/styles.css")
    def styles():
        return send_from_directory(frontend_dir, "styles.css")

    return app
