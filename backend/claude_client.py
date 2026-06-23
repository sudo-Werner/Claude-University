import json
import os
import subprocess

DEFAULT_MODEL = "claude-sonnet-4-6"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/werner/.local/bin/claude")
_TIMEOUT = 120


class ClaudeError(Exception):
    pass


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
        raise ClaudeError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


def _spawn_cli(args):
    proc = subprocess.Popen(
        [CLAUDE_BIN, *args], stdout=subprocess.PIPE, text=True, env=_env()
    )
    for line in proc.stdout:
        yield line


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


def run_structured(prompt, *, model=DEFAULT_MODEL, validate=None, runner=_run_cli):
    args_for = lambda p: ["-p", p, "--output-format", "json", "--model", model]
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


def stream(prompt, *, model=DEFAULT_MODEL, spawn=_spawn_cli):
    args = ["-p", prompt, "--output-format", "stream-json", "--verbose", "--model", model]
    for line in spawn(args):
        text = _extract_stream_text(line)
        if text:
            yield text
