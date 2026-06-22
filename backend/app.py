from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from backend import db, events, profile, queries, courses


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

    @app.get("/api/courses/<course_id>")
    def get_course(course_id):
        manifest = courses.load_manifest(courses.CONTENT_DIR, course_id)
        if manifest is None:
            return jsonify({"error": "course not found"}), 404
        return jsonify(manifest)

    @app.get("/api/courses/<course_id>/lessons/<lesson_id>")
    def get_lesson(course_id, lesson_id):
        lesson = courses.load_lesson(courses.CONTENT_DIR, course_id, lesson_id)
        if lesson is None:
            return jsonify({"error": "lesson not found"}), 404
        return jsonify(lesson)

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
