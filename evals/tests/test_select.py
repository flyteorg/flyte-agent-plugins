from evals.harness.spec import Manifest, load_scenarios
from evals.select import select, is_shared_infra


def _manifest():
    return Manifest.load()


def test_single_skill_change_selects_only_that_skill():
    m = _manifest()
    scs = load_scenarios()
    out = select(["plugins/flyte-skills/skills/flyte-sdk-author/SKILL.md"], m, scs)
    assert out["run_all"] is False
    assert out["skills"] == ["flyte-sdk-author"]
    assert "flyte-sdk-author-static" in out["scenario_ids"]
    assert "deploy-flyte-kind-static" not in out["scenario_ids"]


def test_engine_change_runs_all():
    m = _manifest()
    scs = load_scenarios()
    out = select(["evals/harness/checks.py"], m, scs)
    assert out["run_all"] is True
    assert len(out["skills"]) >= 15
    assert out["run_kind"] is True and out["run_real"] is True


def test_kind_skill_sets_run_kind():
    m = _manifest()
    scs = load_scenarios()
    out = select(["plugins/flyte-skills/skills/deploy-flyte-kind/SKILL.md"], m, scs)
    assert out["run_kind"] is True
    out2 = select(["plugins/flyte-skills/skills/flyte-sdk-types/SKILL.md"], m, scs)
    assert out2["run_kind"] is False


def test_unrelated_change_selects_nothing():
    m = _manifest()
    scs = load_scenarios()
    out = select(["README.md"], m, scs)
    assert out["skills"] == [] and out["scenario_ids"] == []


def test_is_shared_infra():
    m = _manifest()
    assert is_shared_infra("evals/workflows/eval_wf.py", m)
    assert not is_shared_infra("plugins/flyte-skills/skills/flyte-sdk-run/SKILL.md", m)
