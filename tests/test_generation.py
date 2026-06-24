from backend import generation as gen

_OK_CHECK = {"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}


def test_sanitize_html_allows_safe_block_tags():
    # Block tags the generator actually emits should render, not show as literal text.
    src = (
        "<h1>Title</h1><h2>Sub</h2><h3>Smaller</h3>"
        "<p>A paragraph with <strong>bold</strong> and <code>code</code>.</p>"
        "<pre><code>print(1)</code></pre>"
        "<ul><li>one</li><li>two</li></ul>"
        "<ol><li>first</li></ol>"
    )
    out = gen.sanitize_html(src)
    for tag in ("<h1>", "</h1>", "<h2>", "<h3>", "<p>", "</p>",
                "<pre>", "</pre>", "<ul>", "<ol>", "<li>", "</li>"):
        assert tag in out, tag
    assert "<strong>bold</strong>" in out
    assert "<code>print(1)</code>" in out


def test_sanitize_html_still_blocks_dangerous_markup():
    # Default-deny holds: scripts, images, event handlers, and tags with
    # attributes stay escaped and inert.
    out = gen.sanitize_html(
        '<script>alert(1)</script><img src=x onerror=alert(1)>'
        '<p onclick="x()">hi</p><h2 style="x">t</h2><a href="x">link</a>'
    )
    assert "<script" not in out
    assert "<img" not in out
    assert "&lt;img" in out  # img escaped, its onerror handler inert as text
    assert "<p onclick" not in out  # attribute-bearing <p ...> not restored as live tag
    assert "<h2 style" not in out
    assert "<a" not in out
    assert "&lt;script&gt;" in out
    # A bare <p> is restored, but <p onclick=...> (with attributes) is NOT —
    # only the exact attribute-less open tag string is in the allowlist.
    assert "<p>" not in out


def test_sanitize_html_does_not_double_escape_entities():
    # The generator writes HTML, so it escapes its own code: `<` -> `&lt;`.
    # We must NOT re-escape that into `&amp;lt;` (which renders as literal "&lt;").
    src = "<code>if diameter &lt; 9.80 mm or diameter &gt; 10.20 mm</code>"
    out = gen.sanitize_html(src)
    assert "&amp;lt;" not in out   # not double-escaped
    assert "&amp;gt;" not in out
    assert "&lt;" in out           # renders in the browser as a literal "<"
    assert "&gt;" in out
    assert "<code>" in out and "</code>" in out


def test_sanitize_html_entity_restore_stays_inert():
    # Even if the model escapes a whole tag as entities, restoring the single
    # entity keeps it inert text (it renders as "<script>", not a live element).
    out = gen.sanitize_html("&lt;script&gt;alert(1)&lt;/script&gt;")
    assert "<script" not in out          # never a live tag
    assert "&lt;script&gt;" in out       # shown as text
    assert "&amp;lt;" not in out         # but not double-escaped


def test_detect_proposal_parses_course_fence():
    text = 'Sounds good!\n```course\n{"title": "Stats", "modules": []}\n```'
    p = gen.detect_proposal(text)
    assert p["title"] == "Stats"
    assert gen.detect_proposal("just chatting, no proposal yet") is None


def test_valid_lesson_requires_all_keys():
    good = {k: "x" for k in gen.LESSON_KEYS}
    good["checks"] = [dict(_OK_CHECK)]
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


import json as _json
import pytest
from backend import claude_client


def _course(tmp_path):
    from backend import courses
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(_json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "beginner friendly",
        "modules": [{"id": "m1", "title": "Basics",
                     "lessons": [{"id": "demo-l1", "title": "First"}]}],
    }))
    return root


def test_ensure_lesson_generates_validates_and_caches(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return made
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=generate)
    assert out["id"] == "demo-l1"
    assert "beginner friendly" in calls[0]  # brief fed into the prompt
    # cached: file now exists and a second call does not regenerate
    assert (root / "demo" / "lessons" / "demo-l1.json").exists()
    out2 = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: (_ for _ in ()).throw(AssertionError("regenerated")))
    assert out2["id"] == "demo-l1"


def test_ensure_lesson_unknown_id_returns_none(tmp_path):
    root = _course(tmp_path)
    assert gen.ensure_lesson(root, "demo", "demo-l9", {}, generate=lambda p: {}) is None


def test_ensure_lesson_invalid_generation_raises_and_writes_nothing(tmp_path):
    root = _course(tmp_path)
    with pytest.raises(claude_client.ClaudeError):
        gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: {"bad": 1})
    assert not (root / "demo" / "lessons" / "demo-l1.json").exists()


