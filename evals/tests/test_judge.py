from evals.harness.judge import parse_response
from evals.harness.spec import JudgeSpec


def test_parse_weighted_pass():
    text = '{"scores": {"correctness": 1.0, "idiomatic": 0.5}, "rationale": "good"}'
    r = parse_response(text, {"correctness": 0.8, "idiomatic": 0.2}, 0.7)
    assert r.passed
    assert abs(r.score - (1.0 * 0.8 + 0.5 * 0.2)) < 1e-9
    assert r.rationale == "good"


def test_parse_below_threshold():
    text = 'noise {"scores": {"correctness": 0.2}} trailing'
    r = parse_response(text, {"correctness": 1.0}, 0.7)
    assert not r.passed and r.score == 0.2


def test_parse_clamps_out_of_range():
    r = parse_response('{"scores": {"a": 5, "b": -3}}', {}, 0.7)
    assert r.dimensions == {"a": 1.0, "b": 0.0}


def test_parse_garbage_is_error_not_crash():
    r = parse_response("the model refused", {}, 0.7)
    assert not r.passed and r.score == 0.0 and "judge error" in r.rationale


def test_judgespec_from_dict():
    spec = JudgeSpec.from_dict({"rubric": "r", "weights": {"correctness": 1}, "pass_threshold": 0.9})
    assert spec.pass_threshold == 0.9 and spec.weights["correctness"] == 1
    assert JudgeSpec.from_dict(None) is None
