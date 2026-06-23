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
