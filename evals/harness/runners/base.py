"""Runner adapter interface + the Trajectory it returns.

A Runner points a specific agent harness at the GLM endpoint, installs the skill
under test (treatment arm only), runs one non-interactive turn on the scenario
prompt inside the sandbox workspace, and returns a Trajectory: the transcript,
the files the agent produced, and the process outcome.
"""

from __future__ import annotations

import abc
import pathlib
import subprocess
from dataclasses import dataclass, field

from ..glm import GLMConfig
from ..sandbox import Sandbox, install_skill
from ..spec import Scenario

# Files we never treat as "agent-produced artifacts" when snapshotting a workspace.
# `.hermes` holds the installed skill (would leak SKILL.md into the judge prompt as
# agent output); `opencode.json` holds the GLM API key.
_IGNORE = {".stublog", ".opencode", ".pi", ".hermes", ".git", "opencode.json"}


@dataclass
class Trajectory:
    harness: str
    arm: str                                   # "treatment" | "control"
    transcript: str                            # what the agent said (stdout / json events)
    files: dict[str, str] = field(default_factory=dict)   # relpath -> content
    exit_code: int = 0
    error: str = ""

    def as_judge_text(self, max_chars: int = 16000) -> str:
        parts = [f"## Transcript\n{self.transcript.strip()}"]
        for rel, content in sorted(self.files.items()):
            parts.append(f"## File: {rel}\n```\n{content}\n```")
        text = "\n\n".join(parts)
        return text[:max_chars]


class Runner(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True if the harness CLI is installed and usable."""

    @abc.abstractmethod
    def skills_dir(self, workspace: pathlib.Path) -> pathlib.Path:
        """Where this harness discovers skills, relative to the workspace."""

    @abc.abstractmethod
    def _invoke(self, prompt: str, sandbox: Sandbox, glm: GLMConfig) -> tuple[str, int, str]:
        """Run one non-interactive turn. Returns (transcript, exit_code, error)."""

    def run(self, scenario: Scenario, sandbox: Sandbox, arm: str, glm: GLMConfig) -> Trajectory:
        if arm not in ("treatment", "control"):
            raise ValueError(f"bad arm {arm!r}")
        if arm == "treatment":
            skill_dir = _repo_skill_dir(scenario.skill)
            install_skill(skill_dir, self.skills_dir(sandbox.workspace))
        transcript, code, err = self._invoke(scenario.prompt, sandbox, glm)
        return Trajectory(
            harness=self.name,
            arm=arm,
            transcript=transcript,
            files=snapshot_files(sandbox.workspace),
            exit_code=code,
            error=err,
        )


def snapshot_files(workspace: pathlib.Path, max_bytes: int = 200_000) -> dict[str, str]:
    """Capture text files the agent produced in the workspace."""
    out: dict[str, str] = {}
    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(workspace)
        if any(part in _IGNORE for part in rel.parts):
            continue
        try:
            if p.stat().st_size > max_bytes:
                out[str(rel)] = f"<{p.stat().st_size} bytes, truncated>"
                continue
            out[str(rel)] = p.read_text(errors="ignore")
        except OSError:
            continue
    return out


def _repo_skill_dir(skill: str) -> pathlib.Path:
    from ..spec import REPO_ROOT
    return REPO_ROOT / "plugins" / "flyte" / "skills" / skill


def sh(cmd: list[str], cwd: pathlib.Path, env: dict[str, str], timeout: int = 600
       ) -> tuple[str, int, str]:
    """Helper: run a subprocess, capture combined output. Never raises."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout
        )
        return (proc.stdout + proc.stderr, proc.returncode, "")
    except FileNotFoundError as e:
        return ("", 127, f"binary not found: {e}")
    except subprocess.TimeoutExpired:
        return ("", 124, f"timeout after {timeout}s")
