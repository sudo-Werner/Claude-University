"""Monthly restore-check (Tier 3 item 13, docs/CHARTER-PHASE-2.md): proves the
daily content/DB backups in ~/backups/claude_university/ actually restore, not
just that they exist. Extracts the NEWEST backup to a throwaway temp dir
(never touches the live content/ or backend/data/), parses every course.json
through the same backend/courses.py code path the app itself uses, and
confirms the DB snapshot passes SQLite's own integrity check.

The 2026-07-15 data-loss incident (docs/DEPLOY.md) is what created these
backups; nothing had proven until now that they actually restore.

Usage (on the Pi, in its own venv):
    .venv/bin/python -m backend.restore_check [--backup-dir DIR]

Exits non-zero on any failure, so a cron entry's own mail-on-error (or a
log-tail alert) catches a silently-broken backup:
    0 4 1 * * cd ~/claude_university && .venv/bin/python -m backend.restore_check >> ~/backups/claude_university/restore-check.log 2>&1
"""

import argparse
import gzip
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

from backend import courses

DEFAULT_BACKUP_DIR = Path.home() / "backups" / "claude_university"


def _latest(backup_dir, pattern):
    matches = sorted(backup_dir.glob(pattern), key=lambda p: p.name, reverse=True)
    return matches[0] if matches else None


def check_content(tar_path, tmp_dir):
    extract_dir = tmp_dir / "content"
    extract_dir.mkdir()
    try:
        with tarfile.open(tar_path) as tf:
            try:
                tf.extractall(extract_dir, filter="data")
            except TypeError:
                tf.extractall(extract_dir)  # Python <3.12 without the filter= backport
    except (tarfile.TarError, OSError) as e:
        print(f"FAIL: {tar_path.name} is not a valid/readable tar archive: {e}")
        return False
    # The backup tars the whole content/ tree, which also holds non-course
    # assets (content/design/) — courses.CONTENT_DIR is content/courses/, so
    # that's the actual root to scan, not content/ itself.
    content_dir = extract_dir / "content" / "courses"
    if not content_dir.is_dir():
        print(f"FAIL: {tar_path.name} did not extract a content/courses/ directory")
        return False
    ok = True
    course_dirs = [p for p in sorted(content_dir.iterdir()) if p.is_dir()]
    if not course_dirs:
        print(f"FAIL: {tar_path.name} extracted no course directories")
        return False
    for course_dir in course_dirs:
        manifest = courses.load_manifest(content_dir, course_dir.name)
        if manifest is None:
            print(f"FAIL: {course_dir.name} course.json does not parse")
            ok = False
            continue
        lessons = courses.flatten_lessons(manifest)
        if not lessons:
            print(f"FAIL: {course_dir.name} manifest has zero lessons")
            ok = False
            continue
        print(f"OK: {course_dir.name} — {len(lessons)} lessons in manifest")
    return ok


def check_db(db_gz_path, tmp_dir):
    db_path = tmp_dir / "learning.db"
    try:
        with gzip.open(db_gz_path, "rb") as src, open(db_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
    except OSError as e:
        print(f"FAIL: {db_gz_path.name} is not a valid gzip file: {e}")
        return False
    try:
        conn = sqlite3.connect(db_path)
        try:
            result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        print(f"FAIL: {db_gz_path.name} does not open as a SQLite database: {e}")
        return False
    if result != "ok":
        print(f"FAIL: DB integrity_check returned {result!r}")
        return False
    print("OK: DB integrity_check passed")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()

    content_tar = _latest(args.backup_dir, "content-*.tar.gz")
    db_gz = _latest(args.backup_dir, "learning-*.db.gz")
    if content_tar is None or db_gz is None:
        print(f"FAIL: no backup files found in {args.backup_dir}")
        sys.exit(1)
    print(f"restore-check: content={content_tar.name} db={db_gz.name}")

    with tempfile.TemporaryDirectory(prefix="cu-restore-check-") as tmp:
        tmp_dir = Path(tmp)
        content_ok = check_content(content_tar, tmp_dir)
        db_ok = check_db(db_gz, tmp_dir)

    if content_ok and db_ok:
        print("restore-check PASSED")
        sys.exit(0)
    print("restore-check FAILED")
    sys.exit(1)


if __name__ == "__main__":
    main()
