import json
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
