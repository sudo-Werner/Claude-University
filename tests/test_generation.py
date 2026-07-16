from backend import generation as gen
from backend import generation

_OK_CHECK = {"type": "fill", "prompt": "p", "answer": "x", "explanation": "e"}
_OK_PREQUIZ = {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"], "answer": 0, "explanation": "Because."}


def _ok_spine():
    return {"summary": "Teaches what recursion is.",
            "concepts": [{"term": "recursion",
                          "definition": "A function calling itself on a smaller input."}]}


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


def test_sanitize_html_allows_table_family():
    src = ("<table><thead><tr><th>Approach</th><th>Knowledge</th></tr></thead>"
           "<tbody><tr><td>Rules</td><td>hand-written</td></tr></tbody></table>")
    out = gen.sanitize_html(src)
    for tag in ("<table>", "</table>", "<thead>", "<tbody>", "<tr>", "</tr>",
                "<th>", "</th>", "<td>", "</td>"):
        assert tag in out, tag


def test_sanitize_html_allows_callout_and_box_divs():
    out = gen.sanitize_html('<div class="callout"><strong>Key</strong> idea</div>'
                            '<div class="box">framed</div>')
    assert '<div class="callout">' in out
    assert '<div class="box">' in out
    assert "</div>" in out
    assert "<strong>Key</strong>" in out


def test_sanitize_html_blocks_unlisted_div_classes_and_attributes():
    # Default-deny holds for the new tags: arbitrary classes, attribute-bearing
    # divs, and attribute-bearing table cells stay escaped/inert.
    out = gen.sanitize_html(
        '<div class="evil">x</div>'
        '<div onclick="x()" class="callout">y</div>'
        '<div class="callout" onmouseover="x">z</div>'
        '<td onclick="x()">c</td>'
        '<table onload="x">t</table>'
    )
    assert '<div class="evil"' not in out      # unlisted class not restored
    assert "<div onclick" not in out            # attribute-bearing div stays escaped
    assert '<div class="callout" onmouseover' not in out
    assert "<td onclick" not in out
    assert "<table onload" not in out
    # the escaped forms are present as inert text (proof they were NOT restored)
    assert "&lt;div class=&quot;evil&quot;&gt;" in out


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


def test_sanitize_html_restores_typographic_entities():
    # The reported bug: the model writes smart quotes / dashes as named entities;
    # they were double-escaped to "&amp;ldquo;" and shown as literal "&ldquo;".
    src = "&ldquo;Artificial Intelligence&rdquo; is broad&mdash;really broad&hellip;"
    out = gen.sanitize_html(src)
    assert "&amp;ldquo;" not in out and "&amp;rdquo;" not in out
    assert "&amp;mdash;" not in out and "&amp;hellip;" not in out
    assert "&ldquo;" in out and "&rdquo;" in out
    assert "&mdash;" in out and "&hellip;" in out


def test_sanitize_html_restores_numeric_entities():
    out = gen.sanitize_html("&#8220;quoted&#8221; and &#x201C;hex&#x201D;")
    assert "&amp;#8220;" not in out and "&amp;#x201C;" not in out
    assert "&#8220;" in out and "&#x201C;" in out


def test_sanitize_html_keeps_literal_ampersand_escaped():
    # A real, standalone ampersand (not part of an entity) must stay &amp; so it
    # renders as "&" — only "&amp;NAME;" gets un-doubled.
    out = gen.sanitize_html("Salt & pepper, R&D, AT&T")
    assert "Salt &amp; pepper" in out
    assert "R&amp;D" in out and "AT&amp;T" in out


def test_sanitize_html_entity_restore_stays_inert():
    # Even if the model escapes a whole tag as entities, restoring the single
    # entity keeps it inert text (it renders as "<script>", not a live element).
    out = gen.sanitize_html("&lt;script&gt;alert(1)&lt;/script&gt;")
    assert "<script" not in out          # never a live tag
    assert "&lt;script&gt;" in out       # shown as text
    assert "&amp;lt;" not in out         # but not double-escaped


def test_valid_lesson_requires_all_keys():
    good = {k: "x" for k in gen.LESSON_KEYS}
    good["checks"] = [dict(_OK_CHECK)]
    good["preQuiz"] = dict(_OK_PREQUIZ)
    good["spine"] = _ok_spine()
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


def test_chat_sse_emits_brief_when_learner_brief_fence_present():
    # chat_sse now emits a `brief` event (intake interview), not a `proposal` event.
    def fake_stream(prompt):
        yield 'Great, here is your brief.\n```learnerBrief\n'
        yield '{"goal":"learn Stats","background":"none","priorKnowledge":[],"motivation":"career","desiredDepth":"deep"}\n```'
    chunks = list(gen.chat_sse([{"role": "user", "content": "stats"}], {}, stream_fn=fake_stream))
    evs = _events(chunks)
    brief = [d for (e, d) in evs if e == "brief"]
    assert brief and '"goal": "learn Stats"' in brief[0]
    assert not any(e == "proposal" for (e, _) in evs)


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
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
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
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
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
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
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
    base["preQuiz"] = dict(_OK_PREQUIZ)
    base["spine"] = _ok_spine()
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
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
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
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()

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
    good["preQuiz"] = dict(_OK_PREQUIZ)
    good["spine"] = _ok_spine()
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
                "hintHtml": "h2", "solutionAns": "a2", "solutionNote": "n2", "checks": [dict(_OK_CHECK)],
                "preQuiz": dict(_OK_PREQUIZ), "spine": _ok_spine()}

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


