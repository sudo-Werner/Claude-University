from backend import generation as gen


def test_detect_proposal_parses_course_fence():
    text = 'Sounds good!\n```course\n{"title": "Stats", "modules": []}\n```'
    p = gen.detect_proposal(text)
    assert p["title"] == "Stats"
    assert gen.detect_proposal("just chatting, no proposal yet") is None


def test_valid_lesson_requires_all_keys():
    good = {k: "x" for k in gen.LESSON_KEYS}
    assert gen.valid_lesson(good) is True
    missing = dict(good)
    del missing["promptHtml"]
    assert gen.valid_lesson(missing) is False
    assert gen.valid_lesson("not a dict") is False


def test_lesson_prompt_includes_context():
    prompt = gen.lesson_prompt(
        brief="Beginner, wants intuition.",
        profile={"analogies": True},
        lesson_id="stats-l1",
        lesson_title="Mean & median",
        module_title="Basics",
        position=1,
        total=8,
    )
    assert "Beginner, wants intuition." in prompt
    assert "Mean & median" in prompt
    assert "Basics" in prompt
    assert "stats-l1" in prompt
    assert "promptHtml" in prompt  # tells the model the required shape


def _events(sse_chunks):
    # parse "event: X\ndata: Y\n\n" chunks into (event, data) tuples
    out = []
    for chunk in sse_chunks:
        ev = data = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if ev:
            out.append((ev, data))
    return out


def test_chat_sse_streams_deltas_then_done():
    def fake_stream(prompt):
        yield "Hi! "
        yield "What do you want to learn?"
    chunks = list(gen.chat_sse([{"role": "user", "content": "hello"}], {}, stream_fn=fake_stream))
    evs = _events(chunks)
    assert ("delta", "Hi!") in evs
    assert evs[-1][0] == "done"


def test_chat_sse_emits_proposal_when_course_fence_present():
    def fake_stream(prompt):
        yield "Great, here is a plan.\n```course\n"
        yield '{"title": "Stats", "modules": []}\n```'
    chunks = list(gen.chat_sse([{"role": "user", "content": "stats"}], {}, stream_fn=fake_stream))
    evs = _events(chunks)
    proposal = [d for (e, d) in evs if e == "proposal"]
    assert proposal and '"title": "Stats"' in proposal[0]


def test_chat_sse_preserves_multiline_delta():
    def fake_stream(prompt):
        yield "Line one.\nLine two.\n```course\n{}"  # multi-line chunk with embedded newlines
    chunks = list(gen.chat_sse([{"role": "user", "content": "x"}], {}, stream_fn=fake_stream))
    # find the delta frame and reconstruct its data by joining all data: lines
    delta_frame = next(c for c in chunks if c.startswith("event: delta"))
    data = "\n".join(
        line[len("data:"):].lstrip(" ")
        for line in delta_frame.rstrip("\n").split("\n")
        if line.startswith("data:")
    )
    assert data == "Line one.\nLine two.\n```course\n{}"
