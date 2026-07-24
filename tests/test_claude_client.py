import json
import os
import time
import pytest
from backend import claude_client as cc


def test_extract_json_bare_and_fenced():
    assert cc.extract_json('noise {"a": 1} tail') == {"a": 1}
    assert cc.extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert cc.extract_json("no json here") is None


def test_extract_fenced_json_by_label():
    text = 'intro\n```course\n{"title": "X"}\n```\nouttro'
    assert cc.extract_fenced_json(text, "course") == {"title": "X"}
    assert cc.extract_fenced_json("nothing", "course") is None


def test_structured_generate_forwards_prompt_and_validate_as_keyword(monkeypatch):
    calls = []
    def fake_run_structured(prompt, validate=None):
        calls.append((prompt, validate))
        return {"ok": True}
    monkeypatch.setattr(cc, "run_structured", fake_run_structured)
    v = lambda o: True
    assert cc.structured_generate("hello", v) == {"ok": True}
    assert calls == [("hello", v)]


def test_sourced_generate_forwards_prompt_and_validate_as_keyword(monkeypatch):
    calls = []
    def fake_run_sourced(prompt, validate=None):
        calls.append((prompt, validate))
        return ({"ok": True}, [])
    monkeypatch.setattr(cc, "run_sourced", fake_run_sourced)
    v = lambda o: True
    assert cc.sourced_generate("hello", v) == ({"ok": True}, [])
    assert calls == [("hello", v)]


def test_run_structured_returns_parsed_json():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": 'Here: {"ok": true}'})
    out = cc.run_structured("make json", runner=runner)
    assert out == {"ok": True}
    assert len(calls) == 1


def test_run_structured_retries_once_then_succeeds():
    outputs = iter([
        json.dumps({"result": "sorry no json"}),
        json.dumps({"result": '{"ok": true}'}),
    ])
    out = cc.run_structured("make json", runner=lambda args: next(outputs))
    assert out == {"ok": True}


def test_run_structured_raises_after_second_failure():
    with pytest.raises(cc.ClaudeError):
        cc.run_structured("x", runner=lambda args: json.dumps({"result": "nope"}))


def test_run_structured_applies_validator():
    good = json.dumps({"result": '{"id": "a"}'})
    with pytest.raises(cc.ClaudeError):
        cc.run_structured("x", runner=lambda args: good, validate=lambda o: "missing" in o)


def test_run_structured_passes_tools_as_allowed_tools():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": '{"ok": true}'})
    out = cc.run_structured("x", runner=runner, tools=["Read"])
    assert out == {"ok": True}
    assert calls[0][:2] == ["-p", "x"]
    i = calls[0].index("--allowedTools")
    assert calls[0][i + 1] == "Read"
    assert "--output-format" in calls[0]


def test_run_structured_without_tools_omits_allowed_tools_flag():
    calls = []
    def runner(args):
        calls.append(args)
        return json.dumps({"result": '{"ok": true}'})
    cc.run_structured("x", runner=runner)
    assert "--allowedTools" not in calls[0]


def test_run_structured_retry_carries_same_tools():
    calls = []
    outputs = iter([
        json.dumps({"result": "sorry no json"}),
        json.dumps({"result": '{"ok": true}'}),
    ])
    def runner(args):
        calls.append(args)
        return next(outputs)
    cc.run_structured("x", runner=runner, tools=["Read"])
    assert len(calls) == 2
    for c in calls:
        assert "--allowedTools" in c
        assert c[c.index("--allowedTools") + 1] == "Read"


def test_env_strips_anthropic_credentials(monkeypatch):
    # The Task 0 spike proved a stale ANTHROPIC_API_KEY shadows the Max OAuth and 401s.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-bad")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-bad")
    env = cc._env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_stream_yields_text_deltas():
    # Fake CLI stream-json lines: assistant messages carry text in content blocks.
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hel"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "lo"}]}}),
        json.dumps({"type": "result", "result": "Hello"}),
    ]
    got = list(cc.stream("hi", spawn=lambda args: iter(lines)))
    assert "".join(got) == "Hello"