def test_capstone_prompt_demands_certainty():
    p = gen.capstone_prompt(scope_label="the module", scope_title="Neural Nets",
                            concept_titles=["Backprop"], brief="ML course", profile={})
    assert "widely documented you are certain they exist" in p
    assert "choose a more famous one instead" in p


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


def test_lesson_prompt_has_visual_aid_guidance():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="c-l1", lesson_title="L",
                          module_title="M", position=1, total=3)
    low = p.lower()
    assert "<table>" in p                       # comparison tables offered
    assert 'class="callout"' in p               # the exact callout container
    assert "decorative" in low                  # anti-decoration guardrail
    assert "<pre>" in p                         # diagrams in pre


# ---- accredited sources / course Library (Phase 1) ----

def test_source_type_from_domain():
    assert gen.source_type("https://cs231n.stanford.edu/slides/lecture_4.pdf") == "university"
    assert gen.source_type("https://www.cl.cam.ac.uk/teaching/x") == "university"
    assert gen.source_type("https://arxiv.org/abs/1404.7828") == "preprint"           # not peer-reviewed
    assert gen.source_type("https://www.biorxiv.org/content/x") == "preprint"
    assert gen.source_type("https://doi.org/10.1000/xyz123") == "preprint"            # resolves anything
    assert gen.source_type("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4863083/") == "preprint"
    assert gen.source_type("https://nature.com/articles/x") == "peer-reviewed"        # genuine journal venue
    assert gen.source_type("https://www.sciencedirect.com/science/article/x") == "peer-reviewed"
    assert gen.source_type("https://link.springer.com/content/pdf/x.pdf") == "textbook"
    assert gen.source_type("https://pytorch.org/docs/stable/notes/autograd.html") == "official-docs"
    assert gen.source_type("https://docs.python.org/3/library/x.html") == "official-docs"
    assert gen.source_type("https://docs.foo.com/getting-started") == "official-docs"  # first-label rule
    assert gen.source_type("https://someblog.example.com/post") == "reference"


def test_source_type_matches_host_labels_not_raw_substrings():
    # The must-fix bug: substring matching let "summit.org" pass as a university because
    # it contains "mit." — label-boundary matching must reject it.
    assert gen.source_type("https://summit.org/conference") != "university"
    assert gen.source_type("https://summit.org/conference") == "reference"
    assert gen.source_type("https://mit.edu/about") == "university"
    assert gen.source_type("https://web.mit.edu/some/path") == "university"


def test_valid_bibliography_shape():
    ok = {"sources": [
        {"title": "A", "url": "https://arxiv.org/abs/1", "note": "n"},
        {"title": "B", "url": "https://mit.edu/x", "note": "n"},
        {"title": "C", "url": "https://pytorch.org/docs", "note": "n"}]}
    assert gen.valid_bibliography(ok) is True
    assert gen.valid_bibliography({"sources": [{"title": "A", "url": "https://x", "note": "n"}] * 1}) is False  # too few
    assert gen.valid_bibliography({"sources": [{"title": "", "url": "https://a", "note": "n"}] * 3}) is False
    assert gen.valid_bibliography({"sources": [{"title": "A", "url": "ftp://a", "note": "n"}] * 3}) is False  # not http(s)
    assert gen.valid_bibliography("nope") is False


def test_bibliography_prompt_asks_for_accredited_web_sources():
    p = gen.bibliography_prompt(title="Intro ML", brief="beginner", module_titles=["Basics", "Neural nets"])
    low = p.lower()
    assert "intro ml" in low
    assert "web search" in low or "search the web" in low
    assert "accredited" in low or "authoritative" in low
    assert "Basics" in p


def test_ensure_bibliography_filters_to_really_retrieved_urls(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]
    # captured = what search really returned; the model also cites a URL NOT retrieved -> dropped
    captured = [
        {"title": "Stanford CS231n", "url": "https://cs231n.stanford.edu/"},
        {"title": "arXiv survey", "url": "https://arxiv.org/abs/1404.7828"}]
    model_obj = {"sources": [
        {"title": "Stanford CS231n <script>x</script>", "url": "https://cs231n.stanford.edu/", "note": "course"},
        {"title": "arXiv survey", "url": "https://arxiv.org/abs/1404.7828", "note": "overview"},
        {"title": "Made-up", "url": "https://not-retrieved.example.com/x", "note": "hallucinated"}]}
    def fake_sourced(prompt):
        return model_obj, captured
    lib = gen.ensure_bibliography(root, cid, generate_sourced=fake_sourced)
    urls = [s["url"] for s in lib["sources"]]
    assert "https://not-retrieved.example.com/x" not in urls   # dropped: not really retrieved
    assert "https://cs231n.stanford.edu/" in urls and "https://arxiv.org/abs/1404.7828" in urls
    types = {s["url"]: s["type"] for s in lib["sources"]}
    assert types["https://cs231n.stanford.edu/"] == "university"
    assert types["https://arxiv.org/abs/1404.7828"] == "preprint"
    assert "<script" not in lib["sources"][0]["title"]          # title sanitized
    # cached: second call returns without regenerating
    lib2 = gen.ensure_bibliography(root, cid, generate_sourced=lambda p: (_ for _ in ()).throw(AssertionError("regen")))
    assert lib2["courseId"] == cid


