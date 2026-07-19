import json
import os
import signal
import subprocess
import tempfile
import threading

DEFAULT_MODEL = "claude-sonnet-4-6"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/werner/.local/bin/claude")
# A rich lesson — especially a "go deeper" regeneration that asks for fundamentals +
# a worked example + a visual aid — legitimately takes ~110s via the Max CLI (measured
# 114s on the Pi). 120s was too tight and timed out mid-generation. Give 2x headroom.
_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "240"))

# The streaming path (lessons, compile, revise, chats) needs its own, longer ceiling:
# a rich lesson takes ~110s and a compile outline longer. 540s sits just under the
# waitress --channel-timeout=600, so the process dies before the HTTP channel does.
_STREAM_TIMEOUT = int(os.environ.get("CLAUDE_STREAM_TIMEOUT", "540"))


class ClaudeError(Exception):
    pass


class ClaudeAuthError(ClaudeError):
    """Claude CLI could not authenticate (expired/invalid Max login)."""


_AUTH_MARKERS = (
    "invalid api key", "unauthorized", " 401", "please run /login", "/login",
    "log in", "oauth", "authentication_error", "expired", "not logged in",
)


def _auth_failure_reason(stdout, stderr, *, scan_text):
    try:
        env = json.loads(stdout)
    except (ValueError, TypeError):
        env = None
    if isinstance(env, dict) and env.get("api_error_status") in (401, 403):
        return env.get("result") or ("Claude authentication failed (HTTP %s)." % env.get("api_error_status"))
    if scan_text:
        blob = ((stdout or "") + " " + (stderr or "")).lower()
        if any(m in blob for m in _AUTH_MARKERS):
            return "Claude authentication failed — the Pi login looks invalid."
    return None


def _env():
    env = dict(os.environ)
    # CRITICAL (confirmed in the Task 0 spike): a stale ANTHROPIC_API_KEY in the
    # environment makes Claude Code authenticate with that key instead of the Max
    # subscription OAuth — which 401s. Strip both so the subscription login is used.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.setdefault("HOME", "/home/werner")
    env["PATH"] = "/home/werner/.local/bin:" + env.get("PATH", "/usr/bin:/bin")
    return env


def _run_cli(args):
    proc = subprocess.run(
        [CLAUDE_BIN, *args], capture_output=True, text=True, env=_env(), timeout=_TIMEOUT
    )
    if proc.returncode != 0:
        reason = _auth_failure_reason(proc.stdout, proc.stderr, scan_text=True)
        if reason:
            raise ClaudeAuthError(reason)
        raise ClaudeError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
    reason = _auth_failure_reason(proc.stdout, "", scan_text=False)
    if reason:
        raise ClaudeAuthError(reason)
    return proc.stdout


def _spawn_cli(args):
    with tempfile.TemporaryFile(mode="w+") as tmpfile:
        proc = subprocess.Popen(
            [CLAUDE_BIN, *args], stdout=subprocess.PIPE, stderr=tmpfile,
            text=True, env=_env(), start_new_session=True,
        )

        def _kill_group():
            # start_new_session=True makes proc the leader of its own process group,
            # so killing the group (not just proc.pid) also kills any grandchildren a
            # wrapper script spawns — and closes every write end of the stdout pipe,
            # which is what actually wakes the blocking `for line in proc.stdout` below.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        timed_out = threading.Event()

        def _kill_on_timeout():
            timed_out.set()
            _kill_group()

        watchdog = threading.Timer(_STREAM_TIMEOUT, _kill_on_timeout)
        watchdog.start()
        try:
            for line in proc.stdout:
                yield line
            # Must wait() before reading returncode: the read loop ending only means
            # the pipe closed, not that the process has been reaped yet. Checking
            # returncode before wait() intermittently reads None on a successful run.
            proc.wait()
            if timed_out.is_set():
                raise ClaudeError(f"claude stream timed out after {_STREAM_TIMEOUT}s")
            if proc.returncode != 0:
                tmpfile.seek(0)
                err = tmpfile.read() or ""
                reason = _auth_failure_reason("", err, scan_text=True)
                if reason:
                    raise ClaudeAuthError(reason)
                raise ClaudeError(f"claude stream exited {proc.returncode}: {err[:500]}")
        finally:
            # Runs on normal exit, on error, AND on GeneratorExit (consumer abandoned
            # the stream, e.g. browser disconnect) — never leave an orphan claude -p,
            # or an orphan grandchild the wrapper spawned.
            watchdog.cancel()
            if proc.poll() is None:
                _kill_group()
            proc.wait()