def test_auth_failure_reason_detects_401_envelope():
    envelope = json.dumps({"is_error": True, "api_error_status": 401,
                           "result": "Invalid API key · Fix external API key"})
    assert "Invalid API key" in cc._auth_failure_reason(envelope, "", scan_text=True)
    # structured field is trusted even without text scan (success-path call):
    assert cc._auth_failure_reason(envelope, "", scan_text=False)


def test_auth_failure_reason_text_markers_only_when_scanning():
    err = "stuff: please run /login to authenticate"
    assert cc._auth_failure_reason("", err, scan_text=True)
    # a SUCCESS lesson whose content mentions auth words must NOT be flagged:
    lesson = json.dumps({"api_error_status": None,
                         "result": "Lesson: to log in, type your 401 code"})
    assert cc._auth_failure_reason(lesson, "", scan_text=False) is None


def test_run_cli_raises_auth_error_on_401(monkeypatch):
    class P:
        returncode = 1
        stdout = json.dumps({"api_error_status": 401, "result": "Invalid API key"})
        stderr = ""
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(cc.ClaudeAuthError):
        cc._run_cli(["-p", "x"])


def test_run_cli_plain_error_on_nonauth_failure(monkeypatch):
    class P:
        returncode = 2
        stdout = ""
        stderr = "some other crash"
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(cc.ClaudeError) as ei:
        cc._run_cli(["-p", "x"])
    assert not isinstance(ei.value, cc.ClaudeAuthError)


def test_run_cli_success_passthrough(monkeypatch):
    class P:
        returncode = 0
        stdout = json.dumps({"api_error_status": None, "result": "ok"})
        stderr = ""
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: P())
    assert cc._run_cli(["-p", "x"]) == P.stdout


def test_stream_raises_auth_error_on_401_line():
    line = json.dumps({"type": "result", "api_error_status": 401, "result": "Invalid API key"})
    with pytest.raises(cc.ClaudeAuthError):
        list(cc.stream("hi", spawn=lambda args: iter([line])))


# ---- run_sourced: web-search generation that captures real {title,url} + final JSON ----

def _sourced_lines():
    return [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "server_tool_use", "name": "WebSearch", "input": {"query": "backprop"}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "title": "Stanford CS231n", "url": "https://cs231n.stanford.edu/"},
                {"type": "web_search_result", "title": "Deep Learning survey", "url": "https://arxiv.org/abs/1404.7828"}]}]}}),
        json.dumps({"type": "result",
                    "result": '{"sources":[{"title":"Deep Learning survey","url":"https://arxiv.org/abs/1404.7828","note":"n"}]}'}),
    ]


def test_run_sourced_captures_sources_and_parses_result():
    obj, sources = cc.run_sourced("p", spawn=lambda args: iter(_sourced_lines()))
    assert obj["sources"][0]["url"] == "https://arxiv.org/abs/1404.7828"
    urls = {s["url"] for s in sources}
    assert "https://cs231n.stanford.edu/" in urls
    assert "https://arxiv.org/abs/1404.7828" in urls
    assert all("title" in s and "url" in s for s in sources)


def test_run_sourced_enables_web_search_tools():
    seen = {}
    def spawn(args):
        seen["args"] = args
        return iter(_sourced_lines())
    cc.run_sourced("p", spawn=spawn)
    a = seen["args"]
    assert "--allowedTools" in a and "WebSearch" in a and "WebFetch" in a
    assert "stream-json" in a


def test_run_sourced_applies_validator_and_retries():
    attempts = iter([
        [json.dumps({"type": "result", "result": "no json"})],
        _sourced_lines(),
    ])
    def spawn(args):
        return iter(next(attempts))
    obj, sources = cc.run_sourced("p", validate=lambda o: "sources" in o, spawn=spawn)
    assert "sources" in obj


