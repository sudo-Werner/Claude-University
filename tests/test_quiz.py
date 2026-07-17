import json
import threading
import time

import pytest

from backend import claude_client, courses, db, events, quiz


def _rapid_fire_q(lesson_id="c-l1", **over):
    q = {"lesson_id": lesson_id, "prompt": "What is X?", "choices": ["a", "b", "c"],
         "answer": 1, "reveal": "Because b is right."}
    q.update(over)
    return q


def _rapid_fire_round(n=8, lesson_id="c-l1"):
    return {"title": "Quick Round", "host_intro": "Let's go!", "format": "rapid_fire",
            "questions": [_rapid_fire_q(lesson_id) for _ in range(n)]}


def test_valid_round_accepts_good_rapid_fire():
    assert quiz.valid_round(_rapid_fire_round(), pool={"c-l1"})


def test_valid_round_rejects_unknown_format():
    obj = _rapid_fire_round()
    obj["format"] = "trivia"
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_rejects_bad_question_count():
    assert not quiz.valid_round(_rapid_fire_round(n=3), pool={"c-l1"})   # below 8
    assert not quiz.valid_round(_rapid_fire_round(n=20), pool={"c-l1"})  # above 12


def test_valid_round_rejects_out_of_range_answer_index():
    obj = _rapid_fire_round()
    obj["questions"][0]["answer"] = 9
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_rejects_bool_as_answer_index():
    obj = _rapid_fire_round()
    obj["questions"][0]["answer"] = True  # bool is not a valid index, even though isinstance(True, int)
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_rejects_oversize_strings():
    obj = _rapid_fire_round()
    obj["questions"][0]["prompt"] = "x" * 301
    assert not quiz.valid_round(obj, pool={"c-l1"})
    obj2 = _rapid_fire_round()
    obj2["title"] = "x" * 81
    assert not quiz.valid_round(obj2, pool={"c-l1"})
    obj3 = _rapid_fire_round()
    obj3["host_intro"] = "x" * 201
    assert not quiz.valid_round(obj3, pool={"c-l1"})
    obj4 = _rapid_fire_round()
    obj4["questions"][0]["choices"][0] = "x" * 121
    assert not quiz.valid_round(obj4, pool={"c-l1"})


def test_valid_round_rejects_foreign_lesson_id():
    assert not quiz.valid_round(_rapid_fire_round(lesson_id="not-in-pool"), pool={"c-l1"})


def test_valid_round_rejects_empty_or_whitespace_strings():
    obj = _rapid_fire_round()
    obj["questions"][0]["reveal"] = "   "
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_rejects_too_few_or_too_many_choices():
    obj = _rapid_fire_round()
    obj["questions"][0]["choices"] = ["a", "b"]  # needs 3-5
    assert not quiz.valid_round(obj, pool={"c-l1"})
    obj2 = _rapid_fire_round()
    obj2["questions"][0]["choices"] = ["a", "b", "c", "d", "e", "f"]
    assert not quiz.valid_round(obj2, pool={"c-l1"})


def test_valid_round_true_false_accepts_good_shape():
    obj = {"title": "T/F", "host_intro": "Go!", "format": "true_false",
           "questions": [{"lesson_id": "c-l1", "statement": "S", "answer": True, "reveal": "R"}
                        for _ in range(10)]}
    assert quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_true_false_rejects_non_bool_answer():
    obj = {"title": "T/F", "host_intro": "Go!", "format": "true_false",
           "questions": [{"lesson_id": "c-l1", "statement": "S", "answer": 1, "reveal": "R"}
                        for _ in range(10)]}
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_true_false_rejects_bad_question_count():
    obj = {"title": "T/F", "host_intro": "Go!", "format": "true_false",
           "questions": [{"lesson_id": "c-l1", "statement": "S", "answer": True, "reveal": "R"}
                        for _ in range(9)]}  # needs 10-14
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_odd_one_out_requires_exactly_four_items():
    good = {"title": "OOO", "host_intro": "Go!", "format": "odd_one_out",
            "questions": [{"lesson_id": "c-l1", "items": ["a", "b", "c", "d"], "answer": 2, "reveal": "R"}
                         for _ in range(6)]}
    assert quiz.valid_round(good, pool={"c-l1"})
    bad = json.loads(json.dumps(good))
    bad["questions"][0]["items"] = ["a", "b", "c"]
    assert not quiz.valid_round(bad, pool={"c-l1"})