def test_ensure_bibliography_normalizes_legacy_cached_source_types(tmp_path):
    # A library.json written before the source_type() honesty fix has arxiv mislabeled
    # "peer-reviewed" on disk. Reading it back must relabel it live (not just fresh writes),
    # without needing to touch/rewrite the cache file itself.
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L"}]}]})
    cid = manifest["id"]
    path = root / cid / "library.json"
    legacy = {"courseId": cid, "title": "T", "sources": [
        {"title": "arXiv survey", "url": "https://arxiv.org/abs/1404.7828",
         "type": "peer-reviewed", "note": "n"}]}
    path.write_text(_json.dumps(legacy))
    on_disk_before = path.read_text()
    lib = gen.ensure_bibliography(root, cid, generate_sourced=lambda p: (_ for _ in ()).throw(AssertionError("regen")))
    assert lib["sources"][0]["type"] == "preprint"     # relabeled honestly on read
    assert path.read_text() == on_disk_before          # cache file itself untouched


# ---- Phase 2: per-lesson grounding + roll-up ----

def test_lesson_prompt_asks_for_web_grounded_sources():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="c-l1", lesson_title="L",
                          module_title="M", position=1, total=3)
    low = p.lower()
    assert "web search" in low
    assert "accredited" in low
    assert "sources" in low  # the sources field is requested


def test_ensure_lesson_stores_only_really_retrieved_sources(tmp_path):
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    made["sources"] = [
        {"title": "Stanford CS231n", "url": "https://cs231n.stanford.edu/"},
        {"title": "Hallucinated", "url": "https://not-real.example.com/x"}]
    captured = [{"title": "Stanford CS231n", "url": "https://cs231n.stanford.edu/"}]
    def generate(prompt):
        return made, captured  # sourced generator returns a tuple
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=generate)
    urls = [s["url"] for s in out["sources"]]
    assert urls == ["https://cs231n.stanford.edu/"]        # hallucinated dropped
    assert out["sources"][0]["type"] == "university"       # domain-typed
    # persisted to disk with sources
    on_disk = _json.loads((root / "demo" / "lessons" / "demo-l1.json").read_text())
    assert on_disk["sources"][0]["url"] == "https://cs231n.stanford.edu/"


def test_ensure_lesson_without_tuple_defaults_to_no_sources(tmp_path):
    # A plain (non-sourced) generator returning just a dict still works — sources = [].
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"; made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: made)
    assert out["sources"] == []


def test_course_lesson_sources_rolls_up_and_dedupes(tmp_path):
    root = tmp_path / "courses"; root.mkdir()
    from backend import courses
    manifest = courses.write_course(root, {"title": "T", "subtitle": "s", "brief": "b",
        "modules": [{"title": "M", "lessons": [{"title": "L1"}, {"title": "L2"}]}]})
    cid = manifest["id"]
    ldir = root / cid / "lessons"
    # "peer-reviewed" here simulates a legacy on-disk type predating the source_type()
    # honesty fix — course_lesson_sources() must recompute from the URL, not trust it.
    l1 = {"id": "a", "sources": [
        {"title": "arXiv", "url": "https://arxiv.org/abs/1", "type": "peer-reviewed"},
        {"title": "MIT", "url": "https://mit.edu/x", "type": "university"}]}
    l2 = {"id": "b", "sources": [
        {"title": "arXiv dup", "url": "https://arxiv.org/abs/1", "type": "peer-reviewed"},
        {"title": "Docs", "url": "https://pytorch.org/docs", "type": "official-docs"}]}
    (ldir / "a.json").write_text(_json.dumps(l1))
    (ldir / "b.json").write_text(_json.dumps(l2))
    rolled = gen.course_lesson_sources(root, cid)
    urls = [s["url"] for s in rolled]
    assert urls.count("https://arxiv.org/abs/1") == 1   # deduped across lessons
    assert "https://mit.edu/x" in urls and "https://pytorch.org/docs" in urls
    assert rolled[0]["type"] == "university"            # sorted: university first
    types = {s["url"]: s["type"] for s in rolled}
    assert types["https://arxiv.org/abs/1"] == "preprint"  # legacy "peer-reviewed" relabeled


def test_course_system_prompt_decouples_depth_from_daily_time():
    p = gen.COURSE_SYSTEM_PROMPT
    low = p.lower()
    assert "how intensively" not in low               # old time/intensity ask removed
    assert '"pace"' not in p and "depth, pace" not in p  # brief no longer captures pace
    assert "self-paced" in low                        # explicitly self-paced
    assert "how deep" in low or "desired depth" in low # depth still asked
    assert "per day" not in low or "do not ask" in low # daily time only mentioned to forbid it


def test_lesson_chat_prompt_includes_lesson_context():
    lesson = {"topic": "HTTP requests", "promptHtml": "<p>what is a GET</p>",
              "solutionAns": "GET /x", "solutionNote": "method+path"}
    p = gen.lesson_chat_prompt(lesson, [{"role": "user", "content": "does http/2 change this?"}])
    assert "HTTP requests" in p
    assert "what is a GET" in p
    assert "Learner: does http/2 change this?" in p
    assert p.rstrip().endswith("You:")