def test_run_sourced_raises_auth_error_on_401_line():
    line = json.dumps({"api_error_status": 401, "result": "Invalid API key"})
    with pytest.raises(cc.ClaudeAuthError):
        cc.run_sourced("p", spawn=lambda args: iter([line]))


def test_stream_enables_web_search_tools_when_requested():
    seen = {}
    def spawn(args):
        seen["args"] = args
        return iter([json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})])
    out = list(cc.stream("p", tools=["WebSearch", "WebFetch"], spawn=spawn))
    a = seen["args"]
    assert "--allowedTools" in a and "WebSearch" in a and "WebFetch" in a
    assert "stream-json" in a
    assert out == ["hi"]


def test_stream_without_tools_has_no_allowedtools():
    seen = {}
    def spawn(args):
        seen["args"] = args
        return iter([])
    list(cc.stream("p", spawn=spawn))
    assert "--allowedTools" not in seen["args"]


def test_spawn_cli_times_out_and_kills(monkeypatch, tmp_path):
    script = tmp_path / "fake-claude"
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    monkeypatch.setattr(cc, "CLAUDE_BIN", str(script))
    monkeypatch.setattr(cc, "_STREAM_TIMEOUT", 1)
    start = time.monotonic()
    with pytest.raises(cc.ClaudeError, match="timed out"):
        list(cc._spawn_cli(["-p", "x"]))
    assert time.monotonic() - start < 10  # killed, not waited out


def test_spawn_cli_kills_process_when_generator_abandoned(monkeypatch, tmp_path):
    # The direct child forks a grandchild (`sleep 30 &`) and records its PID, then
    # `wait`s on it — mirroring a real wrapper script. proc.kill() only kills the
    # direct child and would leave this grandchild (and its open pipe fd) alive;
    # this test proves the whole process TREE dies, not just the shell leader.
    pidfile = tmp_path / "pid"
    script = tmp_path / "fake-claude"
    script.write_text(f"#!/bin/sh\necho line1\nsleep 30 &\necho $! > {pidfile}\nwait\n")
    script.chmod(0o755)
    monkeypatch.setattr(cc, "CLAUDE_BIN", str(script))
    gen = cc._spawn_cli(["-p", "x"])
    assert next(gen) == "line1\n"
    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.1)
    else:
        pytest.fail("grandchild never recorded its PID")
    pid = int(pidfile.read_text().strip())
    gen.close()  # simulates the SSE consumer disconnecting
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("grandchild process still alive after generator close (process tree not killed)")


def test_spawn_cli_delivers_bursted_lines_without_returncode_race(monkeypatch, tmp_path):
    # Two things under test at once, both from the review findings:
    # 1. A burst of lines written in one shot (before the read loop gets scheduled
    #    again) must all be delivered in order, not just the first one.
    # 2. proc.returncode must never be read before proc.wait() — this raced ~20% of
    #    the time in the select()-based implementation, so loop to catch it.
    script = tmp_path / "fake-claude"
    script.write_text("#!/bin/sh\nprintf 'a\\nb\\nc\\n'\nsleep 0.05\nprintf 'd\\n'\n")
    script.chmod(0o755)
    monkeypatch.setattr(cc, "CLAUDE_BIN", str(script))
    for _ in range(10):
        assert list(cc._spawn_cli(["-p", "x"])) == ["a\n", "b\n", "c\n", "d\n"]


def test_spawn_cli_raises_auth_error_on_stdout_marker(monkeypatch, tmp_path):
    # The marker is printed to stdout (not stderr) and the process exits non-zero —
    # this used to raise a generic ClaudeError because the exit-code check only
    # scanned stderr, losing an auth failure the CLI reported on stdout.
    script = tmp_path / "fake-claude"
    script.write_text("#!/bin/sh\necho 'not logged in'\nexit 1\n")
    script.chmod(0o755)
    monkeypatch.setattr(cc, "CLAUDE_BIN", str(script))
    with pytest.raises(cc.ClaudeAuthError):
        list(cc._spawn_cli(["-p", "x"]))


