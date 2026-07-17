import json

import pytest

from backend import quiz


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