def test_lesson_chat_sse_streams_delta_then_done():
    def fake_stream(prompt):
        yield "HTTP/2 keeps "
        yield "the same idea."
    lesson = {"topic": "HTTP", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    chunks = list(gen.lesson_chat_sse(lesson, [{"role": "user", "content": "q?"}], stream_fn=fake_stream))
    evs = _events(chunks)
    assert ("delta", "HTTP/2 keeps") in evs
    assert evs[-1][0] == "done"


def test_lesson_chat_sse_emits_reauth_on_auth_error():
    def failing(prompt):
        raise claude_client.ClaudeAuthError("Invalid API key")
        yield
    chunks = list(gen.lesson_chat_sse({"topic": "t"}, [{"role": "user", "content": "x"}], stream_fn=failing))
    msg = [d for (e, d) in _events(chunks) if e == "error"]
    assert msg and "re-authentication" in msg[0].lower()


def test_lesson_chat_system_guides_first_with_escape_hatch():
    s = generation.LESSON_CHAT_SYSTEM
    assert "MAIN EXERCISE" in s
    assert "ONE short guiding question" in s
    assert "give it plainly" in s


def test_lesson_chat_prompt_carries_solution_reveal_state():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    hidden = generation.lesson_chat_prompt(lesson, [])
    assert "has NOT yet revealed the solution" in hidden
    shown = generation.lesson_chat_prompt(lesson, [], solution_revealed=True)
    assert "has already revealed the solution" in shown
    assert "has NOT yet revealed" not in shown


def test_socratic_cowork_system_rules():
    s = gen.SOCRATIC_COWORK_SYSTEM
    assert "NEVER state it" in s
    assert "Reveal solution button" in s
    assert "One question per turn" in s
    assert "under 80 words" in s
    assert "exercise answer box" in s


def test_lesson_chat_prompt_socratic_swaps_system_keeps_context():
    lesson = {"topic": "HTTP requests", "promptHtml": "<p>what is a GET</p>",
              "solutionAns": "GET /x", "solutionNote": "method+path"}
    p = gen.lesson_chat_prompt(lesson, [{"role": "user", "content": "first step?"}],
                               socratic=True)
    assert "NEVER state it" in p                      # socratic system present
    assert "ONE short guiding question" not in p      # default system replaced
    assert "HTTP requests" in p
    assert "what is a GET" in p
    assert "GET /x" in p                              # reference answer still in context
    assert "has NOT yet revealed the solution" in p
    assert "Learner: first step?" in p
    assert p.rstrip().endswith("You:")


def test_lesson_chat_prompt_socratic_carries_reveal_state():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    shown = gen.lesson_chat_prompt(lesson, [], solution_revealed=True, socratic=True)
    assert "has already revealed the solution" in shown


def test_lesson_chat_prompt_default_unchanged_without_socratic():
    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    p = gen.lesson_chat_prompt(lesson, [])
    assert "ONE short guiding question" in p
    assert "give it plainly" in p
    assert "NEVER state it" not in p


def test_lesson_chat_sse_threads_socratic_flag():
    seen = []

    def fake_stream(prompt):
        seen.append(prompt)
        yield "ok"

    lesson = {"topic": "t", "promptHtml": "<p>q</p>", "solutionAns": "a", "solutionNote": "n"}
    chunks = list(gen.lesson_chat_sse(lesson, [], stream_fn=fake_stream, socratic=True))
    assert "NEVER state it" in seen[0]
    assert _events(chunks)[-1][0] == "done"


# ---- self-consistency: prompt hardening + verification pass ----

def _full_lesson(**over):
    base = {"id": "demo-l1", "courseId": "demo", "topic": "t", "step": 1, "totalSteps": 1,
            "eyebrow": "EXERCISE", "promptHtml": "<p>body</p>", "hintHtml": "h",
            "solutionAns": "a", "solutionNote": "n", "checks": [dict(_OK_CHECK)],
            "preQuiz": dict(_OK_PREQUIZ), "spine": _ok_spine()}
    base.update(over)
    return base


def test_lesson_prompt_requires_self_containment_and_consistency():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    low = p.lower()
    assert "self-contained" in low
    assert "answerable using only what you teach" in low
    assert "exact same name" in low                 # one consistent vocabulary
    assert "visual aid must match the prose" in low  # diagram cannot contradict text


def test_lesson_prompt_checks_have_mcq_self_verification():
    p = gen.lesson_prompt(brief="b", profile={}, lesson_id="x-l1", lesson_title="T",
                          module_title="M", position=1, total=2)
    assert "re-answer each mcq check" in p
    assert "Confirm the choice at answer is the answer you get" in p
    assert "no distractor is also defensibly correct" in p


def test_lesson_chat_system_mirrors_lesson_vocabulary():
    low = gen.LESSON_CHAT_SYSTEM.lower()
    assert "mirror the lesson's own vocabulary" in low
    assert "even if you know a different textbook name" in low


def _verify_stub(audit_result, review_result):
    """A verify_generate(prompt, validate) stub: routes the rewrite call (which asks for a
    CORRECTED lesson) to review_result and the audit call to audit_result."""
    def verify(prompt, validate=None):
        if "CORRECTED" in prompt:
            return review_result() if callable(review_result) else review_result
        return audit_result() if callable(audit_result) else audit_result
    return verify


def test_valid_audit_shape():
    assert gen.valid_audit({"ok": True})
    assert gen.valid_audit({"ok": False, "issues": ["x"]})
    assert not gen.valid_audit({"ok": False, "issues": []})   # must name at least one issue
    assert not gen.valid_audit({"ok": False})                 # issues required when not ok
    assert not gen.valid_audit({"ok": "yes"})                 # ok must be a bool
    assert not gen.valid_audit("nope")


def test_lesson_audit_prompt_asks_for_ok_verdict():
    p = gen.lesson_audit_prompt(_full_lesson(topic="business cycles"))
    assert '{"ok": true}' in p
    assert "business cycles" in p            # the lesson under review is embedded
    assert "consistent terminology" in p.lower()


def test_lesson_audit_prompt_checks_objective_coverage():
    p = gen.lesson_audit_prompt(_full_lesson())
    assert "OBJECTIVE COVERAGE" in p
    assert "perform each stated objective's action verb" in p


def test_lesson_audit_prompt_lists_objectives_when_provided():
    objectives = [{"text": "Calculate the multiplier effect", "bloom": "apply"}]
    p = gen.lesson_audit_prompt(_full_lesson(), objectives=objectives)
    assert "Calculate the multiplier effect" in p
    p_none = gen.lesson_audit_prompt(_full_lesson())
    assert "Calculate the multiplier effect" not in p_none


def test_lesson_review_prompt_states_the_three_rules():
    p = gen.lesson_review_prompt(_full_lesson(topic="business cycles"))
    low = p.lower()
    assert "self-contained" in low
    assert "consistent terminology" in low
    assert "visual aid matches prose" in low
    assert "business cycles" in p            # the lesson under review is embedded
    assert "do not change" in low and "sources" in low  # citations are off-limits


def test_lesson_review_prompt_includes_flagged_issues_when_given():
    p = gen.lesson_review_prompt(_full_lesson(), issues=["graphic says Slowdown, answer says contraction"])
    assert "graphic says Slowdown, answer says contraction" in p
    p2 = gen.lesson_review_prompt(_full_lesson())
    assert "already flagged" not in p2


def test_lesson_review_prompt_checks_objective_coverage_and_lists_objectives():
    p = gen.lesson_review_prompt(_full_lesson())
    assert "OBJECTIVE COVERAGE" in p
    objectives = [{"text": "Calculate the multiplier effect", "bloom": "apply"}]
    p_with = gen.lesson_review_prompt(_full_lesson(), objectives=objectives)
    assert "Calculate the multiplier effect" in p_with


def test_verification_rewrites_only_when_audit_flags_a_defect(tmp_path):
    root = _course(tmp_path)
    raw = _full_lesson(promptHtml="<p>uses Slowdown</p>", solutionAns="early contraction")
    fixed = _full_lesson(promptHtml="<p>uses Slowdown</p>", solutionAns="Slowdown")
    audit = {"ok": False, "issues": ["solutionAns 'early contraction' vs graphic 'Slowdown'"]}
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(raw),
                            verify_generate=_verify_stub(audit, lambda: dict(fixed)))
    assert out["solutionAns"] == "Slowdown"       # reconciled version was stored
    on_disk = _json.loads((root / "demo" / "lessons" / "demo-l1.json").read_text())
    assert on_disk["solutionAns"] == "Slowdown"


