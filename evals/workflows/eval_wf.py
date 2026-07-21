"""Flyte orchestration of the flyte-skills eval harness.

Runs on demo.hosted.unionai.cloud (org demo / project flytesnacks / domain
development, remote image builder — see evals/config/flyte.yaml). The workflow
expands the scenario matrix, fans out one action per (scenario x harness) via
`flyte.map`, then aggregates verdicts into a scorecard.

Run it:
  flyte --config evals/config/flyte.yaml run evals/workflows/eval_wf.py main \\
      --skills '["flyte-sdk-author"]' --tiers '["static","trajectory"]'

The GLM endpoint key is mounted from a Flyte secret `glm-api-key` as GLM_API_KEY.
"""

from __future__ import annotations

import json

import flyte

from evals.workflows.images import eval_image

env = flyte.TaskEnvironment(
    name="flyte-skills-evals",
    image=eval_image,
    resources=flyte.Resources(cpu="2", memory="4Gi"),
    secrets=[flyte.Secret(key="glm-api-key", as_env_var="GLM_API_KEY")],
    env_vars={
        "GLM_BASE_URL": "https://glm-5-2-llm-service-development.apps.demo.hosted.unionai.cloud/v1",
        "GLM_MODEL": "glm-5.2",
        "PYTHONPATH": "/root",
    },
)


@env.task
def eval_unit(unit: dict) -> dict:
    """Evaluate one (scenario_id, harness) unit and return its verdict dict."""
    from evals.harness.evaluate import evaluate_scenario, evaluate_static
    from evals.harness.glm import GLMConfig
    from evals.harness.spec import load_scenarios

    scenarios = {s.id: s for s in load_scenarios()}
    sc = scenarios[unit["scenario_id"]]
    glm = GLMConfig.from_env()
    if sc.tier == "static":
        return evaluate_static(sc).to_dict()
    return evaluate_scenario(sc, unit["harness"], glm).to_dict()


@env.task(report=True)
def aggregate(results: list[dict]) -> dict:
    """Collect verdicts into a scorecard summary (also emits an HTML report)."""
    import flyte.report

    from evals.report import to_html, to_markdown

    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "markdown": to_markdown(results),
        "results": results,
    }
    # Attach the HTML scorecard to the Flyte run's report tab.
    try:
        flyte.report.replace(to_html(results), do_flush=True)
    except Exception:
        pass
    return summary


@env.task
def main(skills: list[str] | None = None,
         harnesses: list[str] | None = None,
         tiers: list[str] | None = None) -> dict:
    """Top-level workflow: build the matrix, fan out, aggregate."""
    from evals.harness.spec import load_scenarios

    tiers = tiers or ["static", "trajectory"]
    scenarios = load_scenarios()

    units: list[dict] = []
    for sc in scenarios:
        if sc.tier not in tiers:
            continue
        if skills and sc.skill not in skills:
            continue
        if sc.tier == "static":
            units.append({"scenario_id": sc.id, "harness": None})
            continue
        for h in (harnesses or list(sc.harnesses)):
            units.append({"scenario_id": sc.id, "harness": h})

    if not units:
        return {"total": 0, "passed": 0, "failed": 0, "results": [], "markdown": "no units selected"}

    results = [r for r in flyte.map(eval_unit, units) if isinstance(r, dict)]
    return aggregate(results)


if __name__ == "__main__":
    # Local driver: `python -m evals.workflows.eval_wf`
    flyte.init_from_config("evals/config/flyte.yaml")
    run = flyte.run(main, skills=None, harnesses=None, tiers=["static"])
    print(run.url)
    print(json.dumps(run.outputs(), indent=2, default=str))