def test_valid_round_spot_the_lie_requires_exactly_three_statements():
    good = {"title": "STL", "host_intro": "Go!", "format": "spot_the_lie",
            "questions": [{"lesson_id": "c-l1", "statements": ["a", "b", "c"], "answer": 1, "reveal": "R"}
                         for _ in range(6)]}
    assert quiz.valid_round(good, pool={"c-l1"})
    bad = json.loads(json.dumps(good))
    bad["questions"][0]["statements"] = ["a", "b"]
    assert not quiz.valid_round(bad, pool={"c-l1"})


def test_valid_round_match_up_requires_five_pairs_per_board():
    good = {"title": "MU", "host_intro": "Go!", "format": "match_up",
            "questions": [{"lesson_id": "c-l1",
                           "pairs": [{"left": f"L{i}", "right": f"R{i}"} for i in range(5)],
                           "reveal": "R"} for _ in range(2)]}
    assert quiz.valid_round(good, pool={"c-l1"})
    bad = json.loads(json.dumps(good))
    bad["questions"][0]["pairs"] = bad["questions"][0]["pairs"][:4]
    assert not quiz.valid_round(bad, pool={"c-l1"})


def test_valid_round_match_up_rejects_wrong_board_count():
    obj = {"title": "MU", "host_intro": "Go!", "format": "match_up",
           "questions": [{"lesson_id": "c-l1",
                          "pairs": [{"left": f"L{i}", "right": f"R{i}"} for i in range(5)],
                          "reveal": "R"}]}  # only 1 board, needs 2-3
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_match_up_rejects_pair_missing_a_side():
    obj = {"title": "MU", "host_intro": "Go!", "format": "match_up",
           "questions": [{"lesson_id": "c-l1",
                          "pairs": [{"left": "A"}] + [{"left": f"L{i}", "right": f"R{i}"} for i in range(1, 5)],
                          "reveal": "R"} for _ in range(2)]}
    assert not quiz.valid_round(obj, pool={"c-l1"})


def test_valid_round_rejects_non_dict():
    assert not quiz.valid_round(None, pool={"c-l1"})
    assert not quiz.valid_round("not a dict", pool={"c-l1"})
    assert not quiz.valid_round(["also", "not"], pool={"c-l1"})


# ---- format weighting + round prompt ----

def test_format_weights_never_played_all_equal():
    weights = quiz.format_weights([])
    assert len(set(weights.values())) == 1
    assert weights["rapid_fire"] == 1.0


def test_format_weights_recently_played_gets_lighter():
    weights = quiz.format_weights(["rapid_fire", "rapid_fire", "true_false"])
    assert weights["rapid_fire"] == pytest.approx(1 / 3)
    assert weights["true_false"] == pytest.approx(1 / 2)
    assert weights["odd_one_out"] == 1.0


def test_format_weights_ignores_unknown_format_strings():
    weights = quiz.format_weights(["not-a-real-format", "rapid_fire"])
    assert weights["rapid_fire"] == pytest.approx(1 / 2)


def test_choose_format_rand_zero_picks_first_format():
    assert quiz.choose_format([], rand=0.0) == quiz.FORMATS[0]


def test_choose_format_rand_near_one_picks_last_format():
    assert quiz.choose_format([], rand=0.999999) == quiz.FORMATS[-1]


def test_choose_format_stays_reachable_after_heavy_play():
    # every format keeps weight > 0 even after being played 50 times, so a
    # rand value in its slice can still pick it.
    history = ["rapid_fire"] * 50
    weights = quiz.format_weights(history)
    assert weights["rapid_fire"] > 0


def test_round_prompt_mentions_format_and_pool_lesson_ids():
    pool = [{"lesson_id": "c-l1", "title": "Intro", "summary": "Basics.",
             "concepts": [{"term": "gradient", "definition": "slope"}]}]
    p = quiz.round_prompt(format="true_false", course_title="ML", pool_lessons=pool)
    assert "true_false" in p and "c-l1" in p and "gradient = slope" in p
    assert "PLAIN TEXT" in p


