"""Local CLI: run eval scenarios without Flyte.

Examples
--------
  # static lint of every skill (no LLM, no agent):
  python -m evals.harness.run --tier static

  # one scenario on one harness, end-to-end (needs GLM_API_KEY + the harness CLI):
  python -m evals.harness.run --scenario sdk-author-map-task --harness opencode

  # every trajectory scenario for a skill, JSON out:
  python -m evals.harness.run --skill flyte-sdk-author --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .evaluate import ScenarioResult, evaluate_scenario, evaluate_static
from .glm import GLMConfig
from .spec import load_scenarios


def _select(args) -> list:
    scenarios = load_scenarios()
    out = []
    for sc in scenarios:
        if args.scenario and sc.id != args.scenario:
            continue
        if args.skill and sc.skill != args.skill:
            continue
        if args.tier and sc.tier != args.tier:
            continue
        out.append(sc)
    return out


def run(args) -> list[ScenarioResult]:
    glm = GLMConfig.from_env()
    results: list[ScenarioResult] = []
    for sc in _select(args):
        if sc.tier == "static":
            results.append(evaluate_static(sc))
            continue
        harnesses = [args.harness] if args.harness else list(sc.harnesses)
        for h in harnesses:
            results.append(evaluate_scenario(sc, h, glm))
    return results


def _print_table(results: list[ScenarioResult]) -> int:
    if not results:
        print("no scenarios matched the filter", file=sys.stderr)
        return 2
    print(f"{'SCENARIO':<32} {'HARNESS':<9} {'TIER':<11} {'PASS':<5} {'LIFT':>6}")
    print("-" * 70)
    failures = 0
    for r in results:
        lift = "" if r.lift is None else f"{r.lift:+.2f}"
        status = "ok" if r.passed else "FAIL"
        failures += 0 if r.passed else 1
        print(f"{r.scenario_id:<32} {(r.harness or '-'):<9} {r.tier:<11} {status:<5} {lift:>6}")
    print("-" * 70)
    print(f"{len(results)} result(s), {failures} failing")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flyte-evals", description="Run flyte-agent-plugin evals locally")
    ap.add_argument("--scenario", help="scenario id")
    ap.add_argument("--skill", help="filter by skill name")
    ap.add_argument("--tier", choices=["static", "trajectory", "real"], help="filter by tier")
    ap.add_argument("--harness", choices=["opencode", "pi", "hermes"], help="single harness")
    ap.add_argument("--json", dest="json_out", help="write full results JSON to this path")
    args = ap.parse_args(argv)

    results = run(args)
    if args.json_out:
        payload = [r.to_dict() for r in results]
        with open(args.json_out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"wrote {args.json_out}", file=sys.stderr)
    return _print_table(results)


if __name__ == "__main__":
    raise SystemExit(main())