def test_ensure_lesson_sanitizes_unsafe_html(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["promptHtml"] = '<code>w</code><img src=x onerror=alert(1)>'
    made["checks"] = [dict(_OK_CHECK)]
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made))
    assert "<img" not in out["promptHtml"]
    assert "&lt;img" in out["promptHtml"]
    assert "<code>w</code>" in out["promptHtml"]


def test_ensure_lesson_reconciles_ids_and_step(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "wrong"
    made["courseId"] = "wrong"
    made["step"] = 99
    made["totalSteps"] = 99
    made["checks"] = [dict(_OK_CHECK)]
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(made))
    assert out["id"] == "demo-l1"
    assert out["courseId"] == "demo"
    assert out["step"] == 1
    assert out["totalSteps"] == 1


def test_chat_sse_emits_error_on_claude_failure():
    def failing_stream(prompt):
        raise claude_client.ClaudeError("connection refused")
        yield  # make it a generator
    chunks = list(gen.chat_sse([{"role": "user", "content": "hello"}], {}, stream_fn=failing_stream))
    evs = _events(chunks)
    event_names = [e for (e, _) in evs]
    assert "error" in event_names
    assert "done" not in event_names


def test_valid_check_accepts_mcq_and_fill():
    assert gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", "b"], "answer": 1, "explanation": "e"})
    assert gen.valid_check({"type": "fill", "prompt": "p", "answer": "4", "explanation": "e"})


def test_valid_check_rejects_malformed():
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", "b"], "answer": 5, "explanation": "e"})  # index out of range
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a"], "answer": 0, "explanation": "e"})  # <2 choices
    assert not gen.valid_check({"type": "fill", "prompt": "p", "explanation": "e"})  # no answer
    assert not gen.valid_check({"type": "other", "prompt": "p"})
    assert not gen.valid_check("nope")


def test_valid_lesson_requires_checks():
    base = {k: "x" for k in gen.LESSON_KEYS}
    assert not gen.valid_lesson(base)  # no checks
    base["checks"] = []
    assert not gen.valid_lesson(base)  # empty
    base["checks"] = [{"type": "fill", "prompt": "p", "answer": "a", "explanation": "e"}]
    assert gen.valid_lesson(base)
    base["checks"] = [base["checks"][0]] * 4
    assert not gen.valid_lesson(base)  # too many


def test_lesson_prompt_mentions_checks():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    assert "checks" in p
    assert "mcq" in p and "fill" in p


def test_ensure_lesson_sanitizes_check_html(tmp_path):
    import json as _json
    from backend import courses
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(_json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "beginner",
        "modules": [{"id": "m1", "title": "M", "lessons": [{"id": "demo-l1", "title": "L1"}]}],
    }))
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [{"type": "mcq", "prompt": "<img src=x onerror=alert(1)>pick", "choices": ["<b>a</b>", "ok"],
                        "answer": 1, "explanation": "<code>fine</code>"}]
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: made)
    chk = out["checks"][0]
    assert "<img" not in chk["prompt"] and "&lt;img" in chk["prompt"]   # unsafe escaped
    assert "<code>fine</code>" in chk["explanation"]                     # allowlisted kept
    assert "<b>a</b>" not in chk["choices"][0] and "&lt;b&gt;a" in chk["choices"][0]


def test_lesson_prompt_includes_performance_when_given():
    p = gen.lesson_prompt(
        brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
        module_title="M", position=2, total=3,
        performance="The learner is performing strongly — go deeper.",
    )
    assert "Learner performance so far:" in p
    assert "performing strongly" in p


def test_lesson_prompt_omits_performance_when_empty():
    p = gen.lesson_prompt(
        brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
        module_title="M", position=1, total=1,
    )
    assert "Learner performance so far:" not in p


def test_ensure_lesson_forwards_performance(tmp_path):
    root = _course(tmp_path)
    captured = {}
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["checks"] = [dict(_OK_CHECK)]

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return dict(made)

    gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=fake_generate,
                      performance="The learner has been struggling — slow down.")
    assert "Learner performance so far:" in captured["prompt"]
    assert "struggling" in captured["prompt"]


def test_valid_check_rejects_empty_fields():
    assert not gen.valid_check({"type": "mcq", "prompt": "  ", "choices": ["a", "b"], "answer": 0, "explanation": "e"})
    assert not gen.valid_check({"type": "mcq", "prompt": "p", "choices": ["a", ""], "answer": 0, "explanation": "e"})
    assert not gen.valid_check({"type": "fill", "prompt": "p", "answer": "  ", "explanation": "e"})
    assert gen.valid_check({"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"})


