#!/usr/bin/env python3
"""Build every distribution and prove it installs before we publish it.

Run locally exactly as CI runs it:

    python packaging/verify.py

Checks, for both names on both registries:
  * every manifest agrees on one version;
  * every skill has frontmatter with a name matching its directory;
  * the npm tarball carries the dot-directories Claude Code needs at the package
    root (npm's default file selection is not reliable about those);
  * the built wheel carries the skills as package data;
  * both CLIs install the full skill set into a directory and remove it again.

Requires: node/npm, and either `uv` or `python -m build`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packaging"))

import build as builder  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True, **kw)


def check_versions() -> None:
    print("versions")
    versions = {}
    for path in (
        REPO / "plugins/flyte/.claude-plugin/plugin.json",
        REPO / "plugins/flyte/.codex-plugin/plugin.json",
        REPO / "package.json",
    ):
        versions[path.relative_to(REPO).as_posix()] = json.loads(path.read_text())["version"]
    check(len(set(versions.values())) == 1, f"one version across manifests: {versions}")


def check_targets(workdir: Path, npm_pkg: Path, py_exe: str) -> None:
    """The Python and Node CLIs declare harness targets independently, so a
    target added to one and forgotten in the other is a real drift risk."""
    print("targets")
    node_out = run(["node", str(npm_pkg / "bin" / "cli.mjs"), "install", "--target", "nope"], check=False)
    py_out = run([py_exe, "install", "--target", "nope"], check=False)

    def parse(stderr: str) -> set[str]:
        # Both CLIs reject an unknown target by listing the valid ones, but
        # argparse quotes its choices and the Node parser does not.
        listed = stderr.split("choose from ")[-1].split(")")[0]
        return {t.strip().strip("'\"") for t in listed.split(",") if t.strip()}

    node_targets, py_targets = parse(node_out.stderr), parse(py_out.stderr)
    check(
        node_targets == py_targets and len(py_targets) > 1,
        f"both CLIs declare the same targets: {sorted(py_targets)}",
    )


def check_skills() -> None:
    print("skills")
    names = builder.skill_names()
    check(len(names) > 0, f"{len(names)} skills found")
    for name in names:
        text = (REPO / "plugins/flyte/skills" / name / "SKILL.md").read_text()
        if not text.startswith("---\n"):
            check(False, f"{name}: SKILL.md has YAML frontmatter")
            continue
        fm = text.split("---\n", 2)[1]
        declared = next(
            (ln.split(":", 1)[1].strip() for ln in fm.splitlines() if ln.startswith("name:")),
            None,
        )
        has_desc = any(ln.startswith("description:") for ln in fm.splitlines())
        check(declared == name and has_desc, f"{name}: frontmatter name + description")


def check_npm(dist: str, pkg: Path, workdir: Path) -> None:
    print(f"npm {dist}")
    out = run(["npm", "pack", "--dry-run", "--json"], cwd=pkg).stdout
    files = {f["path"] for f in json.loads(out)[0]["files"]}
    for required in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".mcp.json", "bin/cli.mjs"):
        check(required in files, f"tarball contains {required}")
    packed = {f.split("/")[1] for f in files if f.startswith("skills/")}
    check(packed == set(builder.skill_names()), f"tarball contains all {len(builder.skill_names())} skills")

    dest = workdir / f"npm-{dist}"
    cli = str(pkg / "bin" / "cli.mjs")
    run(["node", cli, "install", "--dir", str(dest)])
    installed = sorted(p.name for p in dest.iterdir() if (p / "SKILL.md").is_file())
    check(installed == builder.skill_names(), f"`{dist} install --dir` writes every skill")
    run(["node", cli, "uninstall", "--dir", str(dest)])
    check(not any(dest.iterdir()), f"`{dist} uninstall --dir` removes them again")
    check(run(["node", cli, "version"]).stdout.strip() == builder.version(), "`version` matches manifest")
    emitted = run(["node", cli, "emit-plugin"]).stdout
    check(
        emitted.count("\n") == 1 and Path(emitted.strip()).is_absolute(),
        "`emit-plugin` prints exactly one absolute path",
    )


def build_wheel(pkg: Path) -> Path:
    try:
        run([sys.executable, "-m", "build", "--wheel"], cwd=pkg)
    except (subprocess.CalledProcessError, FileNotFoundError):
        run(["uv", "build", "--wheel"], cwd=pkg)
    return next((pkg / "dist").glob("*.whl"))


def check_pypi(dist: str, pkg: Path, workdir: Path) -> None:
    print(f"pypi {dist}")
    wheel = build_wheel(pkg)
    import zipfile

    names = set(zipfile.ZipFile(wheel).namelist())
    mod = builder.module_name(dist)
    check(f"{mod}/plugin/.claude-plugin/plugin.json" in names, "wheel contains .claude-plugin/plugin.json")
    check(f"{mod}/plugin/.mcp.json" in names, "wheel contains .mcp.json")
    packed = {n.split("/")[3] for n in names if n.startswith(f"{mod}/plugin/skills/")}
    check(packed == set(builder.skill_names()), f"wheel contains all {len(builder.skill_names())} skills")

    venv = workdir / f"venv-{dist}"
    if shutil.which("uv"):
        run(["uv", "venv", "--quiet", str(venv)])
        run(["uv", "pip", "install", "--quiet", "--python", str(venv / "bin/python"), str(wheel)])
    else:
        run([sys.executable, "-m", "venv", str(venv)])
        run([str(venv / "bin/pip"), "install", "--quiet", str(wheel)])

    exe = str(venv / "bin" / dist)
    dest = workdir / f"pypi-{dist}"
    run([exe, "install", "--dir", str(dest)])
    installed = sorted(p.name for p in dest.iterdir() if (p / "SKILL.md").is_file())
    check(installed == builder.skill_names(), f"`{dist} install --dir` writes every skill")
    run([exe, "uninstall", "--dir", str(dest)])
    check(not any(dest.iterdir()), f"`{dist} uninstall --dir` removes them again")
    check(run([exe, "version"]).stdout.strip() == builder.version(), "`version` matches manifest")
    emitted = run([exe, "emit-plugin"]).stdout
    check(
        emitted.count("\n") == 1 and Path(emitted.strip()).is_absolute(),
        "`emit-plugin` prints exactly one absolute path",
    )
    check_targets(workdir, workdir / "build" / "npm" / dist, exe)


def main() -> int:
    check_versions()
    check_skills()

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        outdir = workdir / "build"
        subprocess.run(
            [sys.executable, str(REPO / "packaging/build.py"), "--outdir", str(outdir)],
            check=True,
        )
        for dist in builder.DISTS:
            check_npm(dist, outdir / "npm" / dist, workdir)
            check_pypi(dist, outdir / "pypi" / dist, workdir)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