def test_verification_skips_rewrite_when_audit_is_clean(tmp_path):
    root = _course(tmp_path)
    raw = _full_lesson(solutionAns="as generated")
    def no_rewrite():
        raise AssertionError("rewrite must not run when the audit says ok")
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(raw),
                            verify_generate=_verify_stub({"ok": True}, no_rewrite))
    assert out["solutionAns"] == "as generated"   # audit clean -> lesson stored unchanged


def test_verification_falls_back_to_original_when_review_is_invalid(tmp_path):
    root = _course(tmp_path)
    raw = _full_lesson(solutionAns="original answer")
    audit = {"ok": False, "issues": ["something"]}
    # rewrite returns junk (missing required keys) -> keep the original, never break the lesson
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(raw),
                            verify_generate=_verify_stub(audit, {"bad": 1}))
    assert out["solutionAns"] == "original answer"


def test_verification_falls_back_when_audit_errors(tmp_path):
    root = _course(tmp_path)
    raw = _full_lesson(solutionAns="original answer")
    def boom(prompt, validate=None):
        raise claude_client.ClaudeError("audit down")
    out = gen.ensure_lesson(root, "demo", "demo-l1", {},
                            generate=lambda p: dict(raw), verify_generate=boom)
    assert out["solutionAns"] == "original answer"


def test_verification_threads_objectives_into_audit_prompt(tmp_path):
    """_generate_and_store_lesson has meta.get("objectives") in scope; it must reach
    the audit prompt via _reviewed_lesson so the objective-coverage rule can be checked
    against the lesson's actual objectives."""
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(_json.dumps({
        "id": "demo", "title": "Demo", "subtitle": "", "brief": "beginner friendly",
        "modules": [{"id": "m1", "title": "Basics",
                     "lessons": [{"id": "demo-l1", "title": "First",
                                 "objectives": [{"text": "Calculate the multiplier effect",
                                                 "bloom": "apply"}]}]}],
    }))
    raw = _full_lesson(solutionAns="as generated")
    captured = {}

    def spy_verify(prompt, validate=None):
        if "CORRECTED" not in prompt:
            captured["audit_prompt"] = prompt
        return {"ok": True}

    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(raw),
                            verify_generate=spy_verify)
    assert out["solutionAns"] == "as generated"
    assert "Calculate the multiplier effect" in captured["audit_prompt"]


def test_verification_preserves_original_sources(tmp_path):
    root = _course(tmp_path)
    src = [{"title": "MIT OCW", "url": "https://ocw.mit.edu/x"}]
    raw = _full_lesson(sources=list(src))
    audit = {"ok": False, "issues": ["term drift"]}
    # a rewrite that strips sources must not lose the real, captured citations
    fixed = _full_lesson(sources=[], solutionAns="reconciled")
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: (dict(raw), src),
                            verify_generate=_verify_stub(audit, lambda: dict(fixed)))
    assert out["solutionAns"] == "reconciled"
    assert [s["url"] for s in out["sources"]] == ["https://ocw.mit.edu/x"]


def test_ensure_lesson_skips_verification_when_not_requested(tmp_path):
    root = _course(tmp_path)
    raw = _full_lesson(solutionAns="unreviewed")
    out = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: dict(raw))
    assert out["solutionAns"] == "unreviewed"  # no verify_generate -> stored as generated