def extract_json(text):
    fenced = extract_fenced_json(text, "json")
    if fenced is not None:
        return fenced
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except ValueError:
                    start = -1
    return None


def extract_fenced_json(text, label):
    fence = "```" + label
    i = text.find(fence)
    if i == -1:
        return None
    body_start = i + len(fence)
    j = text.find("```", body_start)
    if j == -1:
        return None
    try:
        return json.loads(text[body_start:j].strip())
    except ValueError:
        return None


def _result_text(stdout):
    try:
        return json.loads(stdout).get("result", "")
    except ValueError:
        return stdout  # tolerate a raw text result


def run_structured(prompt, *, model=DEFAULT_MODEL, validate=None, runner=_run_cli, tools=None):
    def args_for(p):
        args = ["-p", p]
        if tools:
            args += ["--allowedTools", *tools]  # variadic; terminated by the next --flag below
        args += ["--output-format", "json", "--model", model]
        return args
    for attempt in range(2):
        text = _result_text(runner(args_for(prompt)))
        obj = extract_json(text)
        if obj is not None and (validate is None or validate(obj)):
            return obj
        prompt = (
            prompt
            + "\n\nYour previous reply was not valid JSON matching the required shape. "
            "Reply again with ONLY the JSON object, no prose, no code fence."
        )
    raise ClaudeError("structured generation failed after retry")


def _extract_stream_text(line):
    try:
        ev = json.loads(line)
    except ValueError:
        return ""
    if ev.get("type") == "assistant":
        blocks = ev.get("message", {}).get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return ""


def stream(prompt, *, model=DEFAULT_MODEL, spawn=_spawn_cli, tools=None):
    args = ["-p", prompt]
    if tools:
        args += ["--allowedTools", *tools]  # variadic; terminated by the next --flag below
    args += ["--output-format", "stream-json", "--verbose", "--model", model]
    for line in spawn(args):
        try:
            ev = json.loads(line)
        except ValueError:
            ev = None
        if isinstance(ev, dict) and ev.get("api_error_status") in (401, 403):
            raise ClaudeAuthError(ev.get("result") or "Claude authentication failed.")
        text = _extract_stream_text(line)
        if text:
            yield text


def _collect_sources(obj, out, seen):
    """Recursively harvest every {title, url} pair (web-search results) from a parsed
    stream event. Broad on purpose — the caller filters to what the model actually cites,
    so over-capturing real URLs is harmless; under-capturing would drop valid citations."""
    if isinstance(obj, dict):
        u, t = obj.get("url"), obj.get("title")
        if (isinstance(u, str) and isinstance(t, str)
                and u.startswith(("http://", "https://")) and u not in seen):
            seen.add(u)
            out.append({"title": t, "url": u})
        for v in obj.values():
            _collect_sources(v, out, seen)
    elif isinstance(obj, list):
        for v in obj:
            _collect_sources(v, out, seen)


def run_sourced(prompt, *, model=DEFAULT_MODEL, validate=None, spawn=_spawn_cli):
    """Web-search-grounded structured generation. Runs the CLI with WebSearch/WebFetch
    and stream-json, returning (parsed_final_json, captured_sources) where captured_sources
    are the real {title, url} pairs retrieved from the actual search results."""
    args_for = lambda p: [
        "-p", p, "--allowedTools", "WebSearch", "WebFetch",
        "--output-format", "stream-json", "--verbose", "--model", model,
    ]
    for attempt in range(2):
        sources, seen, result_text = [], set(), ""
        for line in spawn(args_for(prompt)):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("api_error_status") in (401, 403):
                raise ClaudeAuthError(ev.get("result") or "Claude authentication failed.")
            _collect_sources(ev, sources, seen)
            if isinstance(ev, dict) and ev.get("type") == "result" and ev.get("result"):
                result_text = ev["result"]
        obj = extract_json(result_text)
        if obj is not None and (validate is None or validate(obj)):
            return obj, sources
        prompt = (
            prompt
            + "\n\nYour previous reply was not valid JSON matching the required shape. "
            "Reply again with ONLY the JSON object, no prose, no code fence."
        )
    raise ClaudeError("sourced generation failed after retry")


# Route handlers (and a couple of __main__ backfill scripts) need a plain
# (prompt, validate) callable to pass down into generation.py's ensure_*
# helpers — run_structured/run_sourced take `validate` keyword-only, so
# something has to adapt the positional pair. These replace what used to be
# 16 verbatim-duplicated `lambda prompt, validate: claude_client.run_x(prompt,
# validate=validate)` closures.
def structured_generate(prompt, validate):
    return run_structured(prompt, validate=validate)


def sourced_generate(prompt, validate):
    return run_sourced(prompt, validate=validate)