def test_valid_lesson_rejects_empty_prose():
    good = {k: "x" for k in gen.LESSON_KEYS}
    good["checks"] = [dict(_OK_CHECK)]
    assert gen.valid_lesson(good) is True
    blank = dict(good); blank["promptHtml"] = "   "
    assert gen.valid_lesson(blank) is False
    blank2 = dict(good); blank2["solutionAns"] = ""
    assert gen.valid_lesson(blank2) is False


def test_sanitize_html_allows_hr():
    out = gen.sanitize_html("<p>a</p><hr><p>b</p><hr/>")
    assert "<hr>" in out
    assert out.count("<hr>") == 2  # both <hr> and <hr/> normalize to <hr>


def test_chat_sse_emits_reauth_on_auth_error():
    def failing_stream(prompt):
        raise claude_client.ClaudeAuthError("Invalid API key")
        yield
    chunks = list(gen.chat_sse([{"role": "user", "content": "hi"}], {}, stream_fn=failing_stream))
    evs = _events(chunks)
    msg = [d for (e, d) in evs if e == "error"]
    assert msg and ("re-authenticate" in msg[0].lower() or "log in" in msg[0].lower())


# ---- #4 answer grading ----

def test_valid_grade_accepts_known_verdicts():
    for v in ("correct", "close", "incorrect"):
        assert gen.valid_grade({"verdict": v, "note": "good effort"}) is True


def test_valid_grade_rejects_bad_shape():
    assert gen.valid_grade({"verdict": "maybe", "note": "x"}) is False
    assert gen.valid_grade({"verdict": "correct", "note": "  "}) is False
    assert gen.valid_grade({"note": "no verdict"}) is False
    assert gen.valid_grade("nope") is False


def test_grade_prompt_includes_answer_and_reference():
    p = gen.grade_prompt(prompt_html="<p>What is 2+2?</p>", solution_ans="4",
                         solution_note="addition", answer="four-ish")
    assert "What is 2+2?" in p
    assert "4" in p
    assert "four-ish" in p
    assert "JSON" in p


def test_grade_answer_returns_verdict_and_sanitizes_note(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
                                "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    lesson = {"id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
              "eyebrow": "EXERCISE", "promptHtml": "<p>q</p>", "hintHtml": "h",
              "solutionAns": "a", "solutionNote": "n", "checks": [dict(_OK_CHECK)]}
    (root / cid / "lessons" / f"{lid}.json").write_text(_json.dumps(lesson))

    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"verdict": "close", "note": "Nice <script>alert(1)</script> try"}

    result = gen.grade_answer(root, cid, lid, "my answer", generate=fake_generate)
    assert result["verdict"] == "close"
    assert "<script" not in result["note"]
    assert "my answer" in captured["prompt"]


def test_grade_answer_missing_lesson_returns_none(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
                                "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]
    assert gen.grade_answer(root, cid, "no-such-lesson", "x", generate=lambda p: {}) is None


# ---- #5 per-lesson depth adaptation ----

def test_lesson_prompt_includes_directive_when_given():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="c-l1", lesson_title="L",
                          module_title="M", position=1, total=3, directive="GO DEEPER PLEASE")
    assert "GO DEEPER PLEASE" in p
    p2 = gen.lesson_prompt(brief="b", profile={}, lesson_id="c-l1", lesson_title="L",
                           module_title="M", position=1, total=3)
    assert "GO DEEPER" not in p2


def test_deepen_lesson_regenerates_and_overwrites(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
                                "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]; lid = manifest["modules"][0]["lessons"][0]["id"]
    original = {"id": lid, "courseId": cid, "topic": "t", "step": 1, "totalSteps": 1,
               "eyebrow": "EXERCISE", "promptHtml": "<p>shallow</p>", "hintHtml": "h",
               "solutionAns": "a", "solutionNote": "n", "checks": [dict(_OK_CHECK)]}
    path = root / cid / "lessons" / f"{lid}.json"
    path.write_text(_json.dumps(original))

    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"id": "wrong", "courseId": "wrong", "topic": "deeper", "step": 9, "totalSteps": 9,
                "eyebrow": "EXERCISE", "promptHtml": "<p>now with fundamentals</p>",
                "hintHtml": "h2", "solutionAns": "a2", "solutionNote": "n2", "checks": [dict(_OK_CHECK)]}

    lesson = gen.deepen_lesson(root, cid, lid, {}, generate=fake_generate)
    assert "rusty" in captured["prompt"].lower() or "fundamentals" in captured["prompt"].lower()
    assert lesson["promptHtml"] == "<p>now with fundamentals</p>"
    assert lesson["id"] == lid and lesson["courseId"] == cid  # reconciled to authoritative
    assert lesson["step"] == 1 and lesson["totalSteps"] == 1
    # file overwritten with the deeper version
    on_disk = _json.loads(path.read_text())
    assert on_disk["promptHtml"] == "<p>now with fundamentals</p>"


