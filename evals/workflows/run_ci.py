"""CI driver: submit the eval workflow to demo.hosted, wait for it to finish,
and exit non-zero unless the run actually succeeded.

`flyte run` (the CLI) is fire-and-forget — it exits 0 as soon as the run is
*launched*, regardless of whether the run later fails — so the CI job went green
even when the run failed on the backend. This driver submits the same workflow,
blocks on the terminal phase, and propagates the run's success/failure as the
process exit code so GitHub Actions reports it faithfully.

Auth: the flyte v2 SDK reads the API key from the FLYTE_API_KEY env var (sourced
in CI from the DEMO_HOSTED_API_KEY repo secret); the key encodes the endpoint and
org, and project/domain/image-builder come from evals/config/flyte.yaml.

Usage:
  FLYTE_API_KEY=... python -m evals.workflows.run_ci \
      --skills '["flyte-sdk-author"]' --tiers '["static","trajectory"]'
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import yaml

import flyte

from evals.workflows.eval_wf import main

# The one phase that means "the run finished and everything passed".
_SUCCEEDED = "ACTION_PHASE_SUCCEEDED"

# Repo root (…/evals/workflows/run_ci.py -> parents[2]); the copy-bundle base.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _config(path: str) -> tuple[str | None, str | None, str]:
    """Read project/domain/image-builder from the flyte config (single source
    of truth); the endpoint and org come from the API key itself."""
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    task = cfg.get("task", {})
    builder = cfg.get("image", {}).get("builder", "remote")
    return task.get("project"), task.get("domain"), builder


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.workflows.run_ci")
    ap.add_argument("--skills", required=True, help="JSON list of skills to run")
    ap.add_argument("--tiers", required=True, help="JSON list of tiers to run")
    ap.add_argument("--config", default="evals/config/flyte.yaml")
    args = ap.parse_args(argv)

    if not os.getenv("FLYTE_API_KEY"):
        print("::error::FLYTE_API_KEY is not set (expected from the "
              "DEMO_HOSTED_API_KEY repo secret)", flush=True)
        return 1

    skills = json.loads(args.skills) or None
    tiers = json.loads(args.tiers)
    project, domain, builder = _config(args.config)

    # init_from_api_key reads FLYTE_API_KEY from the environment when api_key is
    # None, and decodes the endpoint + org from it (headless — no browser flow).
    # root_dir pins the copy-bundle base to the repo root so the whole project
    # tree is shipped (see copy_style="all" below).
    flyte.init_from_api_key(
        project=project, domain=domain, image_builder=builder, root_dir=_REPO_ROOT,
    )

    # copy_style="all" ships the entire project tree, not just modules imported at
    # submission time. The harness imports evals.harness.* lazily inside the tasks
    # and reads data files off disk (evals/manifest.yaml, evals/scenarios/**, and
    # plugins/flyte/skills/**), resolved relative to the repo root — none of which
    # "loaded_modules" would copy, which is what caused ModuleNotFoundError.
    run = flyte.with_runcontext(copy_style="all").run(
        main, skills=skills, tiers=tiers,
    )
    print(f"Submitted run: {run.name}\n  {run.url}", flush=True)

    # Block until the run reaches a terminal phase, streaming status transitions.
    run.wait()
    phase = run.phase
    print(f"Run terminal phase: {phase}", flush=True)

    if phase != _SUCCEEDED:
        print(f"::error::Eval run {run.name} did not succeed ({phase}) — {run.url}",
              flush=True)
        return 1
    print(f"Eval run {run.name} succeeded.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
