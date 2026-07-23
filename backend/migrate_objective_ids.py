"""Deterministic Phase-0 migration: schemaVersion-2 courses (embedded objectives) ->
schemaVersion-3 (objectives registry + objectiveIds refs). No LLM, no content change --
a pure id-stamp, so it is lossless and idempotent. Writes a pre-migration backup sidecar
before overwriting, and skips courses already at v3.

Run on a COPY of content/ first, verify, and only then against the live tree (after the
daily backup is confirmed). Usage:
    .venv/bin/python -m backend.migrate_objective_ids [CONTENT_DIR]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import fsutil, objectives


def migrate(content_dir, *, now=None):
    content_dir = Path(content_dir)
    counts = {"migrated": 0, "clean": 0, "errors": 0}
    if not content_dir.exists():
        return counts
    for child in sorted(content_dir.iterdir()):
        manifest_path = child / "course.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (ValueError, OSError) as exc:
            print(f"ERROR {child.name}: course.json does not parse ({exc})")
            counts["errors"] += 1
            continue
        version = manifest.get("schemaVersion", 0)
        if isinstance(version, bool) or not isinstance(version, (int, float)):
            # a schemaVersion we can't interpret must draw operator attention, not be
            # silently skipped or written to.
            print(f"ERROR {child.name}: schemaVersion is not numeric ({version!r})")
            counts["errors"] += 1
            continue
        if version >= 3:
            print(f"skip  {child.name}: already schemaVersion 3")
            counts["clean"] += 1
            continue
        if version != 2:
            # legacy (pre-compile) course with no objectives -> nothing to id-stamp;
            # leave it exactly as-is (Phase 0 does not enrich content).
            print(f"skip  {child.name}: not a compiled (v2) course")
            counts["clean"] += 1
            continue
        try:
            disk = objectives.build_registry(manifest)
        except Exception as exc:  # one bad course must not abort the batch
            print(f"ERROR {child.name}: build_registry failed ({exc})")
            counts["errors"] += 1
            continue
        ts = now or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        try:
            (child / f"course.json.pre-objid-{ts}").write_text(manifest_path.read_text())
            fsutil.write_text_atomic(manifest_path,
                                     json.dumps(disk, indent=2, ensure_ascii=False))
        except Exception as exc:
            print(f"ERROR {child.name}: write failed ({exc})")
            counts["errors"] += 1
            continue
        n = len(disk.get("objectives", []))
        print(f"ok    {child.name}: migrated to schemaVersion 3, {n} objectives")
        counts["migrated"] += 1
    return counts


def main():
    from backend import courses
    content_dir = sys.argv[1] if len(sys.argv) > 1 else courses.CONTENT_DIR
    result = migrate(content_dir)
    print(f"\n{result['migrated']} migrated, {result['clean']} clean, {result['errors']} errors")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