# ---- Sub-project A: program-backbone schema (Bloom objectives, levels, prereq graph) ----

def test_valid_objective_accepts_action_verb_and_tags():
    assert generation.valid_objective(
        {"text": "Calculate the gradient of a loss function", "bloom": "apply", "knowledge": "procedural"})

def test_valid_objective_rejects_banned_verbs():
    for bad in ("Understand recursion", "Know the four phases", "Learn about markets",
                "Appreciate the design", "Be aware of the risks", "Grasp the concept"):
        assert not generation.valid_objective({"text": bad, "bloom": "understand", "knowledge": "conceptual"})

def test_valid_objective_allows_knowledge_word_not_matching_know():
    # "knowledge" must NOT trip the \bknow\b lint (word-boundary, not substring)
    assert generation.valid_objective(
        {"text": "Analyze a knowledge-representation scheme", "bloom": "analyze", "knowledge": "conceptual"})

def test_valid_objective_allows_learning_as_domain_noun():
    # the -ing gerund forms are domain nouns, not the weak objective verb the lint targets:
    # an ML course's objectives are full of "learning" and must not be rejected wholesale.
    for good in ("Apply supervised learning to a labelled dataset",
                 "Compare deep learning architectures",
                 "Design a reinforcement learning reward function",
                 "Build a shared understanding of the bias-variance tradeoff"):
        assert generation.valid_objective({"text": good, "bloom": "apply", "knowledge": "procedural"})
    # but the base weak verbs are still banned
    for bad in ("Learn about gradient descent", "Understand backpropagation"):
        assert not generation.valid_objective({"text": bad, "bloom": "apply", "knowledge": "procedural"})

def test_valid_objective_rejects_bad_tags():
    assert not generation.valid_objective({"text": "Derive Bayes' rule", "bloom": "prove", "knowledge": "conceptual"})
    assert not generation.valid_objective({"text": "Derive Bayes' rule", "bloom": "apply", "knowledge": "meta"})
    assert not generation.valid_objective({"text": "", "bloom": "apply", "knowledge": "procedural"})

def test_valid_outcomes_requires_nonempty_list_of_objectives():
    assert generation.valid_outcomes([{"text": "Compare two models", "bloom": "analyze", "knowledge": "conceptual"}])
    assert not generation.valid_outcomes([])
    assert not generation.valid_outcomes("nope")


# ---- Task 2: Prerequisite-graph + compiled-course validators ----

OBJ = {"text": "Calculate X", "bloom": "apply", "knowledge": "procedural"}

def _mods_with_prereqs(edges):
    # edges: {lessonId: [prereqIds]} over lessons l1,l2,l3 in one module
    return [{"id": "m1", "title": "M", "outcomes": [OBJ],
             "lessons": [{"id": lid, "title": lid, "objectives": [OBJ], "estMinutes": 60,
                          "prereqs": edges.get(lid, [])} for lid in ("l1", "l2", "l3")]}]

def test_valid_prereq_graph_accepts_earlier_only_dag():
    assert generation.valid_prereq_graph(_mods_with_prereqs({"l2": ["l1"], "l3": ["l1", "l2"]}))

def test_valid_prereq_graph_rejects_forward_edge():
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l1": ["l2"]}))

def test_valid_prereq_graph_rejects_self_and_unknown_edge():
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l2": ["l2"]}))
    assert not generation.valid_prereq_graph(_mods_with_prereqs({"l3": ["l9"]}))

def _compiled():
    return {"schemaVersion": 2, "title": "T", "subtitle": "",
            "level": {"code": "bachelor-y2", "label": "Bachelor Year 2-equivalent"},
            "targetHours": 130, "skills": ["do X"], "outcomes": [OBJ],
            "groundingSources": [], "modules": _mods_with_prereqs({"l2": ["l1"]})}

def test_valid_compiled_course_accepts_full_shape():
    assert generation.valid_compiled_course(_compiled())

def test_valid_compiled_course_rejects_missing_pieces():
    c = _compiled(); c.pop("outcomes"); assert not generation.valid_compiled_course(c)
    c = _compiled(); c["level"] = {"code": "phd", "label": "x"}; assert not generation.valid_compiled_course(c)
    c = _compiled(); c["schemaVersion"] = 1; assert not generation.valid_compiled_course(c)
    c = _compiled(); c["modules"][0]["lessons"][0].pop("objectives"); assert not generation.valid_compiled_course(c)


# ---- Task 3: intake-interview prompt + learnerBrief detection + brief SSE event ----

def test_detect_brief_parses_fenced_block():
    text = ('Great, here is your brief.\n```learnerBrief\n'
            '{"goal":"build ML models","background":"python dev","priorKnowledge":["python"],'
            '"motivation":"career","desiredDepth":"deep"}\n```')
    brief = generation.detect_brief(text)
    assert brief["goal"] == "build ML models" and brief["priorKnowledge"] == ["python"]

def test_detect_brief_ignores_prose():
    assert generation.detect_brief("just a normal chat reply, no block") is None

def test_chat_sse_emits_brief_event():
    brief_json = ('```learnerBrief\n{"goal":"g","background":"b","priorKnowledge":[],'
                  '"motivation":"m","desiredDepth":"d"}\n```')
    def fake_stream(prompt):
        yield brief_json
    frames = "".join(generation.chat_sse([{"role": "user", "content": "hi"}], None, stream_fn=fake_stream))
    assert "event: brief" in frames and '"goal": "g"' in frames
    assert "event: proposal" not in frames