def test_round_prompt_excludes_lessons_outside_pool():
    pool = [{"lesson_id": "c-l1", "title": "Intro", "summary": "", "concepts": []}]
    p = quiz.round_prompt(format="rapid_fire", course_title="ML", pool_lessons=pool)
    assert "c-l2" not in p


def test_round_prompt_covers_every_format_instruction():
    pool = [{"lesson_id": "c-l1", "title": "Intro", "summary": "S", "concepts": []}]
    for fmt in quiz.FORMATS:
        p = quiz.round_prompt(format=fmt, course_title="ML", pool_lessons=pool)
        assert fmt in p


def _course_dir(tmp_path, completed=("c-l1",), course_id="c"):
    root = tmp_path / "courses"
    (root / course_id / "lessons").mkdir(parents=True)
    (root / course_id / "course.json").write_text(json.dumps({
        "id": course_id, "title": "Course", "subtitle": "", "brief": "",
        "modules": [{"id": "m1", "title": "M1", "lessons": [
            {"id": "c-l1", "title": "L1"}, {"id": "c-l2", "title": "L2"}]}],
    }))
    for lid in completed:
        (root / course_id / "lessons" / f"{lid}.json").write_text(json.dumps({"id": lid}))
    return root


def _complete(conn, lesson_id, course_id="c"):
    events.insert_events(conn, [{
        "client_event_id": f"done-{lesson_id}-{course_id}", "session_id": "s1",
        "event_type": "lesson_completed", "occurred_at": "2026-07-01T10:00:00+00:00",
        "course_id": course_id, "topic_id": lesson_id,
    }])


def _round(round_id="round-aaaaaaaaaaaa", created_at="2026-07-01T00:00:00+00:00", course_id="c"):
    return {"round_id": round_id, "course_id": course_id, "format": "rapid_fire",
            "title": "T", "host_intro": "I", "questions": [], "created_at": created_at}


def _play(conn, fmt, score=1, total=1, occurred="2026-07-01T00:00:00+00:00", course_id="c"):
    events.insert_events(conn, [{
        "client_event_id": f"qr-{occurred}-{fmt}-{course_id}", "session_id": "s1",
        "event_type": "quiz_round", "occurred_at": occurred, "course_id": course_id,
        "topic_id": "round-000000000001",
        "payload": {"format": fmt, "score": score, "total": total, "missed": {}},
    }])


# ---- question_pool ----

