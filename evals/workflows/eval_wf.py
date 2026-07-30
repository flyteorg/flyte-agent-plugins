"""Flyte orchestration of the flyte-agent-plugin eval harness.

Runs on demo.hosted.unionai.cloud (org demo / project flyte-agent-plugins-evals /
domain development, remote image builder — see evals/config/flyte.yaml). The workflow
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
    name="flyte-agent-plugin-evals",
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
        result = evaluate_static(sc).to_dict()
    else:
        result = evaluate_scenario(sc, unit["harness"], glm).to_dict()

    # Log this unit's verdict so each scenario is visible in its own map action's
    # logs (not just in the aggregate). SCORE shows the tracked rating; SKIP means
    # the agent CLI isn't installed; REGRESSION is a deterministic-check failure.
    from evals.report import reason
    st = result.get("status", "scored")
    tag = {"skipped": "SKIP", "error": "ERROR"}.get(
        st, "REGRESSION" if result.get("is_regression") else "SCORE")
    score = result.get("score")
    score_s = "" if score is None else f" score={score:.2f}"
    suffix = "" if st == "scored" and not result.get("is_regression") else f": {reason(result)}"
    print(f"{tag} {result['scenario_id']} [{result.get('harness') or '-'}] "
          f"({result['skill']}/{result['tier']}){score_s}{suffix}", flush=True)
    return result


@env.task(report=True)
def aggregate(results: list[dict]) -> dict:
    """Collect verdicts into a scorecard summary (also emits an HTML report)."""
    import flyte.report

    from evals.report import rating, to_html, to_markdown

    summary = {
        **rating(results),  # total, scored, skipped, errored, regressions, rating, ...
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
    from evals.harness.evaluate import skipped_scenario
    from evals.harness.runners import get_runner
    from evals.harness.spec import load_scenarios

    tiers = tiers or ["static", "trajectory"]
    scenarios = load_scenarios()
    by_id = {s.id: s for s in scenarios}

    # main runs the same image as eval_unit, so harness availability here matches
    # the workers. Filter unavailable harnesses up front: they become skipped
    # results inline (still on the scorecard) instead of a task pod per skip.
    def _available(h: str) -> bool:
        try:
            return get_runner(h).is_available()
        except Exception:
            return False

    avail_cache: dict[str, bool] = {}
    units: list[dict] = []
    skipped: list[dict] = []
    for sc in scenarios:
        if sc.tier not in tiers:
            continue
        if skills and sc.skill not in skills:
            continue
        if sc.tier == "static":
            units.append({"scenario_id": sc.id, "harness": None})
            continue
        for h in (harnesses or list(sc.harnesses)):
            ok = avail_cache.setdefault(h, _available(h))
            (units if ok else skipped).append({"scenario_id": sc.id, "harness": h})

    if not units and not skipped:
        return {"total": 0, "scored": 0, "skipped": 0, "errored": 0,
                "regressions": 0, "rating": None, "results": [], "markdown": "no units selected"}

    results = [r for r in flyte.map(eval_unit, units) if isinstance(r, dict)] if units else []
    # Add skipped harnesses as synthetic results (no task spent) for visibility.
    results += [skipped_scenario(by_id[u["scenario_id"]], u["harness"]).to_dict()
                for u in skipped]
    summary = aggregate(results)

    import os

    from evals.report import failure_report

    # Emit the rating + per-scenario breakdown to this action's logs, so the
    # tracked score and any regressions are visible right next to the run (not
    # only in the HTML scorecard on the report tab).
    print(failure_report(summary["results"]), flush=True)

    # Gate the run — and therefore CI, which keys on the terminal phase — on
    # REGRESSIONS only: static SKILL.md lint failures, the one deterministic,
    # non-stochastic signal. A skipped harness (agent CLI not installed), a
    # trajectory arm's low score, or a soft LLM-judge verdict never fails the run;
    # those are tracked as the rating over time. An optional FLYTE_EVALS_MIN_RATING
    # adds a floor for stricter runs. aggregate() already attached the scorecard.
    regressions = [r for r in summary["results"] if r.get("is_regression")]
    if regressions:
        ids = ", ".join(
            f"{r['scenario_id']}"
            for r in sorted(regressions, key=lambda r: (r["skill"], r["scenario_id"]))
        )
        raise RuntimeError(
            f"{len(regressions)} static-lint regression(s): {ids}"
        )

    floor = os.environ.get("FLYTE_EVALS_MIN_RATING")
    if floor and summary["rating"] is not None and summary["rating"] < float(floor):
        raise RuntimeError(
            f"eval rating {summary['rating']:.3f} is below the required "
            f"minimum {float(floor):.3f}"
        )
    return summary


if __name__ == "__main__":
    # Local driver: `python -m evals.workflows.eval_wf`
    flyte.init_from_config("evals/config/flyte.yaml")
    run = flyte.run(main, skills=None, harnesses=None, tiers=["static"])
    print(run.url)
    print(json.dumps(run.outputs(), indent=2, default=str))
