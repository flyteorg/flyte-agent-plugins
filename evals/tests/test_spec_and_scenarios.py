"""Validate that every committed scenario spec loads and is well-formed, and that
every skill under plugins/ has at least a static scenario."""

import pathlib

import pytest

from evals.harness.spec import REPO_ROOT, Scenario, load_scenarios, scenarios_by_skill

SKILLS_DIR = REPO_ROOT / "plugins" / "flyte" / "skills"


def test_all_scenarios_load():
    scenarios = load_scenarios()
    assert scenarios, "no scenarios found"


def test_every_scenario_references_a_real_skill():
    valid = {p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists()}
    for sc in load_scenarios():
        assert sc.skill in valid, f"{sc.id} references unknown skill {sc.skill}"


def test_every_skill_has_a_static_scenario():
    by_skill = scenarios_by_skill(load_scenarios())
    for p in SKILLS_DIR.iterdir():
        if (p / "SKILL.md").exists():
            tiers = {sc.tier for sc in by_skill.get(p.name, [])}
            assert "static" in tiers, f"skill {p.name} has no static scenario"


def test_arms_logic():
    static = Scenario.from_dict({"id": "x", "skill": "flyte-sdk-run", "tier": "static"})
    assert static.arms() == ("treatment",)
    traj = Scenario.from_dict({"id": "y", "skill": "flyte-sdk-run", "tier": "trajectory",
                               "prompt": "p"})
    assert set(traj.arms()) == {"treatment", "control"}
    no_ctrl = Scenario.from_dict({"id": "z", "skill": "flyte-sdk-run", "tier": "trajectory",
                                  "prompt": "p", "control": False})
    assert no_ctrl.arms() == ("treatment",)


def test_invalid_tier_rejected():
    with pytest.raises(ValueError):
        Scenario.from_dict({"id": "bad", "skill": "flyte-sdk-run", "tier": "nope", "prompt": "p"})


def test_trajectory_requires_prompt():
    with pytest.raises(ValueError):
        Scenario.from_dict({"id": "bad", "skill": "flyte-sdk-run", "tier": "trajectory"})