def test_question_pool_intersects_completed_and_cached(conn, tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")
    manifest = courses.load_manifest(root, "c")
    pool = quiz.question_pool(root, conn, "c", manifest)
    assert [l["lesson_id"] for l in pool] == ["c-l1"]


def test_question_pool_excludes_completed_without_cached_lesson_file(conn, tmp_path):
    root = _course_dir(tmp_path, completed=())  # c-l1 completed but not cached
    _complete(conn, "c-l1")
    manifest = courses.load_manifest(root, "c")
    pool = quiz.question_pool(root, conn, "c", manifest)
    assert pool == []


def test_question_pool_excludes_uncompleted_even_if_cached(conn, tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1", "c-l2"))  # both cached
    _complete(conn, "c-l1")  # only c-l1 completed
    manifest = courses.load_manifest(root, "c")
    pool = quiz.question_pool(root, conn, "c", manifest)
    assert [l["lesson_id"] for l in pool] == ["c-l1"]


def test_question_pool_pulls_summary_and_concepts_from_spine(conn, tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")
    (root / "c" / "spine.json").write_text(json.dumps({"lessons": {
        "c-l1": {"summary": "Teaches basics.", "concepts": [{"term": "x", "definition": "y"}]}
    }}))
    manifest = courses.load_manifest(root, "c")
    pool = quiz.question_pool(root, conn, "c", manifest)
    assert pool[0]["summary"] == "Teaches basics."
    assert pool[0]["concepts"] == [{"term": "x", "definition": "y"}]


def test_question_pool_empty_when_nothing_completed(conn, tmp_path):
    root = _course_dir(tmp_path, completed=())
    manifest = courses.load_manifest(root, "c")
    assert quiz.question_pool(root, conn, "c", manifest) == []


# ---- bank: save / list / serve / consume ----

def test_save_and_list_bank_orders_oldest_first(tmp_path):
    root = tmp_path / "courses"
    quiz.save_round(root, "c", _round("round-000000000001", "2026-07-02T00:00:00+00:00"))
    quiz.save_round(root, "c", _round("round-000000000002", "2026-07-01T00:00:00+00:00"))
    bank = quiz.list_bank(root, "c")
    assert [r["round_id"] for r in bank] == ["round-000000000002", "round-000000000001"]
    assert quiz.bank_count(root, "c") == 2


def test_serve_round_returns_oldest_without_deleting(tmp_path):
    root = tmp_path / "courses"
    quiz.save_round(root, "c", _round("round-000000000001", "2026-07-02T00:00:00+00:00"))
    quiz.save_round(root, "c", _round("round-000000000002", "2026-07-01T00:00:00+00:00"))
    served = quiz.serve_round(root, "c")
    assert served["round_id"] == "round-000000000002"
    assert quiz.bank_count(root, "c") == 2  # still there — consume_round deletes, not serve


def test_serve_round_none_when_empty(tmp_path):
    root = tmp_path / "courses"
    assert quiz.serve_round(root, "c") is None


def test_list_bank_skips_corrupt_file(tmp_path):
    root = tmp_path / "courses"
    quiz_dir = root / "c" / "quiz-rounds"
    quiz_dir.mkdir(parents=True)
    (quiz_dir / "round-aaaaaaaaaaaa.json").write_text("{not json")
    quiz.save_round(root, "c", _round("round-000000000002"))
    bank = quiz.list_bank(root, "c")
    assert len(bank) == 1
    assert bank[0]["round_id"] == "round-000000000002"


def test_consume_round_deletes_file(tmp_path):
    root = tmp_path / "courses"
    quiz.save_round(root, "c", _round("round-000000000001"))
    quiz.consume_round(root, "c", "round-000000000001")
    assert quiz.bank_count(root, "c") == 0


def test_consume_round_missing_file_is_noop(tmp_path):
    root = tmp_path / "courses"
    quiz.consume_round(root, "c", "round-000000000001")  # must not raise


def test_consume_round_rejects_malformed_round_id(tmp_path):
    root = tmp_path / "courses"
    quiz.consume_round(root, "c", "../etc/passwd")  # must not raise or escape the course dir


def test_finalize_round_keeps_only_known_fields_and_stamps_id():
    obj = {"format": "rapid_fire", "title": "T", "host_intro": "I",
           "questions": [{"lesson_id": "c-l1", "prompt": "P", "choices": ["a", "b", "c"],
                         "answer": 1, "reveal": "R", "extra": "drop me"}]}
    r = quiz.finalize_round(obj, "c")
    assert quiz.ROUND_ID_RE.match(r["round_id"])
    assert r["course_id"] == "c"
    assert "extra" not in r["questions"][0]
    assert r["questions"][0] == {"lesson_id": "c-l1", "prompt": "P", "choices": ["a", "b", "c"],
                                 "answer": 1, "reveal": "R"}
    assert r["created_at"]


def test_finalize_round_match_up_keeps_only_left_right_per_pair():
    obj = {"format": "match_up", "title": "T", "host_intro": "I",
           "questions": [{"lesson_id": "c-l1",
                          "pairs": [{"left": "A", "right": "1", "extra": "x"}] * 5,
                          "reveal": "R", "junk": "y"}]}
    r = quiz.finalize_round(obj, "c")
    assert r["questions"][0]["pairs"][0] == {"left": "A", "right": "1"}
    assert "junk" not in r["questions"][0]


# ---- recent_formats ----

def test_recent_formats_most_recent_first_capped_at_limit(conn):
    for i, fmt in enumerate(["rapid_fire", "true_false", "odd_one_out"]):
        _play(conn, fmt, occurred=f"2026-07-0{i + 1}T00:00:00+00:00")
    assert quiz.recent_formats(conn, "c", limit=2) == ["odd_one_out", "true_false"]


def test_recent_formats_empty_when_never_played(conn):
    assert quiz.recent_formats(conn, "c") == []


# ---- restock (synchronous _restock_once, no threads) ----

def test_restock_generates_until_floor_capped_at_restock_cap(conn, tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")
    calls = []

    def fake_generate(prompt, validate):
        calls.append(prompt)
        obj = {"format": "rapid_fire", "title": "T", "host_intro": "I",
               "questions": [dict(_rapid_fire_q("c-l1")) for _ in range(8)]}
        assert validate(obj)
        return obj

    quiz._restock_once(root, conn, "c", generate=fake_generate)
    assert len(calls) == quiz.RESTOCK_CAP == 3
    assert quiz.bank_count(root, "c") == 3


def test_restock_stops_when_floor_already_met(conn, tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")
    for i in range(quiz.BANK_FLOOR):
        quiz.save_round(root, "c", _round(f"round-00000000000{i}"))
    calls = []
    quiz._restock_once(root, conn, "c", generate=lambda p, v: calls.append(1))
    assert calls == []


def test_restock_stops_silently_on_generation_failure(conn, tmp_path, capsys):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")

    def failing(prompt, validate):
        raise claude_client.ClaudeError("boom")

    quiz._restock_once(root, conn, "c", generate=failing)
    assert quiz.bank_count(root, "c") == 0
    assert "quiz restock failed" in capsys.readouterr().err


def test_restock_swallows_non_claude_error_exceptions(conn, tmp_path, capsys):
    root = _course_dir(tmp_path, completed=("c-l1",))
    _complete(conn, "c-l1")

    def failing(prompt, validate):
        raise RuntimeError("boom")

    quiz._restock_once(root, conn, "c", generate=failing)
    assert quiz.bank_count(root, "c") == 0
    assert "quiz restock failed" in capsys.readouterr().err


def test_restock_stops_when_pool_empty(conn, tmp_path):
    root = _course_dir(tmp_path, completed=())  # nothing completed
    calls = []
    quiz._restock_once(root, conn, "c", generate=lambda p, v: calls.append(1))
    assert calls == []
    assert quiz.bank_count(root, "c") == 0


def test_restock_missing_course_is_noop(conn, tmp_path):
    root = tmp_path / "courses"  # no course dir at all
    calls = []
    quiz._restock_once(root, conn, "c", generate=lambda p, v: calls.append(1))
    assert calls == []


# ---- kick_restock: single-flight lock + injected spawn ----

def test_kick_restock_uses_injected_synchronous_spawn(tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",), course_id="c-lock2")
    db_path = tmp_path / "t.db"
    conn0 = db.get_connection(db_path)
    db.init_db(conn0)
    _complete(conn0, "c-l1", course_id="c-lock2")
    conn0.close()

    def fake_generate(prompt, validate):
        return {"format": "rapid_fire", "title": "T", "host_intro": "I",
                "questions": [dict(_rapid_fire_q("c-l1")) for _ in range(8)]}

    quiz.kick_restock(root, db_path, "c-lock2", generate=fake_generate, spawn=lambda target: target())
    assert quiz.bank_count(root, "c-lock2") == quiz.BANK_FLOOR


def test_kick_restock_single_flight_second_kick_is_noop(tmp_path):
    root = _course_dir(tmp_path, completed=("c-l1",), course_id="c-lock1")
    db_path = tmp_path / "t.db"
    conn0 = db.get_connection(db_path)
    db.init_db(conn0)
    _complete(conn0, "c-l1", course_id="c-lock1")
    conn0.close()

    started = threading.Event()
    release = threading.Event()
    calls = []

    # Blocks on EVERY call until the test releases it — this pins the first
    # restock run inside its very first generate() call for the whole window
    # where we probe the second kick, so "second kick is a no-op" can be
    # checked as "no second call happened yet" rather than needing to reason
    # about how many rounds one successful run generates (up to RESTOCK_CAP).
    def slow_generate(prompt, validate):
        calls.append(1)
        started.set()
        release.wait(5)
        return {"format": "rapid_fire", "title": "T", "host_intro": "I",
                "questions": [dict(_rapid_fire_q("c-l1")) for _ in range(8)]}

    def real_spawn(target):
        threading.Thread(target=target, daemon=True).start()

    quiz.kick_restock(root, db_path, "c-lock1", generate=slow_generate, spawn=real_spawn)
    started.wait(2)
    # a second kick while the first is still blocked mid-generate is a no-op —
    # it must not block the caller and must not enter a second generate() call
    # while the first restock run is still in flight.
    quiz.kick_restock(root, db_path, "c-lock1", generate=slow_generate, spawn=real_spawn)
    time.sleep(0.2)
    assert len(calls) == 1  # the second kick never called generate at all
    release.set()  # let the first run finish so its thread doesn't outlive the test
    time.sleep(0.3)