# ---- Task 11: constructive alignment — Bloom objectives in lesson prompt ----

def test_lesson_prompt_includes_objectives_alignment():
    p = generation.lesson_prompt(brief="b", profile=None, lesson_id="c-l1", lesson_title="A",
        module_title="M", position=1, total=3,
        objectives=[{"text": "Calculate the mean", "bloom": "apply", "knowledge": "procedural"}])
    assert "Calculate the mean" in p and "constructive alignment" in p

def test_lesson_prompt_omits_block_without_objectives():
    p = generation.lesson_prompt(brief="b", profile=None, lesson_id="c-l1", lesson_title="A",
        module_title="M", position=1, total=3)
    assert "constructive alignment" not in p


# ---- #5 explain-it-back grading ----

def test_explain_answer_grades_and_sanitizes(tmp_path):
    import json as _json
    d = tmp_path / "c1" / "lessons"
    d.mkdir(parents=True)
    (d / "c1-l1.json").write_text(_json.dumps({
        "id": "c1-l1", "promptHtml": "<p>Body</p>", "solutionAns": "42", "solutionNote": "why",
    }))
    captured = {}
    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"verdict": "close", "note": "Nice <script>alert(1)</script> effort",
                "followUp": "why?"}
    result = generation.explain_answer(tmp_path, "c1", "c1-l1", "my own words", generate=fake_generate)
    assert result["verdict"] == "close"
    assert "<script>" not in result["note"]
    assert "my own words" in captured["prompt"]
    assert "42" in captured["prompt"]


def test_explain_answer_none_for_missing_lesson(tmp_path):
    assert generation.explain_answer(tmp_path, "c1", "c1-l9", "x", generate=lambda p: {}) is None


def test_valid_explain_requires_followup():
    base = {"verdict": "close", "note": "good try"}
    assert not generation.valid_explain(base)
    assert not generation.valid_explain({**base, "followUp": "  "})
    assert generation.valid_explain({**base, "followUp": "Why does that hold?"})
    assert not generation.valid_explain({**base, "verdict": "nope", "followUp": "q"})


def test_explain_prompt_asks_for_followup():
    p = generation.explain_prompt(prompt_html="<p>q</p>", solution_ans="a",
                                  solution_note="n", explanation="e")
    assert "followUp" in p
    assert "weakest point" in p
    assert "transfer question" in p


def test_explain_answer_sanitizes_followup(tmp_path):
    import json as _json
    d = tmp_path / "c1" / "lessons"
    d.mkdir(parents=True)
    (d / "c1-l1.json").write_text(_json.dumps({
        "id": "c1-l1", "promptHtml": "<p>Body</p>", "solutionAns": "42", "solutionNote": "why",
    }))
    def fake_generate(prompt):
        return {"verdict": "close", "note": "<script>x</script>ok", "followUp": "<script>y</script>why?"}
    result = generation.explain_answer(tmp_path, "c1", "c1-l1", "my own words", generate=fake_generate)
    assert "<script>" not in result["note"]
    assert "<script>" not in result["followUp"]
    assert "why?" in result["followUp"]


# ---- corrupt-cache self-heal: ensure_lesson regenerates instead of hitting a dead end ----

def test_ensure_lesson_regenerates_corrupt_cache(tmp_path):
    # same manifest + stub generate as test_ensure_lesson_generates_validates_and_caches
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    def generate(prompt):
        return made
    lesson_path = root / "demo" / "lessons" / "demo-l1.json"
    lesson_path.parent.mkdir(parents=True, exist_ok=True)
    lesson_path.write_text('{"truncated": ')  # corrupt cache — must NOT be a dead end
    lesson = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=generate)
    assert lesson is not None
    assert _json.loads(lesson_path.read_text())  # cache repaired with valid JSON


# ---- Task 4: single-flight lock — concurrent ensure_lesson calls must not double-generate ----

import threading
import time


def test_ensure_lesson_single_flight(tmp_path):
    # same manifest + stub generate as test_ensure_lesson_generates_validates_and_caches
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    calls = []

    def slow_generate(prompt):
        calls.append(1)
        time.sleep(0.3)
        return made

    results = [None, None]

    def hit(i):
        results[i] = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=slow_generate)

    t1 = threading.Thread(target=hit, args=(0,))
    t2 = threading.Thread(target=hit, args=(1,))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert len(calls) == 1  # second caller waited, then served the cache
    assert results[0] == results[1]


# ---- Task 1: required preQuiz field (pretesting effect) ----

def _valid_lesson_base():
    # Build from the file's existing valid-lesson fixture; shown here explicitly
    # so this test is self-contained if the fixture name differs.
    return {
        "id": "c-l1", "courseId": "c", "topic": "T", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "<p>Body</p>", "hintHtml": "h",
        "solutionAns": "a", "solutionNote": "n",
        "checks": [{"type": "fill", "prompt": "q", "answer": "a", "explanation": "e"}],
        "preQuiz": {"type": "mcq", "prompt": "Guess?", "choices": ["A", "B"],
                    "answer": 0, "explanation": "Because."},
        "spine": _ok_spine(),
    }


def test_valid_lesson_requires_prequiz():
    lesson = _valid_lesson_base()
    assert generation.valid_lesson(lesson)
    del lesson["preQuiz"]
    assert not generation.valid_lesson(lesson)


def test_valid_lesson_rejects_malformed_prequiz():
    lesson = _valid_lesson_base()
    lesson["preQuiz"] = {"type": "mcq", "prompt": "", "choices": ["A"], "answer": 0, "explanation": "e"}
    assert not generation.valid_lesson(lesson)


