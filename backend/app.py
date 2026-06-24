from pathlib import Path
import re as _re

from flask import Flask, jsonify, request, send_from_directory

from backend import db, events, profile, queries, courses, claude_client, generation, srs, mastery

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
        finally:
            conn.close()
        return jsonify({**manifest, "mastery": m, "masteryCounts": mastery.mastery_counts(m)})

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
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_lesson)
        try:
            lesson = generation.ensure_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance,
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
        generate = lambda prompt: claude_client.run_structured(prompt, validate=generation.valid_lesson)
        try:
            lesson = generation.deepen_lesson(
                courses.CONTENT_DIR, course_id, lesson_id, prof_data,
                generate=generate, performance=performance,
            )
        except claude_client.ClaudeAuthError:
            return jsonify({"error": "Claude needs re-authentication on the Pi — run `claude` there to log in again.", "code": "reauth"}), 503
        except claude_client.ClaudeError:
            return jsonify({"error": "could not deepen this lesson"}), 502
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)

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
