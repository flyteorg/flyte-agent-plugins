"""Integration test of the scoring/arm/lift plumbing with a mocked harness+judge
so it needs neither a real agent CLI nor the GLM endpoint."""

from evals.harness import evaluate as ev
from evals.harness.glm import GLMConfig
from evals.harness.judge import JudgeResult
from evals.harness.runners.base import Trajectory
from evals.harness.spec import Scenario


class FakeRunner:
    """Treatment arm writes a valid workflow.py; control arm writes nothing."""

    name = "fake"

    def is_available(self):
        return True

    def run(self, scenario, sandbox, arm, glm):
        if arm == "treatment":
            (sandbox.workspace / "workflow.py").write_text(
                "import flyte\n@env.task\ndef f():\n    return 1\n"
            )
        return Trajectory(harness="fake", arm=arm, transcript=f"ran {arm}")


def _scenario():
    return Scenario.from_dict({
        "id": "t", "skill": "flyte-sdk-author", "tier": "trajectory", "prompt": "p",
        "checks": [
            {"kind": "file_glob", "glob": "*.py"},
            {"kind": "python_imports", "module": "flyte"},
        ],
        "judge": {"rubric": "r", "weights": {"correctness": 1.0}, "pass_threshold": 0.7},
    })


def test_treatment_beats_control_positive_lift(monkeypatch):
    monkeypatch.setattr(ev, "get_runner", lambda name: FakeRunner())
    # Judge scores treatment high (checks pass) and is not even called for control
    # (checks fail -> score 0 short-circuits in ArmResult.score).
    monkeypatch.setattr(ev, "run_judge",
                        lambda spec, text, glm: JudgeResult(score=0.9, passed=True,
                                                            dimensions={"correctness": 0.9}))
    res = ev.evaluate_scenario(_scenario(), "fake", GLMConfig("u", "k", "m"))

    assert set(res.arms) == {"treatment", "control"}
    assert res.arms["treatment"].checks_passed is True
    assert res.arms["treatment"].score == 0.9
    assert res.arms["control"].checks_passed is False   # no file produced
    assert res.arms["control"].score == 0.0
    assert res.lift == 0.9
    assert res.passed is True


def test_harness_unavailable_is_recorded_not_crash(monkeypatch):
    class Unavailable(FakeRunner):
        def is_available(self):
            return False
    monkeypatch.setattr(ev, "get_runner", lambda name: Unavailable())
    res = ev.evaluate_scenario(_scenario(), "fake", GLMConfig("u", "k", "m"))
    assert res.arms["treatment"].error and not res.passed


def test_to_dict_serializable(monkeypatch):
    monkeypatch.setattr(ev, "get_runner", lambda name: FakeRunner())
    monkeypatch.setattr(ev, "run_judge",
                        lambda spec, text, glm: JudgeResult(score=0.8, passed=True))
    d = ev.evaluate_scenario(_scenario(), "fake", GLMConfig("u", "k", "m")).to_dict()
    import json
    json.dumps(d)  # must be JSON-serializable for Flyte I/O + report
    assert d["lift"] == 0.8 and d["arms"]["treatment"]["passed"] is True