def test_lesson_prompt_mentions_prequiz():
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="c-l1", lesson_title="T",
        module_title="M", position=1, total=1,
    )
    assert "preQuiz" in prompt


# ---- Task 2: Harvest — generated lessons carry a required spine entry ----

def test_valid_lesson_requires_spine():
    good = {
        "id": "l1", "courseId": "c", "topic": "t", "step": 1, "totalSteps": 1,
        "eyebrow": "EXERCISE", "promptHtml": "<p>q</p>", "hintHtml": "<p>h</p>",
        "solutionAns": "a", "solutionNote": "n",
        "checks": [{"type": "fill", "prompt": "p", "answer": "a", "explanation": "e"}],
        "preQuiz": dict(_OK_PREQUIZ),
    }
    assert not generation.valid_lesson(good)  # missing spine
    good["spine"] = _ok_spine()
    assert generation.valid_lesson(good)
    good["spine"] = {"summary": "s", "concepts": []}
    assert not generation.valid_lesson(good)


def test_lesson_prompt_asks_for_spine():
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l1", lesson_title="T",
        module_title="M", position=1, total=2)
    assert "spine:" in prompt
    assert "NO HTML in any spine field" in prompt
    assert "EXACT term spelling" in prompt


def test_ensure_lesson_pops_spine_and_writes_spine_json(tmp_path):
    # same manifest + lesson-dict style as test_ensure_lesson_generates_validates_and_caches
    root = _course(tmp_path)
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = "demo-l1"
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    lesson = gen.ensure_lesson(root, "demo", "demo-l1", {}, generate=lambda p: made)
    assert "spine" not in lesson
    cached = _json.loads((root / "demo" / "lessons" / "demo-l1.json").read_text())
    assert "spine" not in cached
    from backend import spine as spine_mod
    assert spine_mod.load_spine(root, "demo")["lessons"]["demo-l1"] == _ok_spine()


def test_spine_block_empty_when_no_earlier_lessons():
    assert generation.spine_block([], {"c-l1": _ok_spine()}) == ""


def test_spine_block_definitions_for_recent_terms_only_for_older():
    earlier = [{"id": f"c-l{i}", "title": f"Lesson {i}", "objectives": []}
               for i in range(1, 11)]  # 10 earlier lessons
    entries = {f"c-l{i}": {"summary": f"Sum {i}.",
                           "concepts": [{"term": f"term{i}", "definition": f"def {i}"}]}
               for i in range(1, 11)}
    block = generation.spine_block(earlier, entries)
    # oldest two fall outside SPINE_RECENT=8: summary + term name, no definition
    # (compare full "term = def" pairs — "def 1" alone is a substring of "def 10")
    assert "Sum 1." in block and "term1" in block and "term1 = def 1" not in block
    assert "Sum 2." in block and "term2 = def 2" not in block
    # the recent eight carry full definitions
    assert "term3 = def 3" in block and "term10 = def 10" in block
    assert "do NOT re-teach" in block
    assert "Never refer to lessons by number" in block


def test_spine_block_falls_back_to_objectives_for_ungenerated_lessons():
    earlier = [{"id": "c-l1", "title": "Recursion basics",
                "objectives": [{"text": "Trace a recursive call", "bloom": "apply"}]}]
    block = generation.spine_block(earlier, {})
    assert "Recursion basics" in block
    assert "planned, not yet studied" in block
    assert "Trace a recursive call" in block


def test_lesson_prompt_appends_spine_context():
    ctx = "\n\nThe learner has ALREADY covered these earlier lessons"
    prompt = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l2", lesson_title="T",
        module_title="M", position=2, total=2, spine_context=ctx)
    assert ctx in prompt
    without = generation.lesson_prompt(
        brief="b", profile={}, lesson_id="l2", lesson_title="T",
        module_title="M", position=2, total=2)
    assert "ALREADY covered" not in without


def _course_with_two_lessons(tmp_path):
    # same manifest style as _course, but course id "c" with two lessons in one module,
    # so c-l2's generation prompt can be checked for injected c-l1 spine context.
    from backend import courses
    root = tmp_path / "courses"
    (root / "c" / "lessons").mkdir(parents=True)
    (root / "c" / "course.json").write_text(_json.dumps({
        "id": "c", "title": "Course", "subtitle": "", "brief": "beginner friendly",
        "modules": [{"id": "m1", "title": "Basics",
                     "lessons": [{"id": "c-l1", "title": "First"},
                                 {"id": "c-l2", "title": "Second"}]}],
    }))
    return root


def _made_lesson_for(lesson_id):
    made = {k: "x" for k in gen.LESSON_KEYS}
    made["id"] = lesson_id
    made["checks"] = [dict(_OK_CHECK)]
    made["preQuiz"] = dict(_OK_PREQUIZ)
    made["spine"] = _ok_spine()
    return made


def test_ensure_lesson_injects_earlier_spine_into_prompt(tmp_path):
    cdir = _course_with_two_lessons(tmp_path)  # a manifest with c-l1 then c-l2
    from backend import spine as spine_mod
    spine_mod.upsert_entry(cdir, "c", "c-l1", _ok_spine())
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        made = _made_lesson_for("c-l2")  # complete valid lesson dict incl. preQuiz + spine
        return made

    generation.ensure_lesson(cdir, "c", "c-l2", {}, generate=fake_generate)
    assert "recursion = A function calling itself on a smaller input." in prompts[0]
    assert 'As you saw in' in prompts[0]