def test_deepen_lesson_unknown_lesson_returns_none(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
                                "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]
    assert gen.deepen_lesson(root, cid, "no-such-lesson", {}, generate=lambda p: {}) is None


# ---- #1 real-world evidence capstone ----

_OK_ITEM = {"title": "AlphaFold", "detail": "It predicts protein structures.", "source": "DeepMind"}


def test_valid_capstone_accepts_well_formed():
    assert gen.valid_capstone({"intro": "Here is where this shows up.",
                               "items": [dict(_OK_ITEM), dict(_OK_ITEM)]}) is True


def test_valid_capstone_rejects_bad_shape():
    assert gen.valid_capstone({"items": [dict(_OK_ITEM), dict(_OK_ITEM)]}) is False  # no intro
    assert gen.valid_capstone({"intro": "x", "items": [dict(_OK_ITEM)]}) is False     # too few items
    assert gen.valid_capstone({"intro": "x", "items": [{"title": "", "detail": "d"}, dict(_OK_ITEM)]}) is False
    assert gen.valid_capstone({"intro": "x", "items": [{"title": "t"}, dict(_OK_ITEM)]}) is False  # no detail
    assert gen.valid_capstone({"intro": "x", "items": [{"title": "t", "detail": "d"}, dict(_OK_ITEM)]}) is False  # no source
    assert gen.valid_capstone("nope") is False


def test_capstone_prompt_includes_scope_and_concepts():
    p = gen.capstone_prompt(scope_label="the module", scope_title="Neural Nets",
                            concept_titles=["Backprop", "Gradients"], brief="ML course", profile={})
    assert "Neural Nets" in p
    assert "Backprop" in p and "Gradients" in p
    assert "JSON" in p


def test_ensure_capstone_module_scope_generates_caches_sanitizes(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
        "modules": [{"title": "Mod A", "lessons": [{"title": "L1"}, {"title": "L2"}]}]})
    cid = manifest["id"]; mid = manifest["modules"][0]["id"]
    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"intro": "Real world!", "items": [
            {"title": "Sys <script>x</script>", "detail": "Used in <em>industry</em>.", "source": "Wikipedia"},
            dict(_OK_ITEM)]}
    cap = gen.ensure_capstone(root, cid, mid, {}, generate=fake_generate)
    assert cap["scope"] == mid and cap["title"] == "Mod A"
    assert "L1" in captured["prompt"] and "L2" in captured["prompt"]
    assert "<script" not in cap["items"][0]["title"]          # title escaped
    assert "<em>industry</em>" in cap["items"][0]["detail"]   # safe inline tag kept
    # cached: second call does not regenerate
    cap2 = gen.ensure_capstone(root, cid, mid, {}, generate=lambda p: (_ for _ in ()).throw(AssertionError("regenerated")))
    assert cap2["scope"] == mid


def test_ensure_capstone_course_scope_uses_module_titles(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "Whole Course", "subtitle": "s", "brief": "b",
        "modules": [{"title": "Alpha", "lessons": [{"title": "L1"}]},
                    {"title": "Beta", "lessons": [{"title": "L2"}]}]})
    cid = manifest["id"]
    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"intro": "i", "items": [dict(_OK_ITEM), dict(_OK_ITEM)]}
    cap = gen.ensure_capstone(root, cid, "course", {}, generate=fake_generate)
    assert cap["scope"] == "course" and cap["title"] == "Whole Course"
    assert "Alpha" in captured["prompt"] and "Beta" in captured["prompt"]


def test_ensure_capstone_unknown_module_returns_none(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]
    assert gen.ensure_capstone(root, cid, "m99", {}, generate=lambda p: {}) is None


# ---- #3 Slice A: readability/engagement style guidance in the default prompt ----

def test_lesson_prompt_has_readability_style_guidance():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="c-l1", lesson_title="L",
                          module_title="M", position=1, total=3)
    low = p.lower()
    assert "worked example" in low          # solutionNote as a worked example
    assert "encouraging" in low             # warm, specific check feedback
    assert "<strong>" in p                  # bold the key term (chunking/scannability)
    assert "short" in low                   # short paragraphs/sentences
