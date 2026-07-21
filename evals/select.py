"""Map changed files -> the subset of scenarios to run.

Used by CI to run only what a PR affects:
  - a changed `plugins/flyte-skills/skills/<skill>/**` -> that skill's scenarios
  - a change to engine/shared-infra paths (manifest.shared_infra_globs) -> run ALL
  - flags whether the kind DinD smoke and the real tier are in scope

Emits JSON on stdout:
  {"run_all": bool, "skills": [...], "scenario_ids": [...],
   "run_kind": bool, "run_real": bool}

Usage:
  python -m evals.select --base origin/main            # diff vs a git ref
  python -m evals.select --changed a.md b.py           # explicit file list
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import re
import subprocess
import sys

from evals.harness.spec import Manifest, load_scenarios, scenarios_by_skill

SKILL_PATH_RE = re.compile(r"plugins/flyte-skills/skills/([^/]+)/")


def changed_from_git(base: str, repo_root: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if out.returncode != 0:
        # fall back to a plain diff (e.g. no merge-base) so CI still selects something
        out = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=str(repo_root), capture_output=True, text=True,
        )
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def is_shared_infra(path: str, manifest: Manifest) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in manifest.shared_infra_globs)


def select(changed: list[str], manifest: Manifest, scenarios) -> dict:
    by_skill = scenarios_by_skill(scenarios)
    run_all = any(is_shared_infra(p, manifest) for p in changed)

    if run_all:
        chosen_skills = sorted(by_skill)
    else:
        chosen_skills = sorted({
            m.group(1) for p in changed if (m := SKILL_PATH_RE.search(p))
        })

    chosen = [sc for sk in chosen_skills for sc in by_skill.get(sk, [])]
    scenario_ids = sorted(sc.id for sc in chosen)

    run_kind = run_all or any(sk in manifest.kind_smoke_skills for sk in chosen_skills)
    run_real = run_all or any(sk in manifest.sdk_real_skills for sk in chosen_skills)

    return {
        "run_all": run_all,
        "skills": chosen_skills,
        "scenario_ids": scenario_ids,
        "run_kind": run_kind,
        "run_real": run_real,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.select")
    ap.add_argument("--base", help="git ref to diff against (e.g. origin/main)")
    ap.add_argument("--changed", nargs="*", help="explicit changed file list")
    args = ap.parse_args(argv)

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    manifest = Manifest.load()
    scenarios = load_scenarios()

    if args.changed is not None:
        changed = args.changed
    elif args.base:
        changed = changed_from_git(args.base, repo_root)
    else:
        print("provide --base <ref> or --changed <files...>", file=sys.stderr)
        return 2

    print(json.dumps(select(changed, manifest, scenarios), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
