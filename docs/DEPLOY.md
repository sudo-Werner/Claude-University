# Deploying to the Pi — canonical procedure

**The Pi is the production data store.** `content/courses/` (course manifests, cached
lessons, spine files) and `backend/data/` (learning.db) exist ONLY on the Pi. They are
created at runtime and are not in git. Any deploy step that can delete unmatched files
on the Pi can destroy them.

## Incident 2026-07-15

A deploy used `rsync --delete` with `content/` unexcluded and wiped all course content
on the Pi (recovered from Claude CLI transcripts). Hence the hard rules below.

## Hard rules

1. **NEVER use `--delete`** in the deploy rsync. No exceptions. If stale files must be
   removed, delete them by explicit path on the Pi after checking what they are.
2. Always exclude the runtime data trees: `backend/data/`, `data/`, `content/`.
3. Before restarting the service, check for in-flight generations:
   `pgrep -fa claude | grep -v pgrep` (waitress's own path contains
   "claude_university" — inspect the list, don't trust a bare count).

## The command

```bash
rsync -az \
  --exclude='.git/' --exclude='.venv/' --exclude='node_modules/' \
  --exclude='__pycache__/' --exclude='.pytest_cache/' --exclude='.superpowers/' \
  --exclude='backend/data/' --exclude='data/' --exclude='content/' \
  /Users/wernervanellewee/Projects/Claude_Education/ werner@192.168.2.69:~/claude_university/
```

Then: `sudo systemctl restart claude-university` and verify
`curl -s http://localhost:8200/api/health` returns `{"status":"ok"}` AND
`curl -s http://localhost:8200/api/courses` still lists the courses (an empty list
after a deploy is a red flag — stop and investigate before doing anything else).

## Backups

A daily cron on the Pi (03:30) tars `content/` and snapshots `learning.db` into
`~/backups/claude_university/` (7 kept), which the existing weekly rclone job syncs
to Google Drive. Verify with: `ls -lh ~/backups/claude_university/` on the Pi.
