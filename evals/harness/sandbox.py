"""Isolated workspace for one agent run: dir, skill install, stub-PATH, env.

A `Sandbox` is a throwaway temp directory the agent runs inside. For the
trajectory tier it also lays down *stub* binaries (fake kubectl/helm/docker/...)
earlier on PATH than the real ones, so side-effecting commands the agent issues
log their argv to `<workspace>/.stublog` and succeed without touching real infra.
The `stub_called` check then asserts on what the agent *would* have run.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import tempfile
from dataclasses import dataclass, field

from .glm import GLMConfig

# Side-effecting tools the deploy/SDK skills may invoke. Stubbed in trajectory
# tier; real (unstubbed) in real tier.
STUBBED_TOOLS = [
    "kubectl", "helm", "docker", "kind", "k3d", "aws", "eksctl",
    "gcloud", "doctl", "ssh", "scp", "terraform",
]

_STUB_TEMPLATE = """#!/usr/bin/env bash
# Auto-generated trajectory-tier stub. Logs argv, succeeds, produces no effects.
echo "$(basename "$0") $*" >> "${STUBLOG:-$PWD/.stublog}"
exit 0
"""


@dataclass
class Sandbox:
    workspace: pathlib.Path
    env: dict[str, str]
    stub_bin: pathlib.Path | None = None
    _tmp: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    @property
    def stublog(self) -> pathlib.Path:
        return self.workspace / ".stublog"

    def cleanup(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


def make_sandbox(*, tier: str, glm: GLMConfig | None = None,
                 fixtures: pathlib.Path | None = None) -> Sandbox:
    tmp = tempfile.TemporaryDirectory(prefix="flyte-eval-")
    ws = pathlib.Path(tmp.name) / "workspace"
    ws.mkdir(parents=True)

    if fixtures and fixtures.exists():
        shutil.copytree(fixtures, ws, dirs_exist_ok=True)

    env = dict(os.environ)
    env["STUBLOG"] = str(ws / ".stublog")

    stub_bin = None
    if tier == "trajectory":
        stub_bin = _write_stubs(pathlib.Path(tmp.name) / "stubbin")
        env["PATH"] = f"{stub_bin}{os.pathsep}{env.get('PATH', '')}"

    if glm is not None:
        # Surfaced to runner adapters so each harness can point at the GLM endpoint.
        env.setdefault("GLM_BASE_URL", glm.base_url)
        env.setdefault("GLM_MODEL", glm.model)
        if glm.has_key:
            env.setdefault("GLM_API_KEY", glm.api_key)

    return Sandbox(workspace=ws, env=env, stub_bin=stub_bin, _tmp=tmp)


def install_skill(skill_dir: pathlib.Path, dest_skills_dir: pathlib.Path) -> pathlib.Path:
    """Copy a skill folder into a harness's skills directory. Returns the dest."""
    dest = dest_skills_dir / skill_dir.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest)
    return dest


def _write_stubs(bin_dir: pathlib.Path) -> pathlib.Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool in STUBBED_TOOLS:
        p = bin_dir / tool
        p.write_text(_STUB_TEMPLATE)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir
