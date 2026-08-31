#!/usr/bin/env python3
"""Generate the npm and PyPI source trees for the Flyte skills distributions.

One source of truth -- ``plugins/flyte/`` -- fans out into four published
artifacts: the same content under two names (``flyte-skills`` and
``flyte-agent-plugins``) on two registries. The names are mirrors, not an alias
and a shim: each carries the full payload so each registry's download counter
reports real installs of that name rather than a redirect.

    python packaging/build.py                 # build everything into ./build
    python packaging/build.py --print-version # version from the plugin manifest
    python packaging/build.py --only npm      # just the npm trees

The version comes from ``plugins/flyte/.claude-plugin/plugin.json``; use
``packaging/set_version.py`` to change it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_SRC = REPO / "plugins" / "flyte"
TEMPLATES = REPO / "packaging" / "templates"

# npm provenance attestations are rejected unless package.json's repository URL
# matches the repo the workflow runs in, so prefer the CI-provided slug.
REPO_URL = (
    f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
    if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_REPOSITORY")
    else "https://github.com/flyteorg/flyte-agent-plugins"
)
DISTS = ["flyte-skills", "flyte-agent-plugins"]

KEYWORDS = [
    "flyte",
    "agent-skills",
    "claude-code",
    "claude-code-plugin",
    "codex",
    "mcp",
    "workflow-orchestration",
]


def version() -> str:
    manifest = json.loads((PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text())
    return manifest["version"]


def description() -> str:
    manifest = json.loads((PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text())
    return manifest["description"]


def module_name(dist: str) -> str:
    return dist.replace("-", "_")


def strip_blocks(text: str, registry: str) -> str:
    """Drop the ``<!-- <other>-only:start -->`` sections from the README template.

    The two registries share one template but not one install story, so each
    package's README carries only the instructions that actually work for it.
    """
    for other in ("npm", "pypi"):
        if other == registry:
            text = text.replace(f"<!-- {other}-only:start -->\n", "")
            text = text.replace(f"<!-- {other}-only:end -->\n", "")
            continue
        start, end = f"<!-- {other}-only:start -->\n", f"<!-- {other}-only:end -->\n"
        while start in text:
            head, _, rest = text.partition(start)
            _, _, tail = rest.partition(end)
            text = head + tail
    return text


def render_readme(dist: str, ver: str, registry: str) -> str:
    tmpl = strip_blocks((TEMPLATES / "README.md.tmpl").read_text(), registry)
    other = [d for d in DISTS if d != dist][0]
    return (
        tmpl.replace("{{DIST}}", dist)
        .replace("{{OTHER_DIST}}", other)
        .replace("{{MODULE}}", module_name(dist))
        .replace("{{VERSION}}", ver)
        .replace("{{REPO_URL}}", REPO_URL)
        .replace("{{DESCRIPTION}}", description())
        .replace("{{SKILL_COUNT}}", str(len(skill_names())))
    )


def skill_names() -> list[str]:
    return sorted(
        p.name for p in (PLUGIN_SRC / "skills").iterdir() if (p / "SKILL.md").is_file()
    )


def copy_plugin(dest: Path) -> None:
    """Copy the plugin payload (manifests + .mcp.json + skills) into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in (".claude-plugin", ".codex-plugin", "skills"):
        shutil.copytree(PLUGIN_SRC / name, dest / name)
    shutil.copy2(PLUGIN_SRC / ".mcp.json", dest / ".mcp.json")


def build_npm(dist: str, ver: str, outdir: Path) -> Path:
    """An npm plugin source requires the package root to BE the plugin root."""
    pkg = outdir / "npm" / dist
    if pkg.exists():
        shutil.rmtree(pkg)
    copy_plugin(pkg)

    (pkg / "bin").mkdir()
    shutil.copy2(TEMPLATES / "cli.mjs", pkg / "bin" / "cli.mjs")
    (pkg / "bin" / "cli.mjs").chmod(0o755)

    shutil.copy2(REPO / "LICENSE", pkg / "LICENSE")
    (pkg / "README.md").write_text(render_readme(dist, ver, "npm"))

    package_json = {
        "name": dist,
        "version": ver,
        "description": description(),
        "license": "Apache-2.0",
        "homepage": f"{REPO_URL}#readme",
        "repository": {"type": "git", "url": f"git+{REPO_URL}.git"},
        "bugs": {"url": f"{REPO_URL}/issues"},
        "keywords": KEYWORDS + ["pi-package"],
        "type": "module",
        "bin": {dist: "bin/cli.mjs"},
        # An explicit allowlist: the payload lives in dot-directories, which the
        # default npm file selection is not reliable about including.
        "files": [
            ".claude-plugin/",
            ".codex-plugin/",
            ".mcp.json",
            "skills/",
            "bin/",
            "README.md",
            "LICENSE",
        ],
        "engines": {"node": ">=18"},
        # pi reads its skill roots from this manifest.
        "pi": {"skills": ["./skills"]},
        "publishConfig": {"access": "public", "provenance": True},
    }
    (pkg / "package.json").write_text(json.dumps(package_json, indent=2) + "\n")
    return pkg


def build_pypi(dist: str, ver: str, outdir: Path) -> Path:
    mod = module_name(dist)
    pkg = outdir / "pypi" / dist
    if pkg.exists():
        shutil.rmtree(pkg)
    src = pkg / "src" / mod
    src.mkdir(parents=True)

    copy_plugin(src / "plugin")
    shutil.copy2(TEMPLATES / "cli.py", src / "cli.py")
    (src / "__init__.py").write_text(
        f'"""Flyte agent skills, installable into any agent harness."""\n\n'
        f'__version__ = "{ver}"\n\n'
        f"from .cli import TARGETS, main, plugin_root\n\n"
        f'__all__ = ["TARGETS", "main", "plugin_root", "__version__"]\n'
    )

    shutil.copy2(REPO / "LICENSE", pkg / "LICENSE")
    (pkg / "README.md").write_text(render_readme(dist, ver, "pypi"))

    pyproject = f"""\
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "{dist}"
version = "{ver}"
description = "{description()}"
readme = "README.md"
requires-python = ">=3.9"
license = "Apache-2.0"
license-files = ["LICENSE"]
authors = [{{ name = "flyteorg" }}]
keywords = {json.dumps(KEYWORDS)}
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Topic :: Software Development :: Code Generators",
]
dependencies = []

[project.urls]
Homepage = "{REPO_URL}"
Repository = "{REPO_URL}"
Issues = "{REPO_URL}/issues"

[project.scripts]
{dist} = "{mod}.cli:main"

# The payload is markdown under src/{mod}/plugin/, including dot-directories.
# ignore-vcs keeps a build/ directory listed in .gitignore from being pruned.
[tool.hatch.build]
ignore-vcs = true

[tool.hatch.build.targets.wheel]
packages = ["src/{mod}"]
artifacts = ["src/{mod}/plugin/**"]

[tool.hatch.build.targets.sdist]
include = ["src", "README.md", "LICENSE", "pyproject.toml"]
artifacts = ["src/{mod}/plugin/**"]
"""
    (pkg / "pyproject.toml").write_text(pyproject)
    return pkg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(REPO / "build"))
    ap.add_argument("--only", choices=["npm", "pypi"], help="Build only one registry.")
    ap.add_argument(
        "--print-version",
        action="store_true",
        help="Print the version from the plugin manifest and exit.",
    )
    args = ap.parse_args()

    ver = version()
    if args.print_version:
        print(ver)
        return 0

    outdir = Path(args.outdir).resolve()
    skills = skill_names()
    if not skills:
        raise SystemExit(f"No skills found under {PLUGIN_SRC / 'skills'}")

    print(f"version {ver}, {len(skills)} skills, out={outdir}")
    for dist in DISTS:
        if args.only != "pypi":
            print(f"  npm  {build_npm(dist, ver, outdir)}")
        if args.only != "npm":
            print(f"  pypi {build_pypi(dist, ver, outdir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
