"""Append-only JSONL sink for figure-selection telemetry. One line per figure
slot at generation/backfill time. Filesystem-only (the generation hook and the
backfill CLI have no DB connection), never raises — a telemetry failure must
never affect a lesson."""

import json
from datetime import datetime, timezone
from pathlib import Path

TELEMETRY_FILENAME = "figure-telemetry.jsonl"


def record(content_dir, event):
    """Append one figure-selection record (event dict + ISO 'ts') as a JSON line."""
    try:
        path = Path(content_dir) / TELEMETRY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({**event, "ts": datetime.now(timezone.utc).isoformat()},
                          ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read(content_dir):
    """Parse the JSONL back into a list of dicts. Missing file -> []; malformed
    lines skipped."""
    path = Path(content_dir) / TELEMETRY_FILENAME
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows
