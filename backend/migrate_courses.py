"""One-off migration: retrofit schemaVersion-2 rigor (level, hours, Bloom objectives,
prerequisite graph, grounding sources) onto existing courses, preserving lesson ids, order,
and study progress (progress is keyed on lesson ids in the DB, so preserving ids preserves it).
Run when the service is quiet (no in-flight generation). Re-runnable: already-v2 courses are
skipped. Usage: python -m backend.migrate_courses"""
import json
import sys
from pathlib import Path

from backend import claude_client, compiler, courses, generation


def _atomic_write(path, data):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def migrate(content_dir=courses.CONTENT_DIR):
    content_dir = Path(content_dir)
    generate_sourced = lambda prompt, validate: claude_client.run_sourced(prompt, validate=validate)
    verify = lambda prompt, validate: claude_client.run_structured(prompt, validate=validate)
    enriched = clean = errors = 0
    for child in sorted(content_dir.iterdir()):
        manifest_path = child / "course.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schemaVersion") == 2:
            print(f"skip  {child.name}: already schemaVersion 2")
            clean += 1
            continue
        try:
            compiled = compiler.enrich_course(manifest, generate_sourced=generate_sourced, verify=verify)
        except Exception as exc:  # one course failing must not abort the batch
            print(f"ERROR {child.name}: {exc}")
            errors += 1
            continue
        if not (generation.valid_compiled_course(compiled) and compiled.get("id") == manifest.get("id")):
            print(f"ERROR {child.name}: enrichment failed validation")
            errors += 1
            continue
        try:
            _atomic_write(manifest_path, compiled)
        except Exception as exc:  # a write failure on one course must not abort the batch
            print(f"ERROR {child.name}: write failed: {exc}")
            errors += 1
            continue
        lessons = sum(len(m.get("lessons", [])) for m in compiled["modules"])
        print(f"OK    {child.name}: level={compiled['level']['code']} "
              f"hours={compiled['targetHours']} lessons={lessons}")
        enriched += 1
    print(f"\ndone: {enriched} enriched, {clean} already-current, {errors} errors")
    return {"enriched": enriched, "clean": clean, "errors": errors}


if __name__ == "__main__":
    migrate()
    sys.exit(0)