# ---- progress_events: stream-json -> user-facing feed lines ----

def _assistant(blocks):
    return {"type": "assistant", "message": {"content": blocks}}


def test_progress_events_translates_web_search():
    ev = _assistant([{"type": "tool_use", "name": "WebSearch", "input": {"query": "hormone signaling speed"}}])
    assert cc.progress_events(ev) == [{"kind": "search", "text": "Searching: hormone signaling speed"}]


def test_progress_events_translates_web_fetch_to_host():
    ev = _assistant([{"type": "tool_use", "name": "WebFetch", "input": {"url": "https://www.khanacademy.org/science/x1"}}])
    assert cc.progress_events(ev) == [{"kind": "read", "text": "Reading: www.khanacademy.org"}]


def test_progress_events_passes_narration_and_thinking():
    ev = _assistant([
        {"type": "thinking", "thinking": "The learner knows neurons already."},
        {"type": "text", "text": "Let me check the hormone half-life numbers."},
    ])
    assert cc.progress_events(ev) == [
        {"kind": "think", "text": "The learner knows neurons already."},
        {"kind": "say", "text": "Let me check the hormone half-life numbers."},
    ]


def test_progress_events_drops_json_payload_and_noise():
    assert cc.progress_events(_assistant([{"type": "text", "text": '{"id": "l4"}'}])) == []
    assert cc.progress_events(_assistant([{"type": "text", "text": "```json\n{}\n```"}])) == []
    assert cc.progress_events(_assistant([{"type": "text", "text": "   "}])) == []
    assert cc.progress_events({"type": "result", "result": "{}"}) == []
    assert cc.progress_events("not a dict") == []


def test_progress_events_clips_long_text():
    ev = _assistant([{"type": "text", "text": "x" * 500}])
    (line,) = cc.progress_events(ev)
    assert len(line["text"]) <= 200
    assert line["text"].endswith("…")


def test_progress_events_tolerates_malformed_stream_events():
    # A malformed-but-plausible event must never raise — it must yield fewer/no
    # lines instead. These four shapes are the exact ones that raised in the
    # reviewed finding (AttributeError, TypeError, AttributeError, AttributeError
    # inside urlparse respectively).
    assert cc.progress_events({"type": "assistant", "message": None}) == []
    assert cc.progress_events({"type": "assistant", "message": {"content": None}}) == []
    assert cc.progress_events({"type": "assistant", "message": {"content": ["not-a-dict"]}}) == []
    assert cc.progress_events(_assistant([
        {"type": "tool_use", "name": "WebFetch", "input": {"url": 123}},
    ])) == []


def test_progress_events_skips_malformed_block_keeps_valid_sibling():
    # One malformed block alongside one valid text block: only the valid line
    # comes back — a translator drops what it can't understand, it doesn't abort.
    ev = _assistant([
        "not-a-dict",
        {"type": "text", "text": "Let me check the hormone half-life numbers."},
    ])
    assert cc.progress_events(ev) == [
        {"kind": "say", "text": "Let me check the hormone half-life numbers."},
    ]


# ---- run_sourced: on_event forwarding and timeout plumbing ----

def test_run_sourced_forwards_parsed_events():
    seen = []
    cc.run_sourced("p", spawn=lambda args: iter(_sourced_lines()), on_event=seen.append)
    assert len(seen) == len([l for l in _sourced_lines()])
    assert all(isinstance(e, dict) for e in seen)


def test_run_sourced_default_spawn_carries_timeout(monkeypatch):
    captured = {}

    def fake_spawn_cli(args, timeout=None):
        captured["timeout"] = timeout
        line = '{"type": "result", "result": "{\\"ok\\": true}"}'
        return iter([line])

    monkeypatch.setattr(cc, "_spawn_cli", fake_spawn_cli)
    obj, sources = cc.run_sourced("p", timeout=1200)
    assert obj == {"ok": True}
    assert captured["timeout"] == 1200
