"""Evaluate one scenario end-to-end and produce a scored verdict.

Static tier   -> lint the SKILL.md (no agent, no LLM).
Trajectory    -> for each arm (treatment/control): sandbox -> run harness ->
                 deterministic checks + LLM judge. Report per-arm score and the
                 treatment-minus-control *lift*.
Real tier     -> trajectory, plus (best-effort) execute the produced artifact
                 (`flyte run` on demo.hosted); the real-run outcome is recorded
                 as an extra check. Executed by the caller/workflow, gated on env.

The whole module is defensive: a harness crash, missing CLI, or judge/network
error becomes a failed result with detail — never an exception that aborts a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import checks as checks_mod
from .glm import GLMConfig
from .judge import JudgeResult, judge as run_judge
from .runners import get_runner
from .runners.base import Trajectory
from .sandbox import make_sandbox
from .spec import REPO_ROOT, Scenario
from .static_lint import lint_skill


@dataclass
class ArmResult:
    arm: str
    checks: list[checks_mod.CheckResult] = field(default_factory=list)
    judge: JudgeResult | None = None
    exit_code: int = 0
    error: str = ""

    @property
    def checks_passed(self) -> bool:
        return all(c.passed for c in self.checks) if self.checks else True

    @property
    def score(self) -> float:
        """Combined arm score in [0,1]: deterministic checks gate, judge grades."""
        if not self.checks_passed:
            return 0.0
        if self.judge is not None:
            return self.judge.score
        return 1.0 if self.checks_passed else 0.0

    @property
    def passed(self) -> bool:
        judge_ok = self.judge.passed if self.judge is not None else True
        return self.checks_passed and judge_ok and not self.error


@dataclass
class ScenarioResult:
    scenario_id: str
    skill: str
    tier: str
    harness: str | None = None
    arms: dict[str, ArmResult] = field(default_factory=dict)

    @property
    def lift(self) -> float | None:
        t, c = self.arms.get("treatment"), self.arms.get("control")
        if t is None or c is None:
            return None
        return round(t.score - c.score, 4)

    @property
    def passed(self) -> bool:
        t = self.arms.get("treatment")
        return bool(t and t.passed)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "skill": self.skill,
            "tier": self.tier,
            "harness": self.harness,
            "passed": self.passed,
            "lift": self.lift,
            "arms": {
                arm: {
                    "score": r.score,
                    "passed": r.passed,
                    "checks_passed": r.checks_passed,
                    "exit_code": r.exit_code,
                    "error": r.error,
                    "judge": None if r.judge is None else {
                        "score": r.judge.score,
                        "passed": r.judge.passed,
                        "dimensions": r.judge.dimensions,
                        "rationale": r.judge.rationale,
                    },
                    "checks": [
                        {"kind": c.kind, "passed": c.passed, "detail": c.detail}
                        for c in r.checks
                    ],
                }
                for arm, r in self.arms.items()
            },
        }


def evaluate_static(scenario: Scenario) -> ScenarioResult:
    skill_dir = REPO_ROOT / "plugins" / "flyte" / "skills" / scenario.skill
    results = lint_skill(skill_dir)
    arm = ArmResult(arm="treatment", checks=results)
    return ScenarioResult(scenario.id, scenario.skill, "static", harness=None,
                          arms={"treatment": arm})


def evaluate_scenario(scenario: Scenario, harness: str, glm: GLMConfig) -> ScenarioResult:
    """Run a trajectory/real scenario for one harness across its arms."""
    if scenario.tier == "static":
        return evaluate_static(scenario)

    res = ScenarioResult(scenario.id, scenario.skill, scenario.tier, harness=harness)
    runner = get_runner(harness)

    for arm in scenario.arms():
        if not runner.is_available():
            res.arms[arm] = ArmResult(arm=arm, error=f"{harness} CLI not available")
            continue
        try:
            with make_sandbox(tier=scenario.tier, glm=glm) as sb:
                traj = runner.run(scenario, sb, arm, glm)
                arm_res = _score_trajectory(scenario, traj, sb, glm)
                # Real tier: actually execute the produced artifact (treatment only).
                if scenario.tier == "real" and arm == "treatment" and scenario.real_run:
                    arm_res.checks.append(_maybe_real_run(scenario, sb))
        except Exception as exc:  # never let one arm abort the suite
            arm_res = ArmResult(arm=arm, error=f"harness crashed: {exc!r}")
        res.arms[arm] = arm_res

    return res


def _maybe_real_run(scenario: Scenario, sandbox) -> "checks_mod.CheckResult":
    """Execute the produced workflow via `flyte run` on demo.hosted (gated).

    Guarded by FLYTE_EVALS_ENABLE_REAL so trajectory/local testing never submits
    a remote run by accident. The Flyte task/CI sets it explicitly.
    """
    import os
    import subprocess

    spec = scenario.real_run
    if not (spec and spec.flyte_run):
        return checks_mod.CheckResult("real_run", True, "no real_run requested")
    if os.environ.get("FLYTE_EVALS_ENABLE_REAL", "").lower() not in ("1", "true", "yes"):
        return checks_mod.CheckResult("real_run", True, "skipped (FLYTE_EVALS_ENABLE_REAL unset)")

    entry = (spec.entrypoint or "").split()
    if not entry:
        return checks_mod.CheckResult("real_run", False, "real_run.entrypoint not set")
    cmd = ["flyte", "--config", str(REPO_ROOT / "evals" / "config" / "flyte.yaml"), "run", *entry]
    for k, v in spec.inputs.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    try:
        proc = subprocess.run(cmd, cwd=str(sandbox.workspace), capture_output=True,
                              text=True, timeout=1800)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return checks_mod.CheckResult("real_run", False, f"flyte run failed to start: {e}")
    out = proc.stdout + proc.stderr
    ok = proc.returncode == 0 and (spec.expect_status.upper() in out.upper() or proc.returncode == 0)
    tail = " / ".join(out.strip().splitlines()[-3:])
    return checks_mod.CheckResult("real_run", ok, f"exit {proc.returncode} :: {tail}")


def _score_trajectory(scenario: Scenario, traj: Trajectory, sandbox, glm: GLMConfig) -> ArmResult:
    check_results = checks_mod.run_checks(sandbox.workspace, list(scenario.checks))
    judge_result = None
    if scenario.judge is not None:
        judge_result = run_judge(scenario.judge, traj.as_judge_text(), glm)
    return ArmResult(
        arm=traj.arm,
        checks=check_results,
        judge=judge_result,
        exit_code=traj.exit_code,
        error=traj.error,
    )
